import { createHash } from 'node:crypto'
import { resolve } from 'node:path'
import { createInterface } from 'node:readline'
import { fileURLToPath } from 'node:url'

const MAX_REFERENCE_TOKENS = 1200
const HIT_LIMIT = 5
const SOURCE_KINDS = {
  test_result: 'test_receipt',
  current_version: 'version_readback',
  operation_authorization: 'user_decision',
}
const STATUSES = {
  test_result: new Set(['passed', 'failed', 'not_run', 'unknown']),
  current_version: new Set(['current', 'unknown']),
  operation_authorization: new Set(['granted', 'revoked', 'denied', 'unknown']),
}

const hasText = (value) => typeof value === 'string' && value.trim().length > 0
const timeOf = (value) => typeof value === 'string' ? Date.parse(value) : NaN
const sameEntity = (claim, source) => source.type === claim.type && source.scope === claim.scope && source.entity === claim.entity

function validTestStatus(source) {
  if (source.status === 'not_run') return source.executed === false && source.exitCode == null
  if (source.status === 'unknown') return true
  return source.executed !== false && Number.isSafeInteger(source.exitCode) && (source.exitCode === 0) === (source.status === 'passed')
}

function observe(claim, source, now, opened, origin) {
  if (!source) return { outcome: 'missing_receipt' }
  if (!sameEntity(claim, source)) return { outcome: 'wrong_scope_or_entity' }
  if (source.kind !== SOURCE_KINDS[claim.type]) return { outcome: 'untrusted_source_kind' }
  if (!hasText(source.version) || !hasText(source.sourceRef)) return { outcome: 'invalid_receipt' }
  if (claim.type !== 'current_version' && claim.version !== source.version) return { outcome: 'version_mismatch' }

  const observed = timeOf(source.observedAt)
  if (!Number.isFinite(observed)) return { outcome: 'invalid_receipt' }
  if (observed > now) return { outcome: 'future_receipt' }
  const expires = source.expiresAt == null ? Infinity : timeOf(source.expiresAt)
  let issue = null
  if (!opened || source.complete !== true || !hasText(source.excerpt)) issue = 'incomplete_source'
  else if (Number.isNaN(expires) || expires < observed) issue = 'invalid_receipt'
  else if (!STATUSES[claim.type].has(source.status) || (claim.type === 'test_result' && !validTestStatus(source))) issue = 'invalid_receipt'
  else if (source.status === 'unknown') issue = 'unknown_status'
  else if (now >= expires || now - observed > (claim.maxAgeMs ?? Infinity)) issue = 'stale_receipt'
  return { outcome: issue ?? 'opened', candidate: { source, observed, issue, origin } }
}

function findEvidence(claim, observations) {
  const candidates = observations.flatMap(({ candidate }) => candidate ? [candidate] : [])
  if (!candidates.length) {
    const reason = ['version_mismatch', 'source_mismatch', 'invalid_receipt', 'future_receipt', 'untrusted_source_kind']
      .find((code) => observations.some(({ outcome }) => outcome === code))
    return { reason: reason ?? 'missing_receipt' }
  }

  const latestTime = Math.max(...candidates.map(({ observed }) => observed))
  const latest = candidates.filter(({ observed }) => observed === latestTime)
  const complete = latest.filter(({ issue }) => issue !== 'incomplete_source')
  const available = latest.filter(({ source, issue }) => issue !== 'incomplete_source' || !complete.some((entry) => entry.source.sourceRef === source.sourceRef))
  const values = new Set(available.map(({ source }) => JSON.stringify([source.version, source.status, source.value ?? null])))
  if (values.size > 1) return { reason: 'conflict' }

  const issue = available.find((entry) => entry.issue)?.issue
  if (issue) return { reason: issue }

  const candidate = available.find(({ origin }) => origin === 'retrieval') ?? available[0]
  if (candidate.source.version !== claim.version) return { reason: 'version_mismatch' }
  return { reason: 'verified', candidate }
}

function reference(source) {
  const fields = ['type', 'scope', 'entity', 'version', 'kind', 'status', 'value', 'sourceRef', 'observedAt', 'expiresAt', 'exitCode', 'executed']
  return Object.fromEntries(fields.filter((field) => source[field] !== undefined).map((field) => [field, source[field]]))
}

function matchingOpen(hit, source) {
  if (!source) return 'missing_receipt'
  if (!hasText(hit.sourceRef) || source.sourceRef !== hit.sourceRef) return 'source_mismatch'
  if (hit.excerptSha256 !== undefined && (typeof source.excerpt !== 'string' || createHash('sha256').update(source.excerpt).digest('hex') !== hit.excerptSha256)) return 'source_mismatch'
  return null
}

/**
 * Read-only research gate. `currentEvidence` contains originals already opened
 * in the same trial. Only the host's read-only `open` callback can supply newly
 * opened originals. Structured fields describe the original event, so the host
 * must derive them from its trusted event type and payload, not a search excerpt
 * or another agent's summary. A supported user decision is historical evidence
 * for the named claim and does not grant the adapter permission to act.
 */
