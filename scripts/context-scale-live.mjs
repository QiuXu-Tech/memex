/** Build two nested, token-counted synthetic corpora for read-only live MCP trials. */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { closeSync, mkdirSync, openSync, readFileSync, readdirSync, statSync, writeFileSync, writeSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { performance } from 'node:perf_hooks'
import { createInterface } from 'node:readline'
import { DatabaseSync } from 'node:sqlite'
import { parseArgs } from 'node:util'
import { memoryWorkspaceKey } from '../packages/memex-core/index.js'
import { LocalStoreCore, recordBodyFromFile } from '../packages/memex-core/lib/store.js'

const { values } = parseArgs({ options: {
  out: { type: 'string' },
  python: { type: 'string', default: 'python3' },
  'small-tokens': { type: 'string', default: '10000000' },
  'large-tokens': { type: 'string', default: '100000000' },
} })
const smallTarget = Number(values['small-tokens'])
const largeTarget = Number(values['large-tokens'])
if (!values.out || !Number.isSafeInteger(smallTarget) || !Number.isSafeInteger(largeTarget) || smallTarget < 20_000 || largeTarget < smallTarget + 20_000 || largeTarget > 100_000_000) {
  throw new Error('Usage: node scripts/context-scale-live.mjs --out NEW_DIRECTORY [--python PYTHON] [--small-tokens N --large-tokens N]')
}
const output = resolve(values.out)
const workspace = join(output, 'mcp-workspace')
const otherWorkspace = join(output, 'isolated-workspace')
const workspaceKey = memoryWorkspaceKey(workspace)
const otherWorkspaceKey = memoryWorkspaceKey(otherWorkspace)
const sessionId = 'retention-scale-reader'
const maxDiskBytes = 3 * 1024 ** 3
const archiveCapacity = 110_000_000
const epoch = Date.UTC(2026, 0, 5)
const sha = (text) => createHash('sha256').update(text).digest('hex')
const code = (name) => sha(`memex-context-scale-20261126:${name}`).slice(0, 12).toUpperCase()
const dates = (ordinal) => new Date(epoch + ordinal * 30_000).toISOString()
const putJson = (file, value) => writeFileSync(file, JSON.stringify(value, null, 2) + '\n', { flag: 'wx' })

// The worker refuses to use the network. The published o200k_base SHA-256 is
// validated by tiktoken while loading the pre-populated TIKTOKEN_CACHE_DIR.
const workerCode = String.raw`
import json, sys
import tiktoken
from tiktoken import load

read_asset = load.read_file
def offline_read_asset(path):
    if path.startswith(('http://', 'https://')):
        raise RuntimeError('Prepopulate TIKTOKEN_CACHE_DIR with the official o200k_base asset')
    return read_asset(path)
load.read_file = offline_read_asset
enc = tiktoken.get_encoding('o200k_base')
assert enc.encode_ordinary('Hello, world!') == [13225, 11, 2375, 0]
print(json.dumps(dict(name=enc.name, library='tiktoken', version=tiktoken.__version__)), flush=True)
for line in sys.stdin:
    bodies = json.loads(line)
    print(json.dumps([len(enc.encode_ordinary(body)) for body in bodies]), flush=True)
`

function directoryUsage(directory) {
  let logicalBytes = 0
  let allocatedBytes = 0
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) {
      const usage = directoryUsage(path)
      logicalBytes += usage.logicalBytes
      allocatedBytes += usage.allocatedBytes
    } else {
      const stat = statSync(path)
      logicalBytes += stat.size
      allocatedBytes += 512 * stat.blocks
    }
  }
  return { logicalBytes, allocatedBytes }
}

