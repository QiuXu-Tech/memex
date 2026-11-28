import { createHash } from 'node:crypto'

export const POLICY_VERSION = 'p1-typed-head-v2'
export const claimKey = claim => JSON.stringify([claim.type, claim.scope, claim.entity])
const text = x => typeof x === 'string' && x.trim().length > 0
const date = x => typeof x === 'string' ? Date.parse(x) : NaN
const TYPES = new Set(['test_result', 'current_version', 'operation_authorization'])

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical)
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k, canonical(value[k])]))
  return value
}
export const digest = value => createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex')
export const headCommitment = sources => digest(sources.map(s => [s.eventId, digest(s)]).sort((a, b) => a[0].localeCompare(b[0])))

export function validateClaim(claim) {
  const resolvedOrNull = k => Object.hasOwn(claim, k) && (claim[k] === null || text(claim[k]))
  if (!claim || !TYPES.has(claim.type) || !['scope', 'entity', 'version'].every(resolvedOrNull)) throw new TypeError('unsupported or incomplete proposed claim')
  if (claim.type === 'operation_authorization' && !['actor', 'action'].every(resolvedOrNull)) throw new TypeError('authorization requires actor and action')
  if (claim.maxAgeMs !== undefined && (!Number.isSafeInteger(claim.maxAgeMs) || claim.maxAgeMs < 0)) throw new TypeError('invalid maxAgeMs')
}

function viewIssue(view, claim) {
  if (!view || view.key !== claimKey(claim) || !text(view.epoch) || !text(view.watermark)
      || !/^[a-f0-9]{64}$/.test(view.headCommitment ?? '')
      || !Number.isSafeInteger(view.headSequence) || view.headSequence < 0
      || !Number.isSafeInteger(view.headEventCount) || view.headEventCount < 0) return 'invalid_view'
  if (view.complete !== true) return 'incomplete_view'
  if (view.conflict === true) return 'conflicting_view'
  if (view.headEventCount > 0 && !text(view.sourceId)) return 'ambiguous_source_order'
  return null
}

function qualify(source, claim, now) {
  if (!source || claimKey(source) !== claimKey(claim)) return 'wrong_scope_or_entity'
  if (!text(source.eventId) || !text(source.sourceId) || !text(source.version)
      || !Number.isSafeInteger(source.sourceSequence) || source.sourceSequence < 1) return 'invalid_source'
  if (source.complete !== true || !text(source.text)) return 'incomplete_source'
  const observed = date(source.observedAt)
  if (!Number.isFinite(observed)) return 'invalid_time'
  if (observed > now) return 'future_source'
  const effective = source.effectiveAt === undefined ? observed : date(source.effectiveAt)
  if (!Number.isFinite(effective)) return 'invalid_time'
  if (effective > now) return 'not_yet_effective'
  const expires = source.expiresAt === undefined ? Infinity : date(source.expiresAt)
  if (Number.isNaN(expires) || expires < observed) return 'invalid_time'
  if (now >= expires || now - observed > (claim.maxAgeMs ?? Infinity)) return 'expired'
  if (claim.type !== 'current_version' && source.version !== claim.version) return 'version_mismatch'
  if (claim.type === 'test_result') {
    if (source.kind !== 'command_execution' || source.role !== 'tool') return 'source_kind'
    if (!text(source.command) || source.completed !== true) return 'incomplete_execution'
    if (source.status === 'passed' && (!Number.isSafeInteger(source.testCount) || source.testCount < 1)) return 'no_tests_executed'
    if (source.status === 'not_run') {
      if (source.executed !== false || source.exitCode != null) return 'invalid_execution'
    } else if (source.executed !== true || !Number.isSafeInteger(source.exitCode)
        || !['passed', 'failed'].includes(source.status)
        || (source.exitCode === 0) !== (source.status === 'passed')) return 'invalid_execution'
  } else if (claim.type === 'current_version') {
    if (source.kind !== 'version_readback' || source.role !== 'tool' || source.authoritative !== true) return 'source_kind'
    if (source.status !== 'current') return 'unknown_status'
  } else {
    if (source.kind !== 'user_decision' || source.role !== 'user') return 'source_kind'
    if (source.actor !== claim.actor || source.action !== claim.action) return 'authorization_scope'
    if (!['granted', 'revoked', 'denied'].includes(source.status)) return 'unknown_status'
  }
  return null
}

/**
 * Research verifier over a trusted, complete *ingested* source view.
 * The adapter, not the model or evaluator gold, supplies view metadata.
 * A sourceSequence must order a source's state snapshots, not arrival order.
 * A stable head is insufficient: all distinct events at that head must be opened.
 * This bounded snapshot policy does not interpret arbitrary legal permission,
 * authenticate external producers, or prove absence of unobserved updates.
 */
