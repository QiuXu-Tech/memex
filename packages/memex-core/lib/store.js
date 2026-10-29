/**
 * Filesystem + SQLite storage core for `@qiuxu/memex` and agent adapters.
 *
 * One record is one human-readable markdown file with JSON-in-YAML
 * frontmatter; the SQLite database holds only the queryable projection and an
 * FTS5 index. Files stay the source of truth so the model can reach them with
 * ordinary file tools, while the index makes ranked lookup cheap.
 *
 * All methods are synchronous against SQLite except the file reads/writes that
 * wrap them; the service exposes them behind promises for the seam.
 *
 * @module @qiuxu/memex-core/store
 */
import { DatabaseSync } from 'node:sqlite'
import { mkdirSync, readFileSync, writeFileSync, renameSync, unlinkSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { createHash, randomUUID } from 'node:crypto'
import {
  MEMORY_KINDS, MEMORY_STATUSES, MEMORY_TRUST, MEMORY_TEXT_LIMITS,
  MEMORY_LEVELS, MEMORY_MODES, MEMORY_SCOPES, MEMORY_LEVEL_SCOPE, memoryCaptureScope, memoryLevelsFromRow, memoryVisibleScopes,
  archiveRecordId, clipText, estimateTokens, memoryQueryTerms, DEFAULT_RERANK_WEIGHTS,
} from '../index.js'

/** Bounded prompt-free abstract of a raw body, used for cold-tier search. */
function abstractOfBody(body) {
  return clipText(String(body ?? '').replace(/\s+/g, ' ').trim(), 1000)
}

// ── Body term index: exact, cheap hot-body rescue ────────────────────────────
//
// Card legs only index title/summary/useWhen/tags/abstract. A fact that lives
// only in a record body is otherwise invisible when card matches fill the
// candidate limit. Identifier-like tokens (digits, hyphens, underscores,
// paths, versions) and bare numbers are indexed into `record_terms`
// (record_id, term_hash) from the body **and the card fields**. Those are what
// the body/cold rescues key on — the token set stays small (a few rows per
// record, DB stays small), while a query that has such an anchor can rank
// candidates exactly with one indexed GROUP BY. Natural-language-only facts
// without any number/identifier still rely on card summaries / memory_grep.

const BODY_TERM_LIMIT = 2000
const BODY_TERM_CHARS = 262_144

/** FNV-1a 32-bit hash (deterministic, dependency-free). */
function fnv1a32(text) {
  let hash = 0x811c9dc5
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash >>> 0
}

/** Whether a body token is identifier-like enough to index for rescue. */
function isIdentifierToken(token) {
  return /[0-9]/.test(token) || /[-_./:]/.test(token)
}

/** Bounded **identifier-like** token set for one body (term-index rows). */
function bodyTokens(body) {
  const text = String(body ?? '').slice(0, BODY_TERM_CHARS)
  const tokens = new Set()
  for (const match of text.matchAll(/[A-Za-z][A-Za-z0-9_.:/-]{1,}/g)) {
    const token = match[0].toLowerCase()
    if (!isIdentifierToken(token)) continue
    tokens.add(token)
    if (tokens.size >= BODY_TERM_LIMIT) return tokens
  }
  // Bare turn/step numbers (“turn 25”, “step 3”) are the natural-language
  // anchors users actually type; index them exactly as tokens.
  for (const match of text.matchAll(/\b\d{1,6}\b/g)) {
    tokens.add(match[0])
    if (tokens.size >= BODY_TERM_LIMIT) return tokens
  }
  return tokens
}

/** The term hashes to index for one body. */
function bodyTermHashes(body) {
  return [...bodyTokens(body)].map((term) => fnv1a32(term))
}

const DB_FILE = 'index.db'
const RECORDS_DIR = 'records'

/** JSON.stringify that survives a circular argv-like object. */
function safeJson(value, fallback = '{}') {
  try {
    return JSON.stringify(value ?? {})
  } catch {
    return fallback
  }
}

/** Serialize one frontmatter scalar: JSON strings are valid YAML scalars. */
function fm(key, value) {
  return `${key}: ${JSON.stringify(value)}`
}

/** Render the on-disk markdown file for one record. */
export function renderRecordFile(record) {
  const front = [
    '---',
    fm('id', record.id),
    fm('kind', record.kind),
    fm('scope', record.scope),
    fm('workspace', record.workspace ?? ''),
    fm('workspace_key', record.workspaceKey ?? ''),
    fm('session_id', record.sessionId ?? ''),
    fm('title', record.title),
    fm('use_when', record.useWhen),
    fm('status', record.status),
    fm('trust', record.trust),
    fm('tokens', record.tokens),
    `tags: ${safeJson(record.tags)}`,
    `links: ${safeJson(record.links)}`,
    `provenance: ${safeJson(record.provenance)}`,
    fm('created_at', record.createdAt),
    fm('updated_at', record.updatedAt),
    '---',
    '',
  ].join('\n')
  return `${front}${record.body ?? ''}\n`
}

/** Parse the body out of a stored record file, tolerating user edits to the frontmatter. */
export function recordBodyFromFile(fileText) {
  if (!fileText.startsWith('---\n')) return fileText
  const end = fileText.indexOf('\n---\n', 4)
  if (end < 0) return fileText
  // `renderRecordFile` terminates the file with one newline; strip exactly that
  // terminator so a write→read round-trip returns the body that was written.
  const body = fileText.slice(end + 5).replace(/^\n/, '')
  return body.endsWith('\n') ? body.slice(0, -1) : body
}

/** Render a snippet around the first match of a literal query, or the head of the text. */
function makeSnippet(text, query, max = 180) {
  const value = String(text ?? '').replace(/\s+/g, ' ').trim()
  if (!value) return ''
  const needle = String(query ?? '').trim()
  const at = needle.length >= 2 ? value.toLowerCase().indexOf(needle.toLowerCase()) : -1
  if (at < 0) return clipText(value, max)
  const start = Math.max(0, at - Math.floor(max / 3))
  return `${start > 0 ? '…' : ''}${clipText(value.slice(start), max)}`
}

/**
 * The concrete storage core. One instance serves every workspace; records are
 * partitioned by `workspaceKey` so a single FTS index can answer both
 * workspace-scoped and (later) cross-workspace queries.
 */
export class LocalStoreCore {
  /**
   * @param {object} options - Storage options.
   * @param {string} options.root - Absolute memory root directory.
   * @param {number} options.capacityTokens - Soft capacity target of the workspace-shared pool.
   * @param {number} [options.sessionCapacityTokens] - Soft capacity target of one session-private pool.
   * @param {{l2?: boolean, l3?: boolean}} [options.defaultLevels] - Levels for sessions without a stored choice.
   * @param {() => {warn: (message: string) => void} | undefined} [options.logger] - Lazy logger accessor.
   */
  constructor(options) {
    this.root = options.root
    this.capacityTokens = options.capacityTokens
    this.sessionCapacityTokens = options.sessionCapacityTokens ?? 10_000_000
    this.defaultLevels = { l2: options.defaultLevels?.l2 === true, l3: options.defaultLevels?.l3 === true }
    this.settingsTtlMs = Number.isSafeInteger(options.settingsTtlMs) ? options.settingsTtlMs : 90 * 24 * 60 * 60 * 1000
    this.logger = options.logger
    this.db = undefined
    this.ready = false
  }

  /** Lazily create the root, records tree and database. */
  ensure() {
    if (this.ready) return this
    mkdirSync(join(this.root, RECORDS_DIR), { recursive: true, mode: 0o700 })
    const db = new DatabaseSync(join(this.root, DB_FILE))
    db.exec('PRAGMA journal_mode = WAL')
    db.exec('PRAGMA synchronous = NORMAL')
    db.exec(`
      CREATE TABLE IF NOT EXISTS records (
        id TEXT PRIMARY KEY,
        workspace_key TEXT NOT NULL,
        workspace TEXT NOT NULL DEFAULT '',
        scope TEXT NOT NULL DEFAULT 'workspace',
        session_id TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL,
        title TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        use_when TEXT NOT NULL DEFAULT '',
        tags_json TEXT NOT NULL DEFAULT '{}',
        links_json TEXT NOT NULL DEFAULT '{}',
        provenance_json TEXT NOT NULL DEFAULT '{}',
        path TEXT NOT NULL,
        tokens INTEGER NOT NULL DEFAULT 1,
        bytes INTEGER NOT NULL DEFAULT 0,
        trust TEXT NOT NULL DEFAULT 'trusted',
        status TEXT NOT NULL DEFAULT 'active',
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        read_count INTEGER NOT NULL DEFAULT 0,
        last_read_at INTEGER,
        cold INTEGER NOT NULL DEFAULT 0,
        abstract TEXT NOT NULL DEFAULT ''
      );
      CREATE INDEX IF NOT EXISTS records_ws_index ON records(workspace_key, kind, status, updated_at);
      CREATE INDEX IF NOT EXISTS records_scope_index ON records(workspace_key, scope, session_id, updated_at);
      CREATE TABLE IF NOT EXISTS record_terms (
        record_id TEXT NOT NULL,
        term_hash INTEGER NOT NULL,
        PRIMARY KEY (record_id, term_hash)
      );
      CREATE INDEX IF NOT EXISTS record_terms_hash ON record_terms(term_hash);
      CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
        title, summary, use_when, tags, abstract, tokenize = 'trigram'
      );
      CREATE TABLE IF NOT EXISTS archived_compactions (
        session_id TEXT NOT NULL,
        compaction_id TEXT NOT NULL,
        record_id TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        PRIMARY KEY (session_id, compaction_id)
      );
      CREATE TABLE IF NOT EXISTS l1_evictions (
        session_id TEXT NOT NULL,
        start_seq INTEGER NOT NULL,
        end_seq INTEGER NOT NULL,
        record_id TEXT NOT NULL,
        shadowed_tokens INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        PRIMARY KEY (session_id, start_seq, end_seq)
      );
      CREATE TABLE IF NOT EXISTS compression_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL DEFAULT '',
        level TEXT NOT NULL,
        strategy TEXT NOT NULL,
        before_hot INTEGER NOT NULL,
        after_hot INTEGER NOT NULL,
        cold_moved INTEGER NOT NULL,
        digests INTEGER NOT NULL,
        llm_calls INTEGER NOT NULL,
        errors TEXT NOT NULL DEFAULT '',
        created_at INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS session_settings (
        session_id TEXT PRIMARY KEY,
        mode TEXT NOT NULL DEFAULT 'off',
        l2 INTEGER NOT NULL DEFAULT 0,
        l3 INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER NOT NULL
      );
    `)
    // Migration: earlier rounds stored a single `mode`; the sticky L2/L3 levels
    // replaced it. Add the level columns to an existing table and backfill once.
    const columns = db.prepare('PRAGMA table_info(session_settings)').all().map((row) => row.name)
    if (!columns.includes('l2')) db.exec('ALTER TABLE session_settings ADD COLUMN l2 INTEGER NOT NULL DEFAULT 0')
    if (!columns.includes('l3')) db.exec('ALTER TABLE session_settings ADD COLUMN l3 INTEGER NOT NULL DEFAULT 0')
    db.exec("UPDATE session_settings SET l2 = 1 WHERE l2 = 0 AND l3 = 0 AND mode = 'session'")
    db.exec("UPDATE session_settings SET l3 = 1 WHERE l2 = 0 AND l3 = 0 AND mode = 'workspace'")
    const recordColumns = db.prepare('PRAGMA table_info(records)').all().map((row) => row.name)
    if (!recordColumns.includes('cold')) db.exec('ALTER TABLE records ADD COLUMN cold INTEGER NOT NULL DEFAULT 0')
    if (!recordColumns.includes('abstract')) db.exec("ALTER TABLE records ADD COLUMN abstract TEXT NOT NULL DEFAULT ''")
    // Migration: older rounds indexed record bodies in FTS. Trigram bodies are
    // the dominant index cost (roughly 13 bytes/token, GBs for a 100M pool), so
    // the index carries card fields plus a bounded cold abstract only. Cold
    // records keep the first ~1k characters of their body in `abstract` so
    // natural-language body terms remain searchable without a full body index.
    const ftsColumns = db.prepare('PRAGMA table_info(records_fts)').all().map((row) => row.name)
    const desiredFts = ['title', 'summary', 'use_when', 'tags', 'abstract']
    const needsRebuild = ftsColumns.includes('body') || desiredFts.some((column) => !ftsColumns.includes(column))
    if (needsRebuild) {
      const hadBody = ftsColumns.includes('body')
      db.exec('DROP TABLE IF EXISTS records_fts')
      db.exec("CREATE VIRTUAL TABLE records_fts USING fts5(title, summary, use_when, tags, abstract, tokenize = 'trigram')")
      const rows = db.prepare('SELECT rowid, title, summary, use_when, tags_json, abstract FROM records').all()
      const insert = db.prepare('INSERT INTO records_fts (rowid, title, summary, use_when, tags, abstract) VALUES (?, ?, ?, ?, ?, ?)')
      for (const row of rows) insert.run(row.rowid, row.title, row.summary, row.use_when, row.tags_json, row.abstract ?? '')
      if (hadBody) {
        // Reclaim the old trigram-body index pages once.
        try {
          db.exec("INSERT INTO records_fts(records_fts) VALUES('optimize')")
          db.exec('PRAGMA wal_checkpoint(TRUNCATE)')
          db.exec('VACUUM')
          db.exec('PRAGMA wal_checkpoint(TRUNCATE)')
        } catch {
          // Maintenance is best-effort; the index is already body-less.
        }
      }
    }
    // Backfill bounded abstracts for cold records that predate the abstract
    // column (or were archived before the write path learned to fill it).
    const missingAbstracts = db.prepare("SELECT id, path FROM records WHERE cold = 1 AND abstract = ''").all()
    for (const row of missingAbstracts) {
      try {
        const abstract = abstractOfBody(recordBodyFromFile(readFileSync(row.path, 'utf8')))
        db.prepare('UPDATE records SET abstract = ? WHERE id = ?').run(abstract, row.id)
        db.prepare('UPDATE records_fts SET abstract = ? WHERE rowid = (SELECT rowid FROM records WHERE id = ?)').run(abstract, row.id)
      } catch {
        // Missing file: card fields remain searchable.
      }
    }
    // v2 term index: card fields + bare numbers are indexed too (cold
    // natural-language anchors). Rebuild once for databases created before v2.
    const termIndexVersion = Number(db.prepare('PRAGMA user_version').get()?.user_version ?? 0)
    if (termIndexVersion < 2) {
      const rows = db.prepare('SELECT id, path, title, summary, use_when, tags_json FROM records').all()
      const insertTerm = db.prepare('INSERT OR IGNORE INTO record_terms (record_id, term_hash) VALUES (?, ?)')
      db.exec('BEGIN IMMEDIATE')
      try {
        db.exec('DELETE FROM record_terms')
        for (const row of rows) {
          const cardText = `${row.title} ${row.summary} ${row.use_when} ${row.tags_json ?? ''}`
          const hashes = new Set(bodyTermHashes(cardText))
          try {
            for (const hash of bodyTermHashes(recordBodyFromFile(readFileSync(row.path, 'utf8')))) hashes.add(hash)
          } catch {
            // Missing file: card terms still get indexed.
          }
          for (const hash of hashes) insertTerm.run(row.id, hash)
        }
        db.exec('PRAGMA user_version = 2')
        db.exec('COMMIT')
      } catch (error) {
        db.exec('ROLLBACK')
        throw error
      }
    }
    // Backfill the body-term index for records whose bodies were written
    // before `record_terms` existed (one-time migration).
    const missingTerms = db.prepare('SELECT id, path FROM records WHERE bytes > 0 AND id NOT IN (SELECT record_id FROM record_terms)').all()
    if (missingTerms.length > 0) {
      const insertTerm = db.prepare('INSERT OR IGNORE INTO record_terms (record_id, term_hash) VALUES (?, ?)')
      db.exec('BEGIN IMMEDIATE')
      try {
        for (const row of missingTerms) {
          try {
            for (const hash of bodyTermHashes(recordBodyFromFile(readFileSync(row.path, 'utf8')))) insertTerm.run(row.id, hash)
          } catch {
            // Missing file: card fields remain searchable; rescue treats it as empty.
          }
        }
        db.exec('COMMIT')
      } catch (error) {
        db.exec('ROLLBACK')
        throw error
      }
    }
    // TTL prune for sticky-level settings rows of long-dead sessions.
    db.prepare('DELETE FROM session_settings WHERE updated_at < ?').run(Date.now() - this.settingsTtlMs)
    this.db = db
    this.ready = true
    return this
  }

  /** Close the database; safe to call more than once. */
  close() {
    if (this.db === undefined) return
    try {
      this.db.close()
    } catch {
      // Closing an already-closed handle is not an error for teardown.
    }
    this.db = undefined
    this.ready = false
  }

  /** @returns {DatabaseSync} The open database. */
  database() {
    return this.ensure().db
  }

  /** Path of one record file. */
  recordPath(workspaceKey, id) {
    return join(this.root, RECORDS_DIR, workspaceKey, `${id}.md`)
  }

  /** Validate and normalize one record input. */
  normalize(input) {
    if (input === null || typeof input !== 'object') throw new TypeError('memory: record must be an object')
    const kind = String(input.kind ?? '')
    if (!MEMORY_KINDS.includes(kind)) throw new TypeError(`memory: unknown record kind "${kind}"`)
    const title = clipText(String(input.title ?? '').trim(), MEMORY_TEXT_LIMITS.title)
    if (title.length === 0) throw new TypeError('memory: record requires a non-empty title')
    const body = String(input.body ?? '')
    if (body.length > MEMORY_TEXT_LIMITS.body) throw new TypeError('memory: record body is too large')
    const status = MEMORY_STATUSES.includes(input.status) ? input.status : 'active'
    const trust = MEMORY_TRUST.includes(input.trust) ? input.trust : 'trusted'
    const scope = MEMORY_SCOPES.includes(input.scope) ? input.scope : 'workspace'
    if (scope === 'session' && (typeof input.sessionId !== 'string' || input.sessionId.length === 0)) {
      throw new TypeError('memory: a session-scoped record requires a non-empty sessionId')
    }
    const workspaceKey = String(input.workspaceKey ?? 'global')
    const now = Date.now()
    return {
      id: typeof input.id === 'string' && input.id.length > 0 ? input.id : `mem_${randomUUID().replace(/-/g, '').slice(0, 10)}`,
      workspaceKey,
      workspace: String(input.workspace ?? ''),
      scope,
      sessionId: String(input.sessionId ?? ''),
      kind,
      title,
      summary: clipText(String(input.summary ?? '').trim(), MEMORY_TEXT_LIMITS.summary),
      useWhen: clipText(String(input.useWhen ?? '').trim(), MEMORY_TEXT_LIMITS.useWhen),
      tags: input.tags !== null && typeof input.tags === 'object' && !Array.isArray(input.tags) ? input.tags : {},
      links: input.links !== null && typeof input.links === 'object' && !Array.isArray(input.links) ? input.links : {},
      provenance: input.provenance !== null && typeof input.provenance === 'object' ? input.provenance : {},
      body,
      tokens: Number.isSafeInteger(input.tokens) && input.tokens > 0 ? input.tokens : estimateTokens(`${title}${body}`),
      trust,
      status,
      createdAt: Number.isSafeInteger(input.createdAt) ? input.createdAt : now,
      updatedAt: now,
    }
  }

  /** Persist one record and its index projection atomically enough for single-process use. */
  write(input) {
    const record = this.normalize(input)
    const file = this.recordPath(record.workspaceKey, record.id)
    mkdirSync(join(this.root, RECORDS_DIR, record.workspaceKey), { recursive: true, mode: 0o700 })
    const text = renderRecordFile(record)
    const tmp = `${file}.${process.pid}.tmp`
    writeFileSync(tmp, text, { mode: 0o600 })
    renameSync(tmp, file)
    const db = this.database()
    const bytes = Buffer.byteLength(text, 'utf8')
    db.exec('BEGIN IMMEDIATE')
    try {
      const existing = db.prepare('SELECT rowid FROM records WHERE id = ?').get(record.id)
      db.prepare(`
        INSERT INTO records (
          id, workspace_key, workspace, scope, session_id, kind, title, summary, use_when,
          tags_json, links_json, provenance_json, path, tokens, bytes, trust, status,
          created_at, updated_at, read_count, last_read_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
        ON CONFLICT(id) DO UPDATE SET
          workspace_key = excluded.workspace_key, workspace = excluded.workspace,
          scope = excluded.scope, session_id = excluded.session_id, kind = excluded.kind,
          title = excluded.title, summary = excluded.summary, use_when = excluded.use_when,
          tags_json = excluded.tags_json, links_json = excluded.links_json,
          provenance_json = excluded.provenance_json, path = excluded.path,
          tokens = excluded.tokens, bytes = excluded.bytes, trust = excluded.trust,
          status = excluded.status, updated_at = excluded.updated_at
      `).run(
        record.id, record.workspaceKey, record.workspace, record.scope, record.sessionId,
        record.kind, record.title, record.summary, record.useWhen,
        safeJson(record.tags), safeJson(record.links), safeJson(record.provenance),
        file, record.tokens, bytes, record.trust, record.status,
        record.createdAt, record.updatedAt,
      )
      const row = db.prepare('SELECT rowid FROM records WHERE id = ?').get(record.id)
      if (existing !== undefined) db.prepare('DELETE FROM records_fts WHERE rowid = ?').run(row.rowid)
      db.prepare('INSERT INTO records_fts (rowid, title, summary, use_when, tags, abstract) VALUES (?, ?, ?, ?, ?, ?)')
        .run(row.rowid, record.title, record.summary, record.useWhen, tagsText(record.tags), '')
      db.prepare('DELETE FROM record_terms WHERE record_id = ?').run(record.id)
      const insertTerm = db.prepare('INSERT OR IGNORE INTO record_terms (record_id, term_hash) VALUES (?, ?)')
      const cardText = `${record.title} ${record.summary} ${record.useWhen} ${tagsText(record.tags)}`
      for (const hash of new Set([...bodyTermHashes(record.body), ...bodyTermHashes(cardText)])) insertTerm.run(record.id, hash)
      db.exec('COMMIT')
    } catch (error) {
      db.exec('ROLLBACK')
      try {
        unlinkSync(file)
      } catch {
        // The index write failed; a leftover file is harmless and reindexable.
      }
      throw error
    }
    return { ...record, path: file }
  }

  /** Read one stored row as a card, without the body. */
  cardFromRow(row) {
    return {
      id: row.id,
      workspaceKey: row.workspace_key,
      kind: row.kind,
      scope: row.scope,
      workspace: row.workspace,
      sessionId: row.session_id,
      title: row.title,
      summary: row.summary,
      useWhen: row.use_when,
      tags: parseJson(row.tags_json),
      links: parseJson(row.links_json),
      provenance: parseJson(row.provenance_json),
      path: row.path,
      tokens: row.tokens,
      bytes: row.bytes,
      trust: row.trust,
      status: row.status,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
      readCount: row.read_count,
      lastReadAt: row.last_read_at ?? undefined,
      cold: Number(row.cold) === 1,
    }
  }

  /** Load one record including its body read from the file. */
  get(id) {
    const row = this.database().prepare('SELECT * FROM records WHERE id = ?').get(id)
    if (row === undefined) return undefined
    const card = this.cardFromRow(row)
    let body = ''
    try {
      body = recordBodyFromFile(readFileSync(row.path, 'utf8'))
    } catch {
      body = card.summary
    }
    return { ...card, body }
  }

  /**
   * Resolve the workspace/visibility filter shared by every query.
   * @param {object} filter - Query filter.
   * @param {{alias?: string}} [options] - Optional table alias prefix (`"r."` for joined SQL).
   * @returns {{clauses: string[], params: unknown[]}} SQL clauses and parameters.
   */
  workspaceClause(filter, options = {}) {
    const alias = options.alias ?? ''
    const col = (name) => `${alias}${name}`
    const clauses = []
    const params = []
    if (filter.workspaceKey !== undefined) {
      clauses.push(`${col('workspace_key')} = ?`)
      params.push(filter.workspaceKey)
    }
    if (filter.kind !== undefined) {
      clauses.push(`${col('kind')} = ?`)
      params.push(filter.kind)
    }
    if (filter.status !== undefined) {
      clauses.push(`${col('status')} = ?`)
      params.push(filter.status)
    }
    if (filter.cold !== undefined) {
      clauses.push(`${col('cold')} = ?`)
      params.push(filter.cold ? 1 : 0)
    }
    if (filter.scopes !== undefined && Array.isArray(filter.scopes)) {
      const scopes = filter.scopes.filter((scope) => MEMORY_SCOPES.includes(scope))
      if (scopes.length > 0 && !scopes.includes('workspace')) {
        clauses.push(`${col('scope')} = ?`)
        params.push('session')
        if (filter.sessionId !== undefined) {
          clauses.push(`${col('session_id')} = ?`)
          params.push(filter.sessionId)
        }
      } else if (scopes.length > 0 && !scopes.includes('session')) {
        clauses.push(`${col('scope')} = ?`)
        params.push('workspace')
      } else if (scopes.length > 0) {
        clauses.push(`(${col('scope')} = 'workspace' OR (${col('scope')} = 'session' AND ${col('session_id')} = ?))`)
        params.push(filter.sessionId ?? '')
      }
    } else {
      if (filter.sessionId !== undefined && (filter.scope === undefined || filter.scope === 'session')) {
        clauses.push(`${col('session_id')} = ?`)
        params.push(filter.sessionId)
      }
      if (filter.scope !== undefined) {
        clauses.push(`${col('scope')} = ?`)
        params.push(filter.scope)
      }
    }
    return { clauses, params }
  }

  /**
   * Ranked search over card fields and bodies.
   *
   * Trigram FTS answers substring queries of three or more code points; shorter
   * terms (common for CJK identifiers and abbreviations like "AI") fall back to
   * a bounded LIKE scan, and a record-body regex scan covers a distinctive
   * identifier that lives only in the archived body. Every path applies the
   * same workspace/kind/status/tag filters, so callers never need to know which
   * one answered.
   */
  search(query) {
    const db = this.database()
    const limit = clampLimit(query.limit, 12)
    // Natural-language queries are decomposed into bounded retrieval terms; the
    // same extractor drives auto-recall so both paths agree.
    const terms = memoryQueryTerms(query.query, query.maxTerms)
    if (terms.length === 0) return { hits: [], total: 0 }
    const lowerTerms = terms.map((term) => term.toLowerCase())
    const anchorTerms = [...new Set([
      ...lowerTerms,
      ...[...String(query.query).matchAll(/\b\d{1,6}\b/g)].map((match) => match[0]),
    ])]
    const keyTerms = anchorTerms.filter((term) => term.length >= 1 && isIdentifierToken(term))
    const { clauses, params } = this.workspaceClause(query, { alias: 'r.' })
    const where = clauses.map((clause) => `AND ${clause}`).join(' ')
    const rowsById = new Map()
    const ftsTerms = terms.filter((term) => Array.from(term).length >= 3).slice(0, 12)
    if (ftsTerms.length > 0) {
      const match = ftsTerms.map((term) => `"${term.replaceAll('"', '""')}"`).join(' OR ')
      const rows = db.prepare(`
        SELECT r.*, snippet(records_fts, 1, '[', ']', '…', 16) AS snippet, bm25(records_fts) AS rank
        FROM records_fts JOIN records r ON r.rowid = records_fts.rowid
        WHERE records_fts MATCH ? ${where}
        ORDER BY rank, r.updated_at DESC LIMIT ?
      `).all(match, ...params, limit * 8)
      for (const row of rows) rowsById.set(row.id, row)
    }
    // LIKE acts as the second retrieval leg for terms FTS trigrams cannot
    // tokenize (short terms and CJK bigrams). For terms of 3+ characters the
    // trigram index already matches substrings, so the LIKE OR-scan is only
    // worth its cost when the FTS leg is sparse.
    const likeTerms = rowsById.size < limit * 2
      ? terms.slice(0, 8)
      // Dense FTS result: skip the expensive OR-scan for ordinary English
      // words (trigram FTS already covers substrings), but keep CJK terms —
      // Chinese has no word boundaries, so LIKE phrase/run evidence still adds
      // recall that the trigram tokenizer cannot reproduce.
      : terms.filter((term) => Array.from(term).length < 3 || /[\u4e00-\u9fff]/.test(term)).slice(0, 8)
    if (likeTerms.length > 0) {
      const like = likeTerms.map(() => '(r.title LIKE ? OR r.summary LIKE ? OR r.use_when LIKE ? OR r.abstract LIKE ?)').join(' OR ')
      const rows = db.prepare(`
        SELECT r.*, '' AS snippet, 0 AS rank FROM records r
        WHERE (${like}) ${where}
        ORDER BY r.updated_at DESC LIMIT ?
      `).all(...likeTerms.flatMap((term) => [`%${term}%`, `%${term}%`, `%${term}%`, `%${term}%`]), ...params, limit * 8)
      for (const row of rows) if (!rowsById.has(row.id)) rowsById.set(row.id, row)
    }
    // Body-only fallback: the FTS/LIKE legs cover card fields and cold
    // abstracts, but a distinctive identifier may live only in a hot body.
    // Hot tier only: cold bodies live on disk and are reached by grep/open.
    if (rowsById.size < limit) {
      const pattern = terms.filter((term) => term.length >= 3).slice(0, 4).map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
      if (pattern.length > 0) {
        const expression = new RegExp(pattern, 'i')
        const candidates = this.list({
          workspaceKey: query.workspaceKey,
          scopes: query.scopes,
          kind: query.kind,
          status: query.status,
          sessionId: query.sessionId,
          includeStatus: query.status !== undefined || query.scope !== undefined || query.scopes !== undefined,
          cold: 0,
          limit: 200,
        })
        for (const card of candidates) {
          if (rowsById.size >= limit * 4) break
          if (rowsById.has(card.id)) continue
          let text
          try {
            text = readFileSync(card.path, 'utf8')
          } catch {
            continue
          }
          const line = text.split('\n').find((entry) => expression.test(entry))
          if (line === undefined) continue
          rowsById.set(card.id, { ...this.rowById(card.id), snippet: clipText(line.trim(), 240), rank: 0 })
        }
      }
    }
    // Body rescue: some query terms never matched any card candidate. Use the
    // exact body-term index to rank candidate bodies by how many query terms
    // they contain, then read only those bodies and add a body-hit score. This
    // is what makes facts that live only in a hot body retrievable without
    // scanning every file.
    if (rowsById.size > 0 && terms.length >= 2) {
      const cardSearchText = (row) => `${row.title} ${row.summary} ${row.use_when} ${row.tags_json} ${row.abstract ?? ''}`.toLowerCase()
      const matchedByCards = new Set()
      for (const row of rowsById.values()) {
        const text = cardSearchText(row)
        for (const term of lowerTerms) if (term.length >= 2 && text.includes(term)) matchedByCards.add(term)
      }
      const unmatched = lowerTerms.filter((term) => term.length >= 2 && !matchedByCards.has(term))
      if (unmatched.length > 0) {
        // Rare-anchor rescue: identifier-like query terms (digits, hyphens,
        // paths) select a small, precise body candidate set. Natural-language
        // queries without such a term skip this cheaply instead of scanning
        // every body-term posting.
        const anchors = lowerTerms
          .filter((term) => term.length >= 2 && /[0-9]/.test(term) || /[-_./:]/.test(term))
          .filter((term, index, all) => all.indexOf(term) === index)
          .slice(0, 3)
          .map((term) => fnv1a32(term))
        if (anchors.length > 0) {
          const placeholders = anchors.map(() => '?').join(', ')
          const { clauses, params } = this.workspaceClause({ workspaceKey: query.workspaceKey, scopes: query.scopes, sessionId: query.sessionId, cold: 0 }, { alias: 'r.' })
          const where = clauses.length > 0 ? `AND ${clauses.join(' AND ')}` : ''
          const candidateRows = this.database().prepare(`
            SELECT t.record_id AS recordId, COUNT(*) AS matches
            FROM record_terms t JOIN records r ON r.id = t.record_id
            WHERE t.term_hash IN (${placeholders}) ${where}
            GROUP BY t.record_id ORDER BY matches DESC LIMIT 120
          `).all(...anchors, ...params)
          let rescued = 0
          for (const candidate of candidateRows) {
            if (rescued >= limit * 5) break
            if (rowsById.has(candidate.recordId)) continue
            const row = this.rowById(candidate.recordId)
            if (row === undefined) continue
            let body = ''
            try {
              body = recordBodyFromFile(readFileSync(row.path, 'utf8'))
            } catch {
              continue
            }
            const lowerBody = body.toLowerCase()
            const bodyHits = lowerTerms.filter((term) => termMatchesText(lowerBody, term)).length
            if (bodyHits === 0) continue
            rowsById.set(candidate.recordId, { ...row, snippet: makeSnippet(body, query.query), rank: undefined, bodyHits })
            rescued += 1
          }
        }
      }
    }
    // Cold-anchor rescue: cold records only expose a bounded abstract, but
    // `record_terms` now indexes card fields and bare numbers too. Use the
    // exact anchors (identifiers / turn numbers) to find cold candidates even
    // when the card legs rank them out of the top limit.
    if (keyTerms.length > 0) {
      const hashes = [...new Set(keyTerms.map((term) => fnv1a32(term)))]
      const placeholders = hashes.map(() => '?').join(', ')
      const { clauses, params } = this.workspaceClause({ workspaceKey: query.workspaceKey, scopes: query.scopes, sessionId: query.sessionId, cold: 1 }, { alias: 'r.' })
      const where = clauses.length > 0 ? `AND ${clauses.join(' AND ')}` : ''
      const coldRows = this.database().prepare(`
        SELECT r.*, '' AS snippet, 0 AS rank, COUNT(*) AS anchorHits
        FROM record_terms t JOIN records r ON r.id = t.record_id
        WHERE t.term_hash IN (${placeholders}) ${where}
        GROUP BY t.record_id ORDER BY anchorHits DESC LIMIT 40
      `).all(...hashes, ...params)
      for (const row of coldRows) {
        if (rowsById.has(row.id)) continue
        rowsById.set(row.id, { ...row, rank: 0 })
      }
    }
    // Hybrid rerank: lexical field matches + body evidence + cold abstract + recency.
    const now = Date.now()
    const fieldHits = (value, weight) => {
      const text = String(value ?? '').toLowerCase()
      if (text.length === 0) return 0
      let hits = 0
      for (const term of lowerTerms) if (text.includes(term)) hits += 1
      return hits * weight
    }
    const ranked = []
    for (const row of rowsById.values()) {
      const card = this.cardFromRow(row)
      const ageDays = Math.max(0, (now - (card.updatedAt ?? now)) / 86_400_000)
      const rankScore = row.rank === 0 || row.rank === undefined ? 0.35 : 1 / (1 + Math.max(0, Number(row.rank)))
      const sweep = { ...DEFAULT_RERANK_WEIGHTS, ...(query.rerank ?? {}) }
      const score = rankScore * sweep.bm25
        + fieldHits(card.title, sweep.title)
        + fieldHits(card.summary, sweep.summary)
        + fieldHits(card.useWhen, sweep.useWhen)
        + fieldHits(tagsText(card.tags), sweep.tags)
        + fieldHits(row.abstract, sweep.abstract)
        + (card.cold === true
          ? keyTerms.filter((term) => termMatchesText(`${row.title} ${row.summary} ${row.use_when} ${row.abstract ?? ''}`.toLowerCase(), term)).length * (sweep.coldAnchor ?? 0)
          : 0)
        + (Number(row.bodyHits) || 0) * sweep.body
        + Math.max(0, 1 - ageDays / 60) * sweep.recency
        - (card.cold === true ? sweep.coldPenalty : 0)
      ranked.push({ card, row, score })
    }
    ranked.sort((left, right) => right.score - left.score || (right.card.updatedAt ?? 0) - (left.card.updatedAt ?? 0))
    if (process.env.DEBUG_RESCUE) console.error('DBG top', ranked.slice(0,8).map(e=>({title:e.card.title, score:+e.score.toFixed(1), body:e.row.bodyHits})))
    const tagFilter = Array.isArray(query.tags) ? query.tags.filter((tag) => typeof tag === 'string' && tag.length > 0) : []
    const hits = []
    for (const { card, row } of ranked) {
      if (tagFilter.length > 0 && !tagFilter.every((tag) => tagsText(card.tags).includes(tag))) continue
      hits.push({
        ...card,
        snippet: row.snippet === '' || row.snippet === null ? makeSnippet(`${card.summary} ${card.title}`, query.query) : row.snippet,
      })
      if (hits.length >= limit) break
    }
    return { hits, total: hits.length }
  }

  /** Load the raw row backing one record id. */
  rowById(id) {
    return this.database().prepare('SELECT * FROM records WHERE id = ?').get(id)
  }

  /** Card-level listing in the requested order. */
  list(filter = {}) {
    const { clauses, params } = this.workspaceClause(filter)
    const limit = clampLimit(filter.limit, 20)
    if (filter.status === undefined && filter.includeStatus === undefined) {
      clauses.push("status != 'superseded'")
    }
    const where = clauses.length > 0 ? `WHERE ${clauses.join(' AND ')}` : ''
    const order = filter.sort === 'oldest' ? 'created_at ASC' : 'updated_at DESC'
    const rows = this.database().prepare(`SELECT * FROM records ${where} ORDER BY ${order} LIMIT ?`).all(...params, limit)
    return rows.map((row) => this.cardFromRow(row))
  }

  /** Literal regex search over stored bodies, with bounded file and line work. */
  grep(request) {
    const pattern = String(request?.pattern ?? '')
    if (pattern.length === 0) throw new Error('memory: grep requires a pattern')
    let expression
    try {
      expression = new RegExp(pattern, 'i')
    } catch (error) {
      throw new Error(`memory: invalid grep pattern: ${error instanceof Error ? error.message : String(error)}`)
    }
    const limit = clampLimit(request.limit, 30)
    const filter = { workspaceKey: request.workspaceKey }
    if (request.scopes !== undefined) filter.scopes = request.scopes
    if (request.scope !== undefined) filter.scope = request.scope
    if (request.sessionId !== undefined) filter.sessionId = request.sessionId
    let rows
    if (request.id === undefined) {
      const { clauses, params } = this.workspaceClause(filter)
      const where = clauses.length > 0 ? `WHERE ${clauses.join(' AND ')}` : ''
      rows = this.database().prepare(`SELECT * FROM records ${where} ORDER BY updated_at DESC LIMIT 400`).all(...params)
    } else {
      rows = this.database().prepare('SELECT * FROM records WHERE id = ?').all(request.id).filter((row) => {
        if (row.workspace_key !== request.workspaceKey) return false
        if (request.scopes !== undefined) {
          if (row.scope === 'workspace') return request.scopes.includes('workspace')
          if (row.scope === 'session') return request.scopes.includes('session') && (request.sessionId === undefined || row.session_id === request.sessionId)
          return false
        }
        if (request.scope !== undefined && row.scope !== request.scope) return false
        if (request.sessionId !== undefined && row.scope === 'session' && row.session_id !== request.sessionId) return false
        return true
      })
    }
    const hits = []
    for (const row of rows) {
      let text
      try {
        text = readFileSync(row.path, 'utf8')
      } catch {
        continue
      }
      const lines = text.split('\n')
      for (let index = 0; index < lines.length; index += 1) {
        if (!expression.test(lines[index])) continue
        hits.push({ id: row.id, title: row.title, line: index + 1, text: clipText(lines[index].trim(), 240) })
        if (hits.length >= limit) return hits
      }
    }
    return hits
  }

  /**
   * Move one record's raw file to the cold tier and exclude it from hot-pool
   * accounting. The record stays searchable/openable by id; only its prompt
   * footprint is released. Idempotent for already-cold records.
   * @param {string} id - Record id.
   * @returns {object|undefined} Updated card, or undefined for an unknown id.
   */
  archiveCold(id) {
    const db = this.database()
    const row = db.prepare('SELECT * FROM records WHERE id = ?').get(id)
    if (row === undefined) return undefined
    if (Number(row.cold) === 1) return this.cardFromRow(row)
    const coldDir = join(this.root, 'cold', row.workspace_key)
    mkdirSync(coldDir, { recursive: true, mode: 0o700 })
    const target = join(coldDir, `${id}.md`)
    let abstract = row.abstract ?? ''
    try {
      abstract = abstractOfBody(recordBodyFromFile(readFileSync(row.path, 'utf8')))
    } catch {
      abstract = row.abstract ?? ''
    }
    try {
      renameSync(row.path, target)
    } catch {
      // A missing source file is tolerable: the record still moves cold and the
      // summary stays readable from the cards table.
      writeFileSync(target, recordBodyFromFile(''), { mode: 0o600 })
    }
    const now = Date.now()
    db.prepare('UPDATE records SET cold = 1, path = ?, updated_at = ?, abstract = ? WHERE id = ?').run(target, now, abstract, id)
    db.prepare('UPDATE records_fts SET abstract = ? WHERE rowid = (SELECT rowid FROM records WHERE id = ?)').run(abstract, id)
    return this.cardFromRow(db.prepare('SELECT * FROM records WHERE id = ?').get(id))
  }

  /**
   * Move a cold record's file back into the hot pool.
   * @param {string} id - Record id.
   * @returns {object|undefined} Updated card, or undefined for an unknown id.
   */
  restoreCold(id) {
    const db = this.database()
    const row = db.prepare('SELECT * FROM records WHERE id = ?').get(id)
    if (row === undefined) return undefined
    if (Number(row.cold) !== 1) return this.cardFromRow(row)
    const hotDir = join(this.root, RECORDS_DIR, row.workspace_key)
    mkdirSync(hotDir, { recursive: true, mode: 0o700 })
    const target = join(hotDir, `${id}.md`)
    try {
      renameSync(row.path, target)
    } catch {
      writeFileSync(target, recordBodyFromFile(''), { mode: 0o600 })
    }
    const now = Date.now()
    db.prepare("UPDATE records SET cold = 0, path = ?, updated_at = ?, abstract = '' WHERE id = ?").run(target, now, id)
    db.prepare("UPDATE records_fts SET abstract = '' WHERE rowid = (SELECT rowid FROM records WHERE id = ?)").run(id)
    return this.cardFromRow(db.prepare('SELECT * FROM records WHERE id = ?').get(id))
  }

  /**
   * Cold-spill the oldest eligible records of one pool until hot usage reaches
   * `targetRatio` of the pool capacity. No LLM is involved.
   * @param {{workspaceKey: string, scope: 'session'|'workspace', sessionId?: string, targetRatio?: number, minAgeMs?: number, limit?: number}} request - Pool and target.
   * @returns {{before: object, targetTokens: number, coldMoved: string[], freedTokens: number}} Report.
   */
  compressCold(request) {
    const scope = MEMORY_SCOPES.includes(request.scope) ? request.scope : 'workspace'
    const filter = {
      workspaceKey: request.workspaceKey,
      scope,
      ...scope === 'session' && request.sessionId !== undefined ? { sessionId: request.sessionId } : {},
    }
    const facets = this.facets(filter)
    const capacity = scope === 'session' ? (facets.sessionCapacityTokens ?? this.sessionCapacityTokens) : facets.capacityTokens
    const hot = Number(facets.hotTokens ?? facets.tokens) || 0
    const targetRatio = Math.min(Math.max(Number(request.targetRatio) || 0.6, 0.01), 0.95)
    const targetTokens = Math.floor(capacity * targetRatio)
    const needed = Math.max(0, hot - targetTokens)
    const report = { before: { hot, capacity, ratio: capacity > 0 ? hot / capacity : 0 }, targetTokens, coldMoved: [], freedTokens: 0 }
    if (needed === 0) return report
    const minAgeMs = Number.isFinite(request.minAgeMs) ? request.minAgeMs : 60 * 60 * 1000
    const cutoff = Date.now() - minAgeMs
    const moveCap = Math.min(Math.max(Number(request.limit) || 2000, 1), 5000)
    // list() clamps to 100 rows, so drain in bounded batches until the target.
    while (report.freedTokens < needed && report.coldMoved.length < moveCap) {
      const batch = this.list({ ...filter, cold: 0, sort: 'oldest', limit: 100 })
        .filter((card) => card.status !== 'pinned' && card.kind !== 'open-thread' && (card.updatedAt ?? 0) < cutoff)
      if (batch.length === 0) break
      let movedInBatch = 0
      for (const card of batch) {
        if (report.freedTokens >= needed || report.coldMoved.length >= moveCap) break
        const updated = this.archiveCold(card.id)
        if (updated === undefined) continue
        report.coldMoved.push(card.id)
        report.freedTokens += card.tokens
        movedInBatch += 1
      }
      if (movedInBatch === 0) break
    }
    return report
  }

  /**
   * Delete cold records/files above a token budget (oldest first).
   * @param {{workspaceKey: string, scope?: 'session'|'workspace', sessionId?: string, keepTokens: number}} request - GC request.
   * @returns {{removed: string[], freedTokens: number}} Report.
   */
  gcCold(request) {
    const keepTokens = Math.max(0, Number(request.keepTokens) || 0)
    const filter = { workspaceKey: request.workspaceKey, cold: 1 }
    if (MEMORY_SCOPES.includes(request.scope)) filter.scope = request.scope
    if (filter.scope === 'session' && request.sessionId !== undefined) filter.sessionId = request.sessionId
    const removed = []
    let freed = 0
    let coldTotal = Number(this.facets(filter).coldTokens) || 0
    const report = { removed, freedTokens: 0 }
    // list() clamps to 100 rows, so drain the oldest cold rows in batches.
    while (coldTotal > keepTokens) {
      const rows = this.list({ ...filter, sort: 'oldest', limit: 100 })
      if (rows.length === 0) break
      for (const card of rows) {
        if (coldTotal <= keepTokens) break
        const path = this.database().prepare('SELECT path FROM records WHERE id = ?').get(card.id)?.path
        try {
          if (path !== undefined) unlinkSync(path)
        } catch {
          // Missing file: the row still goes away.
        }
        this.database().prepare('DELETE FROM records WHERE id = ?').run(card.id)
        removed.push(card.id)
        coldTotal -= card.tokens
        freed += card.tokens
      }
    }
    report.freedTokens = freed
    return report
  }

  /**
   * Record one compression run for observability.
   * @param {{sessionId?: string, level: string, strategy: string, beforeHot: number, afterHot: number, coldMoved: number, digests: number, llmCalls: number, errors?: string[]}} entry - Run summary.
   * @returns {void}
   */
  recordCompression(entry) {
    this.database().prepare(`
      INSERT INTO compression_runs (session_id, level, strategy, before_hot, after_hot, cold_moved, digests, llm_calls, errors, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(entry.sessionId ?? '', entry.level, entry.strategy, entry.beforeHot, entry.afterHot, entry.coldMoved, entry.digests, entry.llmCalls, (entry.errors ?? []).join('; '), Date.now())
  }

  /**
   * Compression history summary for one session (or the whole workspace).
   * @param {string} [sessionId] - Optional session filter.
   * @param {number} [limit] - Recent runs to return.
   * @returns {{count: number, last?: object, recent: object[]}} Summary.
   */
  compressionStats(sessionId, limit = 5) {
    const db = this.database()
    const rows = sessionId === undefined
      ? db.prepare('SELECT * FROM compression_runs ORDER BY created_at DESC LIMIT ?').all(limit)
      : db.prepare('SELECT * FROM compression_runs WHERE session_id = ? ORDER BY created_at DESC LIMIT ?').all(sessionId, limit)
    const total = sessionId === undefined
      ? db.prepare('SELECT COUNT(*) AS count FROM compression_runs').get().count
      : db.prepare('SELECT COUNT(*) AS count FROM compression_runs WHERE session_id = ?').get(sessionId).count
    const recent = rows.map((row) => ({
      level: row.level,
      strategy: row.strategy,
      beforeHot: row.before_hot,
      afterHot: row.after_hot,
      coldMoved: row.cold_moved,
      digests: row.digests,
      llmCalls: row.llm_calls,
      errors: row.errors,
      createdAt: row.created_at,
    }))
    return { count: total, last: recent[0], recent }
  }

  /** Facet counts and capacity accounting for one workspace. */
  facets(filter = {}) {
    const db = this.database()
    const { clauses, params } = this.workspaceClause(filter)
    const where = clauses.length > 0 ? `WHERE ${clauses.join(' AND ')}` : ''
    // One table pass: aggregate by the few dimensions the callers need, then
    // fold the groups in JS. Reading the table 7 times was the hot cost.
    const rows = db.prepare(`
      SELECT kind, status, scope, cold,
        COUNT(*) AS count,
        COALESCE(SUM(tokens), 0) AS tokens,
        COALESCE(SUM(bytes), 0) AS bytes,
        MIN(created_at) AS oldest,
        MAX(updated_at) AS newest
      FROM records ${where}
      GROUP BY kind, status, scope, cold
    `).all(...params)
    let count = 0
    let tokens = 0
    let bytes = 0
    let coldCount = 0
    let coldTokens = 0
    let oldest
    let newest
    const byKind = {}
    const byKindTokens = {}
    const byStatus = {}
    const levels = {}
    for (const row of rows) {
      const rowCount = Number(row.count)
      const rowTokens = Number(row.tokens)
      count += rowCount
      tokens += rowTokens
      bytes += Number(row.bytes)
      if (Number(row.cold) === 1) { coldCount += rowCount; coldTokens += rowTokens }
      byKind[row.kind] = (byKind[row.kind] ?? 0) + rowCount
      byKindTokens[row.kind] = (byKindTokens[row.kind] ?? 0) + rowTokens
      byStatus[row.status] = (byStatus[row.status] ?? 0) + rowCount
      const level = row.scope === 'session' ? 'l2' : 'l3'
      levels[level] = { count: (levels[level]?.count ?? 0) + rowCount, tokens: (levels[level]?.tokens ?? 0) + rowTokens }
      if (oldest === undefined || Number(row.oldest) < oldest) oldest = Number(row.oldest)
      if (newest === undefined || Number(row.newest) > newest) newest = Number(row.newest)
    }
    return {
      count,
      tokens,
      bytes,
      coldCount,
      coldTokens,
      hotCount: count - coldCount,
      hotTokens: Math.max(0, tokens - coldTokens),
      levels,
      capacityTokens: this.capacityTokens,
      sessionCapacityTokens: this.sessionCapacityTokens,
      byKind,
      byKindTokens,
      byStatus,
      oldest,
      newest,
    }
  }

  /**
   * Bounded markdown catalog: pinned records, open threads, recent records and
   * a one-line capacity footer. The caller supplies the budget so the policy
   * layer owns prompt-space allocation.
   */
  catalog(request = {}) {
    const scopes = Array.isArray(request.scopes) && request.scopes.length > 0
      ? request.scopes.filter((scope) => MEMORY_SCOPES.includes(scope))
      : MEMORY_SCOPES.includes(request.scope) ? [request.scope] : undefined
    const filter = {
      workspaceKey: request.workspaceKey,
      cold: 0,
      ...scopes === undefined ? {} : { scopes },
      ...scopes !== undefined && request.sessionId !== undefined ? { sessionId: request.sessionId } : {},
    }
    const capacityTokens = (scopes ?? ['workspace']).reduce((sum, scope) => sum + (scope === 'session' ? this.sessionCapacityTokens : this.capacityTokens), 0)
    const maxChars = Math.max(400, request.maxChars ?? 2400)
    // Scale the catalog depth with the caller's prompt budget instead of always
    // showing a fixed 18 cards: a 2.4k-char default stays as before, larger
    // profile budgets get more pinned/open/recent cards, and the final clip
    // still enforces maxChars.
    const cardBudget = Math.max(8, Math.min(48, Math.floor(maxChars / 160)))
    const pinnedLimit = Math.max(6, Math.min(12, Math.floor(cardBudget * 0.3)))
    const openLimit = Math.max(4, Math.min(8, Math.floor(cardBudget * 0.2)))
    const recentLimit = Math.max(8, Math.min(36, cardBudget - pinnedLimit - openLimit))
    const sections = []
    // Footer accounting is hot+cold: compute it without the cold:0 filter so
    // cold records are still reported; listings above stay hot-only.
    const facets = this.facets({ ...filter, cold: undefined })
    const pinned = this.list({ ...filter, status: 'pinned', limit: pinnedLimit, includeStatus: true })
    const open = this.list({ ...filter, status: 'open', limit: openLimit })
    const recent = this.list({ ...filter, limit: recentLimit })
    const seen = new Set()
    const line = (card) => {
      if (seen.has(card.id)) return ''
      seen.add(card.id)
      const when = clipText(card.useWhen.length > 0 ? card.useWhen : card.summary, 110)
      return `- ${card.id} · ${clipText(card.title, 90)} · ${when}`
    }
    const pushSection = (title, cards) => {
      const lines = cards.map(line).filter((entry) => entry.length > 0)
      if (lines.length > 0) sections.push(`${title}:\n${lines.join('\n')}`)
    }
    pushSection('Pinned', pinned)
    pushSection('Open threads', open)
    pushSection('Recent', recent)
    if (sections.length === 0 && (facets.hotCount ?? 0) + (facets.coldCount ?? 0) === 0) {
      return 'Memory catalog: no archived records in the enabled extra-context levels yet.'
    }
    const header = [
      '## Memory catalog',
      'Earlier context that left the model window is archived here. Search before re-deriving work: `memory_search`, then `memory_open <id>` for the raw archived text. Write durable decisions with `memory_write`.',
      '',
    ].join('\n')
    const levelLabel = (scopes ?? ['workspace']).map((scope) => (scope === 'session' ? 'L2 session-private' : 'L3 workspace-shared')).join(' + ')
    const coldNote = facets.coldCount > 0 ? `, ${facets.coldCount} cold records (${facets.coldTokens} tokens, retrievable via memory_open)` : ''
    const footer = `\nCapacity (hot): ${facets.hotTokens} / ${capacityTokens} tokens across ${facets.hotCount} records${coldNote} (${levelLabel}).`
    let text = `${header}${sections.join('\n\n')}${footer}`
    if (text.length > maxChars) text = `${text.slice(0, maxChars - 40)}\n… (catalog clipped; use memory_search)`
    return text
  }

  /**
   * Read one session's enabled cache levels. Sticky: once a level is on it
   * stays on; sessions without a stored row inherit the deployment default.
   * @param {string} sessionId - Session whose levels are read.
   * @returns {{l2: boolean, l3: boolean}} Enabled levels.
   */
  getLevels(sessionId) {
    const row = this.database().prepare('SELECT l2, l3 FROM session_settings WHERE session_id = ?').get(sessionId)
    if (row !== undefined) return memoryLevelsFromRow(row)
    return { ...this.defaultLevels }
  }

  /**
   * Enable one cache level for a session. Enabling is idempotent and sticky:
   * there is deliberately no way to disable a level once on.
   * @param {string} sessionId - Session whose level turns on.
   * @param {'l2' | 'l3'} level - Level to enable.
   * @returns {{l2: boolean, l3: boolean}} Enabled levels after the change.
   */
  enableLevel(sessionId, level) {
    if (!MEMORY_LEVELS.includes(level)) throw new TypeError(`memory: unknown cache level "${level}"`)
    if (typeof sessionId !== 'string' || sessionId.length === 0) throw new TypeError('memory: session id is required')
    const current = this.getLevels(sessionId)
    const next = { l2: current.l2 || level === 'l2', l3: current.l3 || level === 'l3' }
    this.database().prepare(`
      INSERT INTO session_settings (session_id, mode, l2, l3, updated_at) VALUES (?, 'off', ?, ?, ?)
      ON CONFLICT(session_id) DO UPDATE SET l2 = excluded.l2, l3 = excluded.l3, updated_at = excluded.updated_at
    `).run(sessionId, next.l2 ? 1 : 0, next.l3 ? 1 : 0, Date.now())
    return this.getLevels(sessionId)
  }

  /**
   * Legacy single-mode view over the sticky levels.
   * @param {string} sessionId - Session whose mode is derived.
   * @returns {'off' | 'session' | 'workspace'} Derived mode (L3 wins).
   */
  getMode(sessionId) {
    const levels = this.getLevels(sessionId)
    const scope = memoryCaptureScope(levels)
    if (scope === undefined) return 'off'
    return scope === 'session' ? 'session' : 'workspace'
  }

  /**
   * Legacy mode setter: maps a mode onto sticky levels.
   * @param {string} sessionId - Session whose levels change.
   * @param {'off' | 'session' | 'workspace'} mode - Legacy mode value.
   * @returns {'off' | 'session' | 'workspace'} Derived mode.
   */
  setMode(sessionId, mode) {
    if (!MEMORY_MODES.includes(mode)) throw new TypeError(`memory: unknown extra-context mode "${mode}"`)
    if (mode === 'session') this.enableLevel(sessionId, 'l2')
    if (mode === 'workspace') this.enableLevel(sessionId, 'l3')
    return this.getMode(sessionId)
  }

  /**
   * Record one L1 eviction batch in the audit table.
   * @param {{sessionId: string, start: number, end: number, recordId: string, shadowedTokens: number}} entry - Eviction facts.
   * @returns {void}
   */
  recordEviction(entry) {
    this.database().prepare(`
      INSERT OR REPLACE INTO l1_evictions (session_id, start_seq, end_seq, record_id, shadowed_tokens, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(entry.sessionId, entry.start, entry.end, entry.recordId, entry.shadowedTokens, Date.now())
  }

  /** Aggregate L1 eviction counters. @returns {{count: number, tokens: number}} */
  evictionStats(sessionId) {
    const row = sessionId === undefined
      ? this.database().prepare('SELECT COUNT(*) AS count, COALESCE(SUM(shadowed_tokens), 0) AS tokens FROM l1_evictions').get()
      : this.database().prepare('SELECT COUNT(*) AS count, COALESCE(SUM(shadowed_tokens), 0) AS tokens FROM l1_evictions WHERE session_id = ?').get(sessionId)
    return { count: row?.count ?? 0, tokens: row?.tokens ?? 0 }
  }

  /** Remove one record and its index projection. */
  forget(id) {
    const db = this.database()
    const row = db.prepare('SELECT rowid, path FROM records WHERE id = ?').get(id)
    if (row === undefined) return false
    db.exec('BEGIN IMMEDIATE')
    try {
      db.prepare('DELETE FROM records_fts WHERE rowid = ?').run(row.rowid)
      db.prepare('DELETE FROM records WHERE id = ?').run(id)
      db.exec('COMMIT')
    } catch (error) {
      db.exec('ROLLBACK')
      throw error
    }
    try {
      unlinkSync(row.path)
    } catch {
      // A missing file after the index row is already gone is harmless.
    }
    return true
  }

  /**
   * Update lifecycle status; `pinned` also pins the record in the catalog.
   * Rewrites the record file so the human-readable frontmatter never disagrees
   * with the index (files are documented as the source of truth for content).
   */
  setStatus(id, status) {
    if (!MEMORY_STATUSES.includes(status)) throw new Error(`memory: unknown status "${status}"`)
    const record = this.get(id)
    if (record === undefined) return undefined
    return this.write({ ...record, id, status, createdAt: record.createdAt, body: record.body })
  }

  /** Record read usage for ranking later. */
  markRead(ids) {
    const statement = this.database().prepare('UPDATE records SET read_count = read_count + 1, last_read_at = ? WHERE id = ?')
    const now = Date.now()
    let count = 0
    for (const id of ids) count += Number(statement.run(now, id).changes ?? 0)
    return count
  }

  /** Whether this compaction already has a record. */
  wasArchived(sessionId, compactionId) {
    return this.database().prepare('SELECT record_id FROM archived_compactions WHERE session_id = ? AND compaction_id = ?')
      .get(sessionId, compactionId)?.record_id
  }

  /** Persist an archived compaction and its idempotency marker. */
  archiveRegion(input) {
    const record = this.normalize(input.record)
    const stored = this.write(record)
    this.database().prepare('INSERT OR IGNORE INTO archived_compactions (session_id, compaction_id, record_id, created_at) VALUES (?, ?, ?, ?)')
      .run(input.sessionId, input.compactionId, stored.id, Date.now())
    return stored
  }

  /** No-op hook: SQLite WAL commits synchronously enough for this store. */
  flush() {}
}

/** Escape a term for a regex boundary test. */
function escapeTerm(term) {
  return term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Whether one lowercased query term occurs in a lowercased text.
 *
 * ASCII identifier-ish terms use word boundaries so `inc-1` does not match the
 * prefix of `inc-161` (a real ranking bug for id queries); punctuation/CJK terms
 * keep substring semantics (CJK has no word boundaries, quotes/paths are exact).
 */
export function termMatchesText(text, term) {
  if (text.length === 0 || term.length === 0) return false
  if (/^[a-z0-9][a-z0-9_-]*$/.test(term)) {
    return new RegExp(`(?<![a-z0-9])${escapeTerm(term)}(?![a-z0-9])`).test(text)
  }
  return text.includes(term)
}

/** Build the searchable tag text from a tag facet object. */
export function tagsText(tags) {
  const parts = []
  for (const [key, value] of Object.entries(tags ?? {})) {
    if (Array.isArray(value)) parts.push(key, ...value.map(String))
    else if (typeof value === 'string' || typeof value === 'number') parts.push(key, String(value))
  }
  return parts.join(' ')
}

/** Parse JSON columns tolerantly. */
function parseJson(text) {
  try {
    return JSON.parse(text)
  } catch {
    return {}
  }
}

/**
 * Split a human query into literal terms. Queries are data, never FTS syntax:
 * quoting and boolean operators are treated as text.
 */
function normalizeTerms(query) {
  return String(query ?? '')
    .trim()
    .replace(/\s+/g, ' ')
    .split(' ')
    .map((term) => term.replaceAll('"', ''))
    .filter((term) => term.length > 0)
    .slice(0, 8)
}

/** Escape a literal string for use inside a RegExp. */
function escapeRegExp(text) {
  return String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Clamp a caller limit to a safe range. */
function clampLimit(value, fallback) {
  if (!Number.isSafeInteger(value) || value <= 0) return fallback
  return Math.min(value, 100)
}