const projectNames = ['alder', 'anvil', 'beacon', 'birch', 'cedar', 'cinder', 'cobalt', 'delta', 'elm', 'ember', 'garnet', 'harbor', 'iris', 'juniper', 'keel', 'linden', 'maple', 'orchid', 'pine', 'quartz', 'raven', 'reed', 'sable', 'spruce', 'willow', 'yarrow']
const systems = ['replication worker', 'asset compiler', 'search index', 'schema importer', 'billing emulator', 'image queue', 'calendar bridge', 'release coordinator', 'manual export', 'inventory scanner', 'snapshot adapter', 'report generator']
const symptoms = ['returned partial pages', 'discarded the latest revision', 'held the same lease after restart', 'selected a stale materialized row', 'reported success before readback', 'hid discrepancies after a retry', 'filled its work queue without draining it', 'used a default scope for a shared key', 'missed a quiet partition', 'showed green while the sample disagreed', 'skipped a duplicate trace', 'repeated its first page']
const checks = ['compare receipts at the caller boundary', 'read the raw event before reloading the derived view', 'replay the original input with the same scope', 'sample a separate partition after the queue settles', 'review the incident transcript with the operator', 'compare a clean start to a warm restart', 'check the control run on the same image', 'recount distinct objects from the source manifest', 'open the original record after the checkpoint']
const decisions = ['stage a reversible change in one region', 'hold the rollout until an independent receipt arrives', 'keep both competing explanations in the incident', 'elect a new lease holder at the next checkpoint', 'split the report by workload profile', 'record the observed timing with its uncertainty', 'remove the provisional number from the weekly summary', 'repeat the sample with the fallback enabled', 'mark the round incomplete and retain the first failure']
const contexts = ['on-call shift', 'manual evidence review', 'migration rehearsal', 'release readiness call', 'work queue handoff', 'quality review', 'cohort comparison', 'change-control meeting', 'instance rotation', 'weekly service audit', 'acceptance walk-through', 'rollback drill']
const commonTerms = ['Fern Lantern continuity ledger', 'Alder Circuit export contract', 'Sable Orchard checkpoint register', 'Indigo Lantern maintenance waiver']

function syntheticNote(ordinal) {
  let state = (Math.imul(ordinal, 2654435761) ^ 0xC14908B1) >>> 0
  const next = (modulus) => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0
    return (state >>> 8) % modulus
  }
  const pick = (items) => items[next(items.length)]
  const project = pick(projectNames)
  const system = pick(systems)
  const context = pick(contexts)
  const reference = `${project}-${ordinal}`
  const common = ordinal % 4 === 0 ? pick(commonTerms) : ''
  const paragraphs = [
    `# ${project} ${system} — ${context}\n\n${dates(ordinal)} • Engineering notebook ${reference}. This entry covers the ${context} for the ${system}.`,
  ]
  if (common) paragraphs.push(`Reference desk: ${common}. The reviewer asked us to cross-check their terminology against this local record. Results here apply to ${reference}.`)
  const sections = 70 + next(80)
  for (let index = 0; index < sections; index += 1) {
    const area = pick(projectNames)
    const component = pick(systems)
    const measure = 40 + next(960)
    const elapsed = 15 + next(2400)
    const observed = pick(symptoms)
    const check = pick(checks)
    const decision = pick(decisions)
    const slot = 1 + next(20)
    const mode = ['shadow', 'warm', 'clean', 'canary', 'rehearsal'][next(5)]
    const formats = [
      `In ${area}, the ${component} ${observed} during the ${mode} run. The follow-up is to ${check}. The recorder counted ${measure} items before the work queue was paused. The group agreed to ${decision}.`,
      `> ${area} operator: “Please ${check}. The ${component} ${observed} on slot ${slot}.”\n\nThe reviewer answered after ${elapsed} ms of client timing. Resolution: ${decision}.`,
      `| ${area} | slot ${slot} | ${component} | ${elapsed} ms | ${measure} checked |\n\nObservation: the worker ${observed}. Acceptance requires the owner to ${check}; the current disposition is to ${decision}.`,
      `~~~json\n${JSON.stringify({ project: area, slot, component, elapsed_ms: elapsed, checked: measure, profile: mode, observation: observed })}\n~~~\n\nFollow-up in the review ledger: ${check}. ${decision[0].toUpperCase() + decision.slice(1)}.`,
      `- Sample ${slot} for ${area}: ${component}; profile ${mode}.\n- Observation: ${observed} after ${elapsed} ms and ${measure} inspected objects.\n- Next check: ${check}.\n- Disposition: ${decision}.`,
      `A reviewer expected the ${component} to produce a new receipt once ${measure} objects had settled. During ${area}'s ${mode} run, it ${observed}. We decided to ${decision} and asked the next shift to ${check}.`,
    ]
    paragraphs.push(formats[next(formats.length)])
  }
  return {
    id: `scale-note-${ordinal}`,
    kind: ['episode', 'incident', 'artifact', 'procedure'][next(4)],
    title: `${project} ${system} ${context} ${reference}`,
    summary: `${common ? `${common}. Related local review only. ` : ''}Notes about the ${system} during the ${context} for ${reference}.`,
    useWhen: `Investigating ${project} ${system} behavior or reading the ${reference} notes.`,
    body: paragraphs.join('\n\n'),
    ordinal,
    cold: ordinal % 5 < 3,
  }
}