export async function verifyEvidence({ claim, now, cached = null, mode = 'selective', maxEvidenceBytes = 4800,
  maxReferenceTokens = 1200, maxHits = 128 }, adapter) {
  validateClaim(claim)
  const asOf = date(now)
  if (!Number.isFinite(asOf)) throw new TypeError('now must be an ISO timestamp')
  if (!['selective', 'always'].includes(mode)) throw new TypeError('invalid verification mode')
  for (const n of [maxEvidenceBytes, maxReferenceTokens, maxHits]) if (!Number.isSafeInteger(n) || n < 1) throw new TypeError('budgets must be positive integers')
  const trace = []
  const metrics = { viewReads: 0, searches: 0, opens: 0, openedBytes: 0, deliveredBytes: 0, referenceTokens: 0 }
  const abstain = reason => ({ outcome: 'abstain', status: 'unknown', reason, source: null, receipt: null,
    reused: false, authorizesExecution: false, trace, metrics, policyVersion: POLICY_VERSION })
  if (claim.scope === null || claim.entity === null) return abstain('unresolved_target')
  if (claim.type !== 'current_version' && claim.version === null) return abstain('unresolved_version')
  if (claim.type === 'operation_authorization' && (claim.actor === null || claim.action === null)) return abstain('unresolved_authorization')
  const read = async () => {
    metrics.viewReads++
    const value = await adapter.readView(claim)
    trace.push({ stage: 'view', ...value })
    return value
  }
  let before
  try { before = await read() } catch { return abstain('view_unavailable') }
  const issue = viewIssue(before, claim)
  if (issue) return abstain(issue)

  const deliver = async (source, view, reused) => {
    const packet = JSON.stringify(source)
    const bytes = Buffer.byteLength(packet)
    let tokens
    try { tokens = adapter.countTokens ? await adapter.countTokens(packet) : bytes } catch { return abstain('token_count_error') }
    if (!Number.isSafeInteger(tokens) || tokens < 1) return abstain('token_count_error')
    if (bytes > maxEvidenceBytes || tokens > maxReferenceTokens) return abstain('evidence_budget')
    let finalView
    try { finalView = await read() } catch { return abstain('view_unavailable') }
    if (viewIssue(finalView, claim) || digest(view) !== digest(finalView)) return abstain('view_changed')
    metrics.deliveredBytes = bytes
    metrics.referenceTokens = tokens
    trace.push({ stage: reused ? 'reuse' : 'verify', eventId: source.eventId, sourceSequence: source.sourceSequence })
    return { outcome: 'supported', status: source.status, reason: 'verified_current_ingested_view', source,
      receipt: { policyVersion: POLICY_VERSION, claimDigest: digest(claim), view, source, sourceDigest: digest(source) },
      reused, authorizesExecution: false, trace, metrics, policyVersion: POLICY_VERSION,
      tokenCountMethod: adapter.countTokens ? 'adapter_tokenizer' : 'utf8_bytes_upper_bound' }
  }

  if (mode === 'selective' && cached?.view && cached?.source && cached?.policyVersion === POLICY_VERSION && cached.claimDigest === digest(claim)
      && digest(cached.view) === digest(before) && cached.sourceDigest === digest(cached.source)
      && headCommitment([cached.source]) === before.headCommitment
      && cached.source?.sourceSequence === before.headSequence && before.headEventCount === 1
      && cached.source?.sourceId === before.sourceId && qualify(cached.source, claim, asOf) === null) {
    // The complete original is delivered again. Reuse saves source I/O, not
    // automatically model tokens, and is never reported as zero-cost evidence.
    return deliver(structuredClone(cached.source), before, true)
  }

  let hits
  try {
    metrics.searches++
    hits = await adapter.search({ type: claim.type, scope: claim.scope, entity: claim.entity,
      query: [claim.scope, claim.entity, claim.type].join(' '), limit: maxHits })
    if (!Array.isArray(hits)) throw new TypeError('search must return an array')
  } catch { return abstain('retrieval_error') }
  if (hits.length > maxHits) return abstain('retrieval_budget')
  const opened = new Map()
  for (const hit of hits) {
    try {
      metrics.opens++
      const source = await adapter.open(hit)
      if (!source || source.eventId !== hit.eventId) return abstain('source_mismatch')
      if (hit.sourceDigest !== undefined && hit.sourceDigest !== digest(source)) return abstain('source_mismatch')
      metrics.openedBytes += Buffer.byteLength(JSON.stringify(source))
      if (opened.has(source.eventId) && digest(opened.get(source.eventId)) !== digest(source)) return abstain('source_mismatch')
      opened.set(source.eventId, source)
      trace.push({ stage: 'open', eventId: source.eventId, sourceSequence: source.sourceSequence })
    } catch { return abstain('source_unavailable') }
  }
  let after
  try { after = await read() } catch { return abstain('view_unavailable') }
  if (viewIssue(after, claim) || digest(before) !== digest(after)) return abstain('view_changed')
  const relevant = [...opened.values()].filter(s => claimKey(s) === claimKey(claim) && s.sourceId === before.sourceId)
  const latest = relevant.filter(s => s.sourceSequence === before.headSequence)
  if (!latest.length) return abstain('head_not_opened')
  if (latest.length !== before.headEventCount) return abstain('incomplete_head')
  if (headCommitment(latest) !== before.headCommitment) return abstain('head_commitment_mismatch')
  const states = new Set(latest.map(s => JSON.stringify([s.status, s.version, s.actor ?? null, s.action ?? null, s.exitCode ?? null])))
  if (states.size !== 1) return abstain('conflict')
  for (const source of latest) {
    const problem = qualify(source, claim, asOf)
    if (problem) return abstain(problem)
  }
  // Duplicated same-head records are allowed only if their entire contents are
  // identical apart from their opaque event identifiers.
  if (new Set(latest.map(({ eventId, ...s }) => digest(s))).size !== 1) return abstain('conflict')
  return deliver(latest[0], before, false)
}