export async function checkEvidence({ claim, currentEvidence = [], now, mode = 'auto' }, { search, open, countTokens } = {}) {
  if (!claim || !Object.hasOwn(SOURCE_KINDS, claim.type) || !['scope', 'entity', 'version'].every((key) => hasText(claim[key]))) {
    throw new TypeError('claim requires a supported type, scope, entity, and version')
  }
  if (claim.maxAgeMs !== undefined && (!Number.isSafeInteger(claim.maxAgeMs) || claim.maxAgeMs < 0)) {
    throw new TypeError('maxAgeMs must be a nonnegative integer')
  }
  const asOf = timeOf(now)
  if (!Number.isFinite(asOf)) throw new TypeError('now requires a valid timestamp')
  if (mode !== 'auto' && mode !== 'forced') throw new TypeError('mode must be auto or forced')

  const observations = currentEvidence.map(({ source, opened }) => observe(claim, source, asOf, opened === true, 'current'))
  const trace = []
  const tokenCountMethod = countTokens ? 'o200k_base' : 'utf8_bytes_upper_bound'
  const conclude = ({ candidate, reason, candidateReferenceTokens, injection = null, referenceTokens = 0 }) => {
    const outcome = candidate ? 'supported' : 'abstain'
    const source = candidate ? reference(candidate.source) : null
    const status = source?.status ?? 'unknown'
    trace.push({ stage: 'conclusion', outcome, reason, status, sourceRef: source?.sourceRef ?? null, candidateReferenceTokens })
    return { outcome, status, reason, source, triggered: trace[0].stage === 'trigger', trace, injection, referenceTokens, tokenCountMethod }
  }
  let selection = findEvidence(claim, observations)
  if (selection.candidate && mode !== 'forced') return conclude(selection)

  trace.push({ stage: 'trigger', reason: mode === 'forced' ? 'forced_control' : selection.reason })
  let retrievalError = false
  const unread = new Map()
  for (let attempt = 1; attempt <= 2; attempt++) {
    const query = {
      type: claim.type, scope: claim.scope, entity: claim.entity, version: claim.version,
      matchVersion: attempt === 1 && claim.type !== 'current_version', asOf: now, maxAgeMs: claim.maxAgeMs,
      attempt, strategy: attempt === 1 ? 'exact' : 'disambiguate', hitLimit: HIT_LIMIT,
      unresolvedSourceRefs: [...unread.keys()],
    }
    const step = { stage: 'query', query }
    trace.push(step)
    let hits
    try {
      hits = await search(query)
      if (!Array.isArray(hits)) throw new TypeError('search must return hits as an array')
      step.hitCount = hits.length
    } catch (error) {
      step.error = String(error?.message ?? error)
      retrievalError = true
      continue
    }

    for (const hit of hits.slice(0, HIT_LIMIT)) {
      const sourceRef = hit?.sourceRef ?? null
      if (!hasText(sourceRef)) {
        trace.push({ stage: 'open', sourceRef, outcome: 'invalid_hit', attempted: false })
        continue
      }
      try {
        const source = await open(hit)
        const issue = matchingOpen(hit, source)
        const observation = issue ? { outcome: issue } : observe(claim, source, asOf, true, 'retrieval')
        observations.push(observation)
        if (issue) unread.set(sourceRef, issue)
        else unread.delete(sourceRef)
        trace.push({ stage: 'open', sourceRef, openedSourceRef: source?.sourceRef ?? null, outcome: observation.outcome, attempted: true })
      } catch (error) {
        trace.push({ stage: 'open', sourceRef, outcome: 'retrieval_error', attempted: true, error: String(error?.message ?? error) })
        unread.set(sourceRef, 'retrieval_error')
      }
    }

    selection = findEvidence(claim, observations)
    if (selection.candidate && unread.size === 0) break
  }

  if (unread.size) return conclude({ reason: unread.values().next().value })
  if (!selection.candidate) return conclude({ reason: selection.reason === 'missing_receipt' && retrievalError ? 'retrieval_error' : selection.reason })
  if (selection.candidate.origin === 'current') return conclude(selection)
  const { source } = selection.candidate
  const injection = JSON.stringify({ ...reference(source), excerpt: source.excerpt })
  let referenceTokens
  try {
    // UTF-8 byte length is a conservative upper bound for byte-pair encodings.
    referenceTokens = countTokens ? await countTokens(injection) : Buffer.byteLength(injection)
    if (!Number.isSafeInteger(referenceTokens) || referenceTokens <= 0) throw new TypeError('countTokens must return a positive integer')
  } catch (error) {
    trace.push({ stage: 'count_tokens', outcome: 'token_count_error', error: String(error?.message ?? error) })
    return conclude({ reason: 'token_count_error' })
  }
  if (referenceTokens > MAX_REFERENCE_TOKENS) return conclude({ reason: 'token_budget', candidateReferenceTokens: referenceTokens })
  return conclude({ ...selection, injection, referenceTokens })
}

async function runJsonLines() {
  const input = createInterface({ input: process.stdin })[Symbol.asyncIterator]()
  const emit = (value) => process.stdout.write(`${JSON.stringify(value)}\n`)
  const receive = async (message) => {
    emit(message)
    const reply = await input.next()
    if (reply.done) throw new Error('retrieval driver ended before responding')
    const response = JSON.parse(reply.value)
    if (response.error) throw new Error(response.error)
    return response.value
  }

  for await (const line of input) {
    if (!line.trim()) continue
    try {
      const request = JSON.parse(line)
      const { archive, countReferenceTokens } = request
      const adapter = archive === undefined ? {
        search: (query) => receive({ op: 'search', query }),
        open: (hit) => receive({ op: 'open', hit }),
      } : {
        // Inline archives are a convenience for deterministic offline trials.
        search: (query) => archive.filter((source) => sameEntity(request.claim, source) && (!query.matchVersion || source.version === query.version))
          .sort((a, b) => timeOf(b.observedAt) - timeOf(a.observedAt))
          .map(({ sourceRef }) => ({ sourceRef })),
        open: ({ sourceRef }) => archive.find((source) => source.sourceRef === sourceRef),
      }
      if (countReferenceTokens === true) adapter.countTokens = (injection) => receive({ op: 'count_tokens', injection })
      emit({ op: 'result', result: await checkEvidence(request, adapter) })
    } catch (error) {
      emit({ op: 'error', error: String(error?.message ?? error) })
    }
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) await runJsonLines()