function evidenceNote({ id, title, body, ordinal, version, source, cold = false, status = 'active', namespace = 'workspace' }) {
  return { id, title, body, ordinal, cold, status, namespace, kind: 'decision', summary: title, useWhen: `Review the signed decision for ${title}.`, source, version }
}

const fernSource = 'synthetic://retention/fern-lantern/continuity-ledger'
const alderSource = 'synthetic://retention/alder-circuit/export-contract'
const sableSource = 'synthetic://retention/sable-orchard/checkpoint-register'
const nearSource = 'synthetic://retention/heliotrope-pier/late-checkpoint'
const fern = evidenceNote({ id: 'scale-fern-final', title: 'Fern Lantern continuity ledger – signed recovery convention', ordinal: 2, source: fernSource, version: 'rev-3', cold: true,
  body: `Final witness entry for Fern Lantern continuity. The signed recovery convention uses seal ${code('fern')}. The seal was transcribed from the replacement audit book after the test controller reloaded the original handoff. This entry applies to the project ledger, independent of the separate external review.` })
const alderOld = evidenceNote({ id: 'scale-alder-retired', title: 'Alder Circuit export contract – original allowance', ordinal: 3, source: alderSource, version: 'rev-1', cold: true, status: 'superseded',
  body: `The historical Alder Circuit export allowance used receipt ${code('alder-old')} and a twelve-minute hold. This decision was withdrawn when the second readback exposed duplicate export acknowledgments. See the later signed contract for the active instruction.` })
const alder = evidenceNote({ id: 'scale-alder-current', title: 'Alder Circuit export contract – current signed allowance', ordinal: 4, source: alderSource, version: 'rev-2',
  body: `Alder Circuit's current signed export allowance uses receipt ${code('alder')} and a seven-minute hold. The revised contract supersedes revision one. During a partial export, hold publication until an independent receipt confirms the complete object count.` })
const namespaceDecoys = [
  evidenceNote({ id: 'scale-fern-foreign', title: fern.title, ordinal: 5, source: fernSource, version: 'rev-4', namespace: 'other-workspace', cold: true,
    body: `Different checkout's Fern Lantern record. Its project seat uses seal ${code('fern-foreign')} under an independent agreement.` }),
  evidenceNote({ id: 'scale-indigo-private', title: 'Indigo Lantern maintenance waiver – signed copy', ordinal: 6, namespace: 'other-session', source: 'synthetic://retention/indigo-lantern/private-waiver', version: 'rev-6',
    body: `Private review seat approval for Indigo Lantern. Recorded authorization ${code('indigo-private')}. It applies only to the reviewing session.` }),
]

function sableNote(ordinal) {
  return evidenceNote({ id: 'scale-sable-checkpoint', title: 'Sable Orchard checkpoint register – reviewer handoff', ordinal, namespace: 'current-session', source: sableSource, version: 'rev-5',
    body: `Sable Orchard checkpoint handoff. The latest reviewer signed verification stamp ${code('sable')} after matching the two independent manifests. That stamp is attached to the readback step. Earlier sample notes are discussion copies.` })
}

