#!/usr/bin/env node
/** Persistent controller-only evidence helper for arbitrary bound public tasks.
 * One real Memex archive/epoch survives prime and every paired C/D verification.
 * Original opens require a fresh external controller admission. No providers,
 * credentials, evaluator labels, task answers or native-host claims live here.
 */
import { createHash, randomUUID } from 'node:crypto'
import { closeSync, constants, existsSync, fsyncSync, fstatSync, lstatSync, mkdirSync,
  openSync, readSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { TextDecoder } from 'node:util'
import { EvidenceArchive } from './archive.mjs'
import { extractClaims, EXTRACTION_INSTRUCTIONS, EXTRACTION_POLICY } from './claims.mjs'
import { digest, POLICY_VERSION, verifyEvidence } from './verification.mjs'

const sha = value => createHash('sha256').update(value).digest('hex')
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const label = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/.test(value)
const fields = (value, required, optional = []) => plain(value) && required.every(k => Object.hasOwn(value, k))
  && Object.keys(value).every(k => required.includes(k) || optional.includes(k))
const jsonBytes = value => Buffer.from(JSON.stringify(value), 'utf8')
const SOURCE_FIELDS = new Set(('eventId sourceId sourceSequence observedAt role type scope entity text kind status complete command '
  + 'completed executed exitCode version authoritative actor action effectiveAt expiresAt testCount skippedCount todoCount '
  + 'parserVersion validFrom validUntil revokedAt grantedAt value target targetVersion repository artifact sessionId '
  + 'threadId itemId sourceRef sourceDigest sha256 recordId eventIndex transport').split(' '))
const FORBIDDEN = new Set(('gold golden goldsource goldanswer goldenanswer claims claim expected expectedsource expectedsources '
  + 'expectedanswer expectedsourceid correctsource correctanswer answerkey answer groundtruth oracle oraclesource labels label '
  + 'scoring scoringannotation evaluator private apikey password secret').split(' '))

export class EvidenceHelperError extends Error {}
function fail(code) { throw new EvidenceHelperError(code) }
function safeError(error) { return error instanceof EvidenceHelperError ? error.message : 'evidence_operation_failed' }
function decode(bytes) {
  try { return new TextDecoder('utf-8', { fatal: true }).decode(bytes) } catch { fail('invalid_utf8') }
}
function parse(bytes) {
  try { return JSON.parse(decode(bytes)) } catch (error) {
    if (error instanceof EvidenceHelperError) throw error
    fail('invalid_json')
  }
}
function path(value) {
  if (typeof value !== 'string' || !value || value.includes('\0')) fail('invalid_path')
  const target = resolve(value)
  for (let current = target; ; current = dirname(current)) {
    try { if (lstatSync(current).isSymbolicLink()) fail('symlink_path_forbidden') }
    catch (error) { if (error.code !== 'ENOENT') throw error }
    if (current === dirname(current)) break
  }
  return target
}
function readBounded(file, limit) {
  const target = path(file)
  let fd
  try {
    fd = openSync(target, constants.O_RDONLY | constants.O_NOFOLLOW)
    const before = fstatSync(fd)
    if (!before.isFile() || before.size > limit) fail('input_file_byte_budget')
    const buffer = Buffer.alloc(limit + 1)
    let length = 0
    while (length < buffer.length) {
      const n = readSync(fd, buffer, length, buffer.length - length, null)
      if (!n) break
      length += n
    }
    const after = fstatSync(fd)
    if (length > limit) fail('input_file_byte_budget')
    if (before.size !== after.size || before.mtimeMs !== after.mtimeMs || before.ino !== after.ino || length !== after.size)
      fail('input_file_changed')
    return buffer.subarray(0, length)
  } catch (error) {
    if (error instanceof EvidenceHelperError) throw error
    fail('input_file_unavailable')
  } finally { if (fd !== undefined) closeSync(fd) }
}
function rejectSupervision(value) {
  if (Array.isArray(value)) { value.forEach(rejectSupervision); return }
  if (!plain(value)) return
  for (const [key, item] of Object.entries(value)) {
    if (FORBIDDEN.has(key.toLowerCase().replace(/[^a-z0-9]/g, ''))) fail('supervision_metadata_forbidden')
    rejectSupervision(item)
  }
}
function timestamp(value) {
  if (typeof value !== 'string' || !/(?:Z|[+-][0-9]{2}:[0-9]{2})$/.test(value) || !Number.isFinite(Date.parse(value)))
    fail('invalid_snapshot_time')
  return Date.parse(value)
}
function validateArchive(value, taskId) {
  rejectSupervision(value)
  if (!fields(value, ['schema', 'taskId', 'snapshot', 'sources']) || value.schema !== 1) fail('invalid_public_archive')
  if (value.taskId !== taskId) fail('archive_task_mismatch')
  if (!fields(value.snapshot, ['cutoff', 'watermark', 'complete']) || value.snapshot.complete !== true
      || typeof value.snapshot.watermark !== 'string' || !value.snapshot.watermark.trim()) fail('incomplete_public_snapshot')
  const cutoff = timestamp(value.snapshot.cutoff)
  if (!Array.isArray(value.sources) || !value.sources.length || value.sources.length > 1000) fail('invalid_public_sources')
  const ids = new Set()
  for (const source of value.sources) {
    if (!plain(source) || Object.keys(source).some(k => !SOURCE_FIELDS.has(k))
        || !['eventId', 'sourceId', 'observedAt', 'role', 'type', 'scope', 'entity', 'text']
          .every(k => typeof source[k] === 'string' && source[k].trim())
        || !['system', 'developer', 'user', 'assistant', 'tool'].includes(source.role)
        || !Number.isSafeInteger(source.sourceSequence) || source.sourceSequence < 1
        || Buffer.byteLength(source.text) > 240000 || ids.has(source.eventId)
        || source.transport !== undefined && !plain(source.transport)) fail('invalid_public_source')
    if (timestamp(source.observedAt) > cutoff) fail('source_after_snapshot_cutoff')
    ids.add(source.eventId)
  }
  return value
}
function validateLimits(limits, prime) {
  if (!fields(limits, ['maxSourceOpens', 'maxSourceBytes', 'maxSourceBytesPerOpen'])
      || !Number.isSafeInteger(limits.maxSourceOpens) || limits.maxSourceOpens < 0 || limits.maxSourceOpens > (prime ? 6 : 32)
      || !Number.isSafeInteger(limits.maxSourceBytes) || limits.maxSourceBytes < 0 || limits.maxSourceBytes > 96000
      || !Number.isSafeInteger(limits.maxSourceBytesPerOpen) || limits.maxSourceBytesPerOpen < 1 || limits.maxSourceBytesPerOpen > 4000)
    fail('invalid_source_open_limits')
  return structuredClone(limits)
}

export class PairedEvidence {
  #primeCache = new Map()
  #sourceMetadata = new Map()
  #units = new Set()
  constructor(config, { authorizeOpen } = {}) {
    if (!fields(config, ['schema_version', 'archivePath', 'archiveSha256', 'requestPath', 'requestSha256', 'taskId', 'output', 'publicInput'])
        || config.schema_version !== 1 || !hash(config.archiveSha256) || !hash(config.requestSha256) || !label(config.taskId))
      fail('invalid_evidence_configuration')
    if (!fields(config.publicInput, ['draft', 'context', 'toolDescriptions'])
        || !['draft', 'context'].every(k => typeof config.publicInput[k] === 'string')
        || !Array.isArray(config.publicInput.toolDescriptions) || config.publicInput.toolDescriptions.length > 128
        || config.publicInput.toolDescriptions.some(v => typeof v !== 'string') || jsonBytes(config.publicInput).length > 262144)
      fail('observable_input_required')
    if (typeof authorizeOpen !== 'function') fail('source_open_admission_callback_required')
    this.config = structuredClone(config)
    this.authorizeOpen = authorizeOpen
    this.output = path(config.output)
    this.config.archivePath = path(config.archivePath)
    this.config.requestPath = path(config.requestPath)
    if ([this.config.archivePath, this.config.requestPath].some(file => {
      const rel = relative(this.output, file)
      return rel === '' || !rel.startsWith('..')
    })) fail('source_output_overlap')
    if (existsSync(this.output)) fail('fresh_evidence_state_required')
    const archiveBytes = readBounded(this.config.archivePath, 1048576)
    const requestBytes = readBounded(this.config.requestPath, 16384)
    if (sha(archiveBytes) !== config.archiveSha256) fail('archive_digest_mismatch')
    if (sha(requestBytes) !== config.requestSha256) fail('request_digest_mismatch')
    const data = validateArchive(parse(archiveBytes), config.taskId)
    const request = decode(requestBytes)
    if (!request.trim()) fail('original_request_required')
    this.input = { request, ...structuredClone(config.publicInput) }
    this.cutoff = data.snapshot.cutoff
    this.prepared = false
    this.extraction = null
    this.primed = false
    this.closed = false
    this.busy = false
    this.opening = null
    this.traceRefs = []
    this.sequence = 0
    this.verifySequence = 0
    mkdirSync(this.output, { recursive: true, mode: 0o700 })
    this.archive = new EvidenceArchive({ root: join(this.output, 'memex-l2'), cwd: this.output,
      sessionId: 'paired-' + digest(config.taskId).slice(0, 24), pageChars: 4000, maxSourceBytes: 4000 })
    try {
      this.archive.ingest(data.sources)
      this.archive.setSynchronized(true)
      for (const source of data.sources) this.#sourceMetadata.set(source.eventId,
        { bytes: jsonBytes(source).length, digest: digest(source) })
      const actualOpen = this.archive.engine.openEvent.bind(this.archive.engine)
      this.archive.engine.openEvent = (...args) => {
        const active = this.opening
        if (!active || active.pages !== 0) fail('original_open_requires_single_admitted_page')
        const page = actualOpen(...args)
        active.pages++
        active.counts.source_open_pages++
        if (page && typeof page.content === 'string') {
          const bytes = Buffer.byteLength(page.content)
          active.actualBytes += bytes
          active.counts.source_open_bytes += bytes
          if (bytes > active.upper || bytes > 4000 || page.nextCharOffset !== null && page.nextCharOffset !== undefined)
            fail('original_exceeded_admitted_byte_bound')
        }
        return page
      }
      this.record('bound-source-archive.json', archiveBytes)
      this.record('bound-original-request.txt', requestBytes)
      this.record('binding.json', { schema_version: 1, kind: 'p1-paired-evidence-binding', ...this.identity(),
        process_id: process.pid, archive_snapshot: data.snapshot, config_sha256: digest(config),
        extraction_policy: EXTRACTION_POLICY, verification_policy: POLICY_VERSION,
        reference_count_method: 'utf8_bytes_upper_bound_not_a_tokenizer', native_host_attested: false })
    } catch (error) { this.archive.close(); throw error }
  }

  identity() {
    return { task_id: this.config.taskId, archive_sha256: this.config.archiveSha256,
      original_request_sha256: this.config.requestSha256, archive_epoch: this.archive.epoch }
  }
  assertBinding() {
    if (this.closed) fail('evidence_helper_closed')
    if (sha(readBounded(this.config.archivePath, 1048576)) !== this.config.archiveSha256) fail('archive_digest_mismatch')
    if (sha(readBounded(this.config.requestPath, 16384)) !== this.config.requestSha256) fail('request_digest_mismatch')
  }
  record(name, value) {
    const bytes = Buffer.isBuffer(value) ? value : Buffer.from(JSON.stringify(value, null, 2) + '\n')
    const destination = join(this.output, name)
    mkdirSync(dirname(destination), { recursive: true, mode: 0o700 })
    let fd
    try {
      fd = openSync(destination, constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY, 0o600)
      writeFileSync(fd, bytes); fsyncSync(fd)
    } finally { if (fd !== undefined) closeSync(fd) }
    const ref = { path: name, sha256: sha(bytes) }
    this.traceRefs.push(ref)
    return ref
  }
  result(value) { return { ...value, trace_refs: structuredClone(this.traceRefs) } }

  prepare() {
    this.assertBinding()
    if (this.prepared || this.extraction !== null || this.busy) fail('preparation_consumed')
    this.prepared = true
    const prompt = `${EXTRACTION_INSTRUCTIONS}\n\nOBSERVABLE_INPUT_JSON\n${JSON.stringify(this.input)}`
    const report = { ...this.identity(), input: structuredClone(this.input), prompt, prompt_sha256: sha(prompt),
      policy: EXTRACTION_POLICY, extraction_input_sha256: digest(this.input) }
    this.record('prepared.json', report)
    return this.result(report)
  }
  async install(rawOutput) {
    this.assertBinding()
    if (!this.prepared || this.extraction !== null || this.busy) fail('preparation_consumed')
    if (typeof rawOutput !== 'string' || Buffer.byteLength(rawOutput) > 65536) fail('extraction_output_byte_budget')
    this.prepared = false
    this.extraction = await extractClaims(structuredClone(this.input), async () => rawOutput)
    this.record('extraction.json', { ...this.identity(), ...this.extraction,
      provenance: 'actual_auxiliary_output_validated_by_extractClaims' })
    return this.result({ ...this.identity(), ...structuredClone(this.extraction) })
  }

  async prime(options = {}) {
    if (this.primed) fail('prime_already_consumed')
    return this.run({ ...options, mode: 'selective', unitId: 'prime' }, true)
  }
  async verify(options) { return this.run(options, false) }

  async openOriginal(hit, context) {
    const metadata = this.#sourceMetadata.get(hit.eventId)
    const row = { event_id: hit.eventId, status: 'blocked', reason: null, operation_id: null, actual_bytes: 0, pages: 0 }
    context.openEvents.push(row)
    const deny = code => { row.reason = code; fail(code) }
    if (!metadata || hit.sourceDigest !== metadata.digest) deny('unknown_bound_source')
    if (metadata.bytes > context.limits.maxSourceBytesPerOpen) deny('source_metadata_byte_bound')
    if (context.counts.source_open_calls >= context.limits.maxSourceOpens
        || context.reservedBytes + metadata.bytes > context.limits.maxSourceBytes) deny('source_open_budget_exhausted')
    const ordinal = String(++this.sequence).padStart(6, '0')
    const operationId = 'source-open-' + randomUUID()
    const intent = { schema_version: 1, kind: 'source_open', operation_id: operationId, ...this.identity(),
      unit_id: context.unitId, event_id: hit.eventId, source_bytes_upper_bound: metadata.bytes,
      bound_from_ingested_archive_metadata: true }
    row.operation_id = operationId
    this.record(`opens/${ordinal}-intent.json`, intent)
    context.counts.source_open_admissions_requested++
    let response
    try { response = await this.authorizeOpen(structuredClone(intent)) }
    catch { response = { allowed: false, operation_id: operationId, reason: 'admission_unavailable' } }
    if (!plain(response) || response.allowed !== true || response.operation_id !== operationId) {
      this.record(`opens/${ordinal}-admission.json`, { operation_id: operationId, allowed: false })
      context.counts.source_open_admissions_denied++
      deny('source_open_admission_unconfirmed')
    }
    this.record(`opens/${ordinal}-admission.json`, response)
    this.assertBinding()
    context.counts.source_open_calls++
    context.counts.public_tool_calls++
    context.reservedBytes += metadata.bytes
    const opening = { counts: context.counts, upper: metadata.bytes, actualBytes: 0, pages: 0 }
    this.opening = opening
    try {
      const original = await this.archive.open(hit)
      if (digest(original) !== metadata.digest || jsonBytes(original).length !== metadata.bytes
          || opening.actualBytes !== metadata.bytes || opening.pages !== 1) fail('bound_original_identity_mismatch')
      row.status = 'opened'
      return original
    } catch (error) {
      row.status = 'failed'
      row.reason = safeError(error)
      if (opening.pages === 0) context.counts.source_open_bytes_complete = false
      throw error
    } finally {
      this.opening = null
      row.actual_bytes = opening.actualBytes
      row.pages = opening.pages
      this.record(`opens/${ordinal}-result.json`, row)
    }
  }

  async run(options, prime) {
    this.assertBinding()
    if (this.busy) fail('evidence_helper_busy')
    if (!this.extraction?.ok) fail('no_accepted_extraction')
    if (!prime && !this.primed) fail('prime_required_in_same_process')
    if (!fields(options, ['mode', 'unitId', 'limits'], ['maxPacketBytes', 'maxEvidenceBytes', 'maxReferenceBytes'])
        || !['always', 'selective'].includes(options.mode) || !label(options.unitId)
        || !prime && options.unitId === 'prime') fail('invalid_verification_settings')
    const limits = validateLimits(options.limits, prime)
    const maxPacketBytes = options.maxPacketBytes ?? 20000
    const maxEvidenceBytes = options.maxEvidenceBytes ?? 4000
    const maxReferenceBytes = options.maxReferenceBytes ?? 4000
    if (![maxPacketBytes, maxEvidenceBytes, maxReferenceBytes].every(n => Number.isSafeInteger(n) && n > 0)
        || maxPacketBytes > 262144 || maxEvidenceBytes > 4000 || maxReferenceBytes > 4000)
      fail('invalid_delivery_byte_limits')
    if (this.#units.has(options.unitId)) fail('unit_already_consumed')
    if (this.#units.size >= 129) fail('verification_unit_budget')
    this.#units.add(options.unitId)
    if (prime) this.primed = true
    this.busy = true
    const context = { unitId: options.unitId, limits, reservedBytes: 0, openEvents: [], counts: {
      source_open_calls: 0, source_open_bytes: 0, source_open_pages: 0, public_tool_calls: 0,
      source_open_bytes_complete: true,
      source_open_admissions_requested: 0, source_open_admissions_denied: 0 } }
    const localCache = new Map([...this.#primeCache].map(([key, value]) => [key, structuredClone(value)]))
    try {
      const adapter = { readView: claim => this.archive.readView(claim), search: query => this.archive.search(query),
        open: hit => this.openOriginal(hit, context) }
      const results = []
      for (const claim of this.extraction.claims) {
        const result = await verifyEvidence({ claim, now: this.cutoff, mode: options.mode,
          cached: localCache.get(claim.proposalId) ?? null, maxEvidenceBytes, maxReferenceTokens: maxReferenceBytes, maxHits: 128 }, adapter)
        if (result.receipt && options.mode === 'selective') localCache.set(claim.proposalId, structuredClone(result.receipt))
        results.push(result)
      }
      this.assertBinding()
      if (prime) this.#primeCache = new Map(results.flatMap((r, i) => r.receipt
        ? [[this.extraction.claims[i].proposalId, structuredClone(r.receipt)]] : []))
      const counts = { ...context.counts,
        source_open_reserved_bytes: context.reservedBytes,
        verifier_view_reads: results.reduce((n, r) => n + r.metrics.viewReads, 0),
        verifier_searches: results.reduce((n, r) => n + r.metrics.searches, 0),
        verifier_open_attempts: results.reduce((n, r) => n + r.metrics.opens, 0),
        reused_receipts: results.filter(r => r.reused).length,
        supported_claims: results.filter(r => r.outcome === 'supported').length,
        abstained_claims: results.filter(r => r.outcome === 'abstain').length }
      let packet = { schema_version: 1, kind: 'typed_archive_evidence', verificationAvailable: results.length > 0,
        coverageEstablished: false, authorizesExecution: false,
        evidenceScope: 'complete_ingested_archive_at_recorded_cutoff',
        results: results.map((r, i) => ({ claim: this.extraction.claims[i], outcome: r.outcome,
          status: r.status, reason: r.reason, source: r.source, authorizesExecution: false })) }
      const completePacketBytes = jsonBytes(packet).length
      const deliveryBlocked = completePacketBytes > maxPacketBytes
      if (deliveryBlocked) packet = { schema_version: 1, kind: 'typed_archive_evidence', verificationAvailable: false,
        coverageEstablished: false, authorizesExecution: false, reason: 'combined_packet_byte_budget', results: [] }
      const report = { schema_version: 1, kind: prime ? 'p1-prime-verification' : 'p1-paired-verification',
        ...this.identity(), unit_id: options.unitId, mode: options.mode, results, packet,
        receipts: results.map(r => r.receipt ?? null), counts, open_events: context.openEvents,
        limits, maxPacketBytes, maxEvidenceBytes, maxReferenceBytes, completePacketBytes,
        deliveredPacketBytes: jsonBytes(packet).length, deliveryBlocked,
        countMethod: 'utf8_bytes_upper_bound_not_a_tokenizer', tokenizerMeasurement: false,
        referenceTokenCount: null, providerTokenCount: null,
        cachePolicy: prime ? 'create_immutable_prime_cache' : 'independent_clone_of_original_prime_cache',
        extraction_sha256: this.traceRefs.find(ref => ref.path === 'extraction.json').sha256 }
      this.record(prime ? 'prime.json' : `verifications/${String(++this.verifySequence).padStart(6, '0')}.json`, report)
      return this.result(report)
    } finally { this.busy = false }
  }
  close() {
    if (this.closed) return
    this.closed = true
    this.archive.close()
  }
}

/** Bounded line protocol. Admission responses are serviced while the one active
 * RPC awaits them; ordinary RPCs never run concurrently against one archive. */
export async function servePairedEvidence(config, input = process.stdin, output = process.stdout) {
  const send = value => output.write(JSON.stringify(value) + '\n')
  const pending = new Map()
  let active = null, ended = false, buffer = Buffer.alloc(0)
  const helper = new PairedEvidence(config, { authorizeOpen: intent => new Promise((resolvePromise, reject) => {
    if (ended) { reject(new EvidenceHelperError('controller_input_closed')); return }
    const id = randomUUID()
    const timeout = setTimeout(() => { pending.delete(id); reject(new EvidenceHelperError('source_open_admission_timeout')) }, 30000)
    pending.set(id, { resolve: resolvePromise, reject, timeout })
    send({ kind: 'operation_admission_required', id, intent })
  }) })
  const rpc = async message => {
    if (!plain(message) || !label(message.id) || typeof message.op !== 'string') fail('invalid_controller_rpc')
    let result
    if (message.op === 'prepare' && fields(message, ['id', 'op'])) result = helper.prepare()
    else if (message.op === 'install' && fields(message, ['id', 'op', 'rawOutput'])) result = await helper.install(message.rawOutput)
    else if (message.op === 'prime' && fields(message, ['id', 'op', 'limits'], ['maxPacketBytes', 'maxEvidenceBytes', 'maxReferenceBytes'])) {
      const { id, op, ...options } = message
      result = await helper.prime(options)
    } else if (message.op === 'verify' && fields(message, ['id', 'op', 'unitId', 'mode', 'limits'], ['maxPacketBytes', 'maxEvidenceBytes', 'maxReferenceBytes'])) {
      const { id, op, ...options } = message
      result = await helper.verify(options)
    } else fail('unknown_controller_operation')
    send({ ok: true, id: message.id, result })
  }
  const handle = line => {
    let message
    try { message = parse(line) } catch (error) { send({ ok: false, id: null, error: safeError(error) }); return }
    if (plain(message) && message.kind === 'operation_admission_response') {
      const item = pending.get(message.id)
      if (!item) { send({ ok: false, id: null, error: 'unmatched_admission_response' }); return }
      pending.delete(message.id); clearTimeout(item.timeout)
      if (!fields(message, ['kind', 'id', 'allowed', 'operation_id'], ['receipt'])) item.reject(new EvidenceHelperError('invalid_admission_response'))
      else item.resolve(message)
      return
    }
    if (active) { send({ ok: false, id: label(message?.id) ? message.id : null, error: 'evidence_helper_busy' }); return }
    active = rpc(message).catch(error => send({ ok: false, id: label(message?.id) ? message.id : null, error: safeError(error) }))
      .finally(() => { active = null })
  }
  try {
    for await (const chunk of input) {
      buffer = Buffer.concat([buffer, Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)])
      let newline
      while ((newline = buffer.indexOf(10)) >= 0) {
        const line = buffer.subarray(0, newline)
        buffer = buffer.subarray(newline + 1)
        if (line.length > 1048576) fail('controller_line_byte_budget')
        if (line.length) handle(line)
        // Give a synchronous prepare/install RPC its turn before another line
        // from the same pipe chunk, without awaiting a pending admission RPC.
        await Promise.resolve()
      }
      if (buffer.length > 1048576) fail('controller_line_byte_budget')
    }
    if (buffer.length) fail('unterminated_controller_line')
  } finally {
    ended = true
    for (const item of pending.values()) { clearTimeout(item.timeout); item.reject(new EvidenceHelperError('controller_input_closed')) }
    pending.clear()
    if (active) await active
    helper.close()
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    if (process.argv.length !== 3) fail('configuration_path_required')
    await servePairedEvidence(parse(readBounded(process.argv[2], 524288)))
  } catch (error) {
    process.stderr.write(safeError(error) + '\n')
    process.exitCode = 1
  }
}