function nearNote(ordinal) {
  return evidenceNote({ id: 'scale-heliotrope-checkpoint', title: 'Heliotrope Pier intake checkpoint – final witness ticket', ordinal, source: nearSource, version: 'rev-8',
    body: `Late intake checkpoint for Heliotrope Pier. The final witness ticket is ${code('heliotrope')}. The archive operator entered it after the final reconciliation of intake receipts.` })
}

const prompt = `Use the Memex tools for the configured archive only. Find and open the cited records before answering. The archive contains engineering notes, common terminology, several revisions and some unavailable items. Use the latest applicable evidence when asked for a current value. Output one JSON object, with the keys below, and evidence record IDs for each located value. Use the string NOT_FOUND for an item absent from your visible evidence. Do not make changes.\n\n`
  + `fern: Fern Lantern continuity ledger's signed recovery seal.\n`
  + `alder: Alder Circuit's current signed export receipt and hold length in minutes.\n`
  + `sable: Sable Orchard checkpoint register's latest reviewer verification stamp.\n`
  + `indigo: Indigo Lantern's signed maintenance waiver authorization, if available.\n`
  + `heliotrope: Heliotrope Pier intake checkpoint's final witness ticket.\n`
  + `marigold: Marigold Narrows post-recovery confirmation signature.\n`

function answerKey(extended) {
  return {
    fern: { value: code('fern'), evidence: [fern.id], control: 'early/cold; same title and higher version in another workspace', wrongValues: [code('fern-foreign')] },
    alder: { value: code('alder'), holdMinutes: 7, evidence: [alder.id], control: 'current version supersedes early/cold revision', wrongValues: [code('alder-old')] },
    sable: { value: code('sable'), evidence: ['scale-sable-checkpoint'], control: 'near end of 10M and visible only in the configured current session' },
    indigo: { value: 'NOT_FOUND', evidence: [], control: 'present solely in another session', wrongValues: [code('indigo-private')] },
    heliotrope: extended ? { value: code('heliotrope'), evidence: ['scale-heliotrope-checkpoint'], control: 'near end of 100M, present only in large archive' } : { value: 'NOT_FOUND', evidence: [], control: 'large-only' },
    marigold: { value: 'NOT_FOUND', evidence: [], control: 'absent from all tiers and namespaces' },
  }
}

function storeInput(note, tokens) {
  const { namespace = 'workspace', ordinal } = note
  const scope = namespace.endsWith('session') ? 'session' : 'workspace'
  return {
    id: note.id, kind: note.kind, title: note.title, summary: note.summary, useWhen: note.useWhen,
    body: note.body, tokens, status: note.status, createdAt: Date.parse(dates(ordinal)),
    workspaceKey: namespace === 'other-workspace' ? otherWorkspaceKey : workspaceKey,
    workspace: namespace === 'other-workspace' ? otherWorkspace : workspace,
    scope, sessionId: namespace === 'current-session' ? sessionId : scope === 'session' ? 'retention-scale-isolated' : '',
    provenance: { source: 'synthetic-context-scale', evidence: { source: note.source ?? `synthetic://retention/notebook/${ordinal}`, version: note.version ?? 'rev-1', observedAt: dates(ordinal) } },
  }
}

function visible(row) {
  return row.workspace_key === workspaceKey && (row.scope === 'workspace' || row.session_id === sessionId)
}

function inspectArchive(root, ledger, expected) {
  const index = new DatabaseSync(join(root, 'index.db'), { readOnly: true })
  const bodies = new Set()
  const totals = { visibleRecords: 0, visibleTokens: 0, visibleBodyBytes: 0, hot: 0, cold: 0, visibleHot: 0, visibleCold: 0, namespaces: {} }
  const receipt = createHash('sha256')
  const rows = []
  try {
    for (const row of index.prepare('SELECT * FROM records ORDER BY rowid').iterate()) {
      const body = recordBodyFromFile(readFileSync(row.path, 'utf8'))
      const digest = sha(body)
      const registered = ledger.get(row.id)
      assert.deepEqual({ digest, tokens: row.tokens }, registered, row.id)
      assert(!bodies.has(digest), `Duplicate body: ${row.id}`)
      bodies.add(digest)
      receipt.update(`${row.id} ${row.tokens} ${digest} ${row.cold} ${row.status}\n`)
      const area = `${row.workspace_key}/${row.scope}/${row.session_id || '-'}`
      totals.namespaces[area] ??= { records: 0, tokens: 0 }
      totals.namespaces[area].records += 1
      totals.namespaces[area].tokens += row.tokens
      totals[row.cold ? 'cold' : 'hot'] += 1
      if (visible(row)) {
        totals.visibleRecords += 1
        totals.visibleTokens += row.tokens
        totals.visibleBodyBytes += Buffer.byteLength(body)
        totals[row.cold ? 'visibleCold' : 'visibleHot'] += 1
      }
      rows.push({ row, digest })
    }
  } finally {
    index.close()
  }
  assert.equal(rows.length, ledger.size)
  assert.equal(totals.visibleTokens, expected)
  return { totals, rows, datasetSha256: receipt.digest('hex') }
}

function copyStorePrefix(store, prefix, persist) {
  for (const { row } of prefix.rows) {
    const body = recordBodyFromFile(readFileSync(row.path, 'utf8'))
    persist(store, {
      id: row.id, kind: row.kind, title: row.title, summary: row.summary, useWhen: row.use_when,
      body, tokens: row.tokens, status: row.status, createdAt: row.created_at,
      workspaceKey: row.workspace_key, workspace: row.workspace, scope: row.scope, sessionId: row.session_id,
      provenance: JSON.parse(row.provenance_json),
    }, row.cold === 1)
  }
}

function archiveLabel(target) {
  return target % 1_000_000 === 0 ? `${target / 1_000_000}m` : String(target)
}

function checkDisk() {
  const usage = directoryUsage(output)
  assert(Math.max(usage.logicalBytes, usage.allocatedBytes) < maxDiskBytes, `Disk limit reached: ${JSON.stringify(usage)}`)
  return usage
}

async function buildArchive(target, tokenizer, prefix) {
  const dir = join(output, archiveLabel(target))
  const root = join(dir, 'store')
  mkdirSync(dir)
  mkdirSync(root)
  const store = new LocalStoreCore({ root, capacityTokens: archiveCapacity, sessionCapacityTokens: archiveCapacity, defaultLevels: { l2: false, l3: false } })
  const ledger = new Map()
  const start = performance.now()
  const extended = prefix !== undefined
  let observed = 0
  let ordinal = prefix?.nextOrdinal ?? 10
  let tokenizerMs = 0
  let writeMs = 0
  let coldMs = 0

  const persist = (destination, input, cold) => {
    let operation = performance.now()
    const card = destination.write(input)
    writeMs += performance.now() - operation
    if (cold) {
      operation = performance.now()
      assert.equal(destination.archiveCold(card.id)?.cold, true, `Cold move failed for ${card.id}`)
      coldMs += performance.now() - operation
    }
    assert(!ledger.has(card.id))
    ledger.set(card.id, { digest: sha(input.body), tokens: input.tokens })
    if (visible({ workspace_key: input.workspaceKey, scope: input.scope, session_id: input.sessionId })) observed += input.tokens
  }

  async function encode(notes) {
    const operation = performance.now()
    const counts = await tokenizer.count(notes.map((note) => note.body))
    tokenizerMs += performance.now() - operation
    assert.equal(counts.length, notes.length)
    for (const [index, note] of notes.entries()) persist(store, storeInput(note, counts[index]), note.cold)
  }

  try {
    if (extended) {
      copyStorePrefix(store, prefix, persist)
      checkDisk()
    }
    else await encode([fern, alderOld, alder, ...namespaceDecoys])
    const near = extended ? nearNote : sableNote
    let nextProgress = observed + 2_000_000
    while (observed < target) {
      const count = Math.min(20, Math.max(1, Math.floor((target - observed) / 8500)))
      const batch = Array.from({ length: count }, () => syntheticNote(ordinal++))
      await encode(batch)
      if (observed >= nextProgress) {
        checkDisk()
        console.log(JSON.stringify({ event: 'progress', target, visibleTokens: observed, records: ledger.size, elapsedMs: Math.round(performance.now() - start) }))
        nextProgress += 2_000_000
      }
    }
    await encode([near(ordinal++)])
  } finally {
    store.close()
  }
  const buildMs = performance.now() - start
  const verified = inspectArchive(root, ledger, observed)
  if (extended) {
    const preceding = verified.rows.slice(0, prefix.rows.length)
    for (const [index, { row, digest }] of preceding.entries()) {
      const small = prefix.rows[index]
      assert.deepEqual([row.id, digest, row.tokens, row.cold, row.status], [small.row.id, small.digest, small.row.tokens, small.row.cold, small.row.status])
    }
  }
  const archiveUsage = directoryUsage(dir)
  const totalUsage = checkDisk()
  const manifest = {
    type: 'synthetic-engineering-archive', targetVisibleTokens: target, nominalSize: archiveLabel(target),
    tokenizer: { ...tokenizer.meta, vocabularySha256: '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d', countedUnit: 'independently encoded persisted record body; excludes frontmatter and inaccessible namespaces' },
    root, workspace, workspaceKey, sessionId, archiveCapacity,
    datasetSha256: verified.datasetSha256, exactPrefixOf: extended ? undefined : archiveLabel(largeTarget),
    prefixVerified: extended ? { documents: prefix.rows.length, sha256: prefix.datasetSha256 } : undefined,
    verifiedUniqueBodies: verified.rows.length, ...verified.totals,
    archiveUsage, totalUsage, maxDiskBytes,
    buildMs, tokenizerMs, writeMs, coldMs, readbackMs: performance.now() - start - buildMs,
    node: process.version, platform: process.platform, architecture: process.arch,
    ordinaryRecords: 'Deterministically generated, mixed engineering notes with distinct bodies and repeated realistic vocabulary. All data is synthetic.',
  }
  writeFileSync(join(dir, 'prompt.txt'), prompt, { flag: 'wx' })
  putJson(join(dir, 'key.json'), answerKey(extended))
  putJson(join(dir, 'manifest.json'), manifest)
  const index = openSync(join(dir, 'bodies.jsonl'), 'wx')
  try {
    for (const { row, digest } of verified.rows) {
      writeSync(index, JSON.stringify({ id: row.id, tokens: row.tokens, sha256: digest, visible: visible(row), cold: row.cold === 1, status: row.status }) + '\n')
    }
  } finally {
    closeSync(index)
  }
  console.log(JSON.stringify({ event: 'ready', ...manifest }))
  return { ...verified, nextOrdinal: ordinal }
}

mkdirSync(output, { recursive: true })
mkdirSync(workspace)
const worker = spawn(values.python, ['-u', '-c', workerCode], { stdio: ['pipe', 'pipe', 'inherit'] })
const workerDone = new Promise((resolve, reject) => {
  worker.on('error', reject)
  worker.on('exit', resolve)
})
const answers = createInterface({ input: worker.stdout })[Symbol.asyncIterator]()
async function reply() {
  const answer = await answers.next()
  if (answer.done) throw new Error(`Tokenizer produced no response (exit ${await workerDone})`)
  return JSON.parse(answer.value)
}
try {
  const tokenizer = {
    meta: await reply(),
    async count(bodies) {
      await new Promise((resolve, reject) => worker.stdin.write(JSON.stringify(bodies) + '\n', (error) => error ? reject(error) : resolve()))
      return reply()
    },
  }
  const small = await buildArchive(smallTarget, tokenizer)
  await buildArchive(largeTarget, tokenizer, small)
} finally {
  worker.stdin.end()
  assert.equal(await workerDone, 0, 'Tokenizer worker failed')
}
