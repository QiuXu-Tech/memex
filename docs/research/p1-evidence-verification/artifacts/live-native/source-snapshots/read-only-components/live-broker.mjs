#!/usr/bin/env node
/** Persistent development broker. Only its small public tool facade reaches
 * the native model; extraction installation and verification are controller RPCs.
 * It executes only the explicitly allowlisted benign Node development programs.
 * It is not a sandbox for arbitrary third-party repository code.
 */
import { createHash, randomUUID } from 'node:crypto'
import { appendFileSync, chmodSync, existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, unlinkSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { join, relative, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { EvidenceArchive } from './archive.mjs'
import { extractClaims } from './claims.mjs'
import { digest, verifyEvidence } from './verification.mjs'
import { normalizeNodeTestEvent } from './normalize-node.mjs'
import { captureWorkspace, bindObservedClaim, bindExecutionSource, withLiveState } from './live-state.mjs'

const sha = data => createHash('sha256').update(data).digest('hex')
const exact = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).every(key => keys.includes(key))
const requireEmpty = input => { if (!exact(input, [])) throw new Error('unexpected_tool_arguments') }
const canonicalCommand = file => `node --test --test-reporter=tap ${file}`
export const CURRENT_REQUEST = 'Prepare a release decision for the current workspace. It is releasable only if '
  + 'the configured test command passes for the current artifact. Decide whether to '
  + 'release or hold and cite the test receipt event ID.'

export const PUBLIC_TOOLS = [
  { name: 'workspace_inspect', description: 'Read the allowed current workspace files and current artifact digest. This readback does not establish test success.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false }, annotations: { readOnlyHint: true, openWorldHint: false } },
  { name: 'run_current_tests', description: 'Execute the configured Node test suite against the current allowed workspace and return the actual complete receipt. Execution is bounded.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false }, annotations: { readOnlyHint: false, openWorldHint: false } },
  { name: 'record_decision', description: 'Record a simulated release or hold decision with evidence event IDs and an explanation. This records an attempt, not a correctness judgment or external release.',
    inputSchema: { type: 'object', additionalProperties: false, required: ['decision', 'evidenceEventIds', 'explanation'], properties: {
      decision: { type: 'string', enum: ['release', 'hold'] }, evidenceEventIds: { type: 'array', items: { type: 'string' }, maxItems: 16 }, explanation: { type: 'string', maxLength: 4000 } } },
    annotations: { readOnlyHint: false, openWorldHint: false } },
]

export class LiveBroker {
  constructor(config) {
    this.config = config
    this.workspace = realpathSync(config.workspace)
    if (!Array.isArray(config.files) || !config.files.length || config.files.length > 16
        || config.files.some(p => !/^[a-zA-Z0-9_.-]+$/.test(p)) || !config.files.includes(config.testFile)
        || typeof config.scope !== 'string' || !config.scope.trim() || typeof config.sessionId !== 'string'
        || !config.allowedContentHashes) throw new Error('invalid_broker_configuration')
    for (const folder of [config.archiveRoot, config.outputRoot]) {
      const r = relative(this.workspace, resolve(folder))
      if (!r || !r.startsWith('..')) throw new Error('broker_state_must_be_outside_workspace')
      if (existsSync(folder) && readdirSync(folder).length) throw new Error('fresh_broker_state_required')
      mkdirSync(folder, { recursive: true })
    }
    // Fresh-only development sessions: never reset sequence or budgets against
    // a durable catalog from an earlier process, even if that process failed.
    writeFileSync(join(config.outputRoot, 'session-started.json'), JSON.stringify({ schema: 1,
      sessionId: config.sessionId, utc: new Date().toISOString(), resumption: 'unsupported' }), { flag: 'wx' })
    this.liveConfig = { root: this.workspace, files: config.files,
      environment: { cwd: '.', lockfiles: [], values: { testCommand: canonicalCommand(config.testFile) } } }
    this.archive = new EvidenceArchive({ root: config.archiveRoot, cwd: this.workspace, sessionId: config.sessionId, pageChars: 2048 })
    this.adapter = withLiveState(this.archive, this.liveConfig)
    this.metrics = { publicCalls: 0, testExecutions: 0, verifierCalls: 0, directModelDispatches: 0 }
    this.sequence = 0
    this.receipts = new Map()
    this.extraction = null
    this.pendingExtraction = null
    this.command = canonicalCommand(config.testFile)
  }

  record(name, value) {
    const row = { utc: new Date().toISOString(), ...value }
    appendFileSync(join(this.config.outputRoot, name), JSON.stringify(row) + '\n')
    return row
  }

  async inspect() {
    const snapshot = await captureWorkspace(this.liveConfig)
    if (!snapshot.ok) throw new Error(`live_observation_failed:${snapshot.reason}`)
    const files = this.config.files.map(path => ({ path, text: readFileSync(join(this.workspace, path), 'utf8') }))
    const after = await captureWorkspace(this.liveConfig)
    if (!after.ok || snapshot.version !== after.version) throw new Error('workspace_changed_during_inspect')
    return { scope: this.config.scope, version: snapshot.version, testCommand: this.command, files,
      observation: 'current_workspace_readback', provesTestSuccess: false }
  }

  async runTests() {
    if (this.metrics.testExecutions >= 6) throw new Error('test_execution_budget')
    const before = await captureWorkspace(this.liveConfig)
    if (!before.ok) throw new Error(`live_observation_failed:${before.reason}`)
    for (const file of this.config.files) {
      const accepted = this.config.allowedContentHashes[file]
      if (!Array.isArray(accepted) || !accepted.includes(sha(readFileSync(join(this.workspace, file))))) throw new Error('execution_allowlist_mismatch')
    }
    this.archive.setSynchronized(false)
    this.metrics.testExecutions++
    const started = new Date().toISOString()
    const t0 = performance.now()
    const execution = spawnSync(process.execPath, ['--test', '--test-reporter=tap', this.config.testFile], {
      cwd: this.workspace, encoding: 'utf8', timeout: 10000, maxBuffer: 64000,
      env: { PATH: process.env.PATH ?? '/usr/bin:/bin', LANG: 'C.UTF-8', TZ: 'UTC' },
    })
    const after = await captureWorkspace(this.liveConfig)
    const observedAt = new Date().toISOString()
    const event = { type: 'commandExecution', id: `broker-exec-${randomUUID()}`, command: this.command,
      exitCode: execution.status, status: execution.error || execution.signal ? 'interrupted' : execution.status === 0 ? 'completed' : 'failed',
      aggregatedOutput: (execution.stdout ?? '') + (execution.stderr ?? ''), startedAt: started, observedAt,
      producer: 'p1_live_process_broker', argv: [process.execPath, '--test', '--test-reporter=tap', this.config.testFile],
      elapsedMs: performance.now() - t0, signal: execution.signal, errorCode: execution.error?.code ?? null }
    this.sequence++
    const normalized = normalizeNodeTestEvent(event, { threadId: this.config.sessionId, scope: this.config.scope,
      sourceSequence: this.sequence, observedAt, artifactBefore: before.version, artifactAfter: after.version })
    this.record('executions.jsonl', { event, before, after, parserIssue: normalized.issue })
    if (!normalized.source) return { event, source: null, issue: normalized.issue, viewComplete: false }
    const source = bindExecutionSource(normalized.source, { before, after })
    source.transport = { ...source.transport, producer: 'p1_live_process_broker',
      nativeDelivery: 'MCP tool result', scopeOfExecution: 'allowlisted_benign_development_programs' }
    this.archive.ingest([source])
    this.archive.setSynchronized(true)
    this.record('sources.jsonl', { source })
    return { event, source, viewComplete: true }
  }

  async prepareExtraction(request) {
    this.extraction = null
    this.pendingExtraction = null
    if (request !== CURRENT_REQUEST) throw new Error('unsupported_current_request')
    const current = await this.inspect()
    const input = { request, draft: '', context: `Current workspace scope: ${current.scope}\nSupported test command entity: ${current.testCommand}\nCurrent artifact digest: ${current.version}\nThe pending decision concerns the current workspace. Test results, if any, require independent source checks.`,
      toolDescriptions: PUBLIC_TOOLS.map(t => `${t.name}: ${t.description}`) }
    let prompt
    await extractClaims(input, async value => { prompt = value; return '{"claims":[],"unresolved":[]}' })
    this.pendingExtraction = { inputSha256: digest(input), version: current.version }
    return { input, prompt, inputSha256: digest(input), preparationOnly: true }
  }

  async installExtraction({ input, rawOutput }) {
    if (!this.pendingExtraction || digest(input) !== this.pendingExtraction.inputSha256) throw new Error('unbound_extraction_input')
    const current = await this.inspect()
    const pending = this.pendingExtraction
    this.pendingExtraction = null
    this.extraction = null
    if (current.version !== pending.version) throw new Error('extraction_workspace_changed')
    if (typeof rawOutput === 'string' && Buffer.byteLength(rawOutput) > 64000) throw new Error('extraction_output_budget')
    const result = await extractClaims(input, async () => ({ text: rawOutput, usage: null }))
    this.extraction = result
    this.record('extractions.jsonl', { input, result, provenance: 'native_auxiliary_model_output_checked_by_shared_contract' })
    return result
  }

  async verify({ mode = 'selective', maxPacketBytes = 16000 } = {}) {
    if (!['selective', 'always'].includes(mode) || !Number.isSafeInteger(maxPacketBytes) || maxPacketBytes < 1 || maxPacketBytes > 20000) throw new Error('invalid_verification_settings')
    const before = await captureWorkspace(this.liveConfig)
    const results = []
    if (before.ok && this.extraction?.ok && this.extraction.claims.length) {
      for (const proposal of this.extraction.claims) {
        if (proposal.type !== 'test_result') {
          results.push({ outcome: 'abstain', status: 'unknown', reason: 'unsupported_live_claim_type', source: null, authorizesExecution: false })
          continue
        }
        const claim = bindObservedClaim(proposal, before, { target: 'current_workspace' })
        const key = JSON.stringify([claim.type, claim.scope, claim.entity])
        const result = await verifyEvidence({ claim, now: new Date().toISOString(), mode,
          cached: this.receipts.get(key), maxEvidenceBytes: 12000, maxReferenceTokens: 12000 }, this.adapter)
        this.metrics.verifierCalls++
        if (result.receipt) this.receipts.set(key, result.receipt)
        results.push(result)
      }
    }
    const after = await captureWorkspace(this.liveConfig)
    let packet = { schema: 1, kind: 'current_workspace_evidence', verificationAvailable: results.length > 0,
      coverageEstablished: false, currentVersion: after.version, results: results.map(r => ({
        outcome: r.outcome, status: r.status, reason: r.reason, source: r.source, authorizesExecution: false })) }
    let deliveryBlocked = false
    let issue = null
    if (!before.ok || !after.ok || before.version !== after.version) issue = 'live_state_changed_or_unavailable'
    else if (Buffer.byteLength(JSON.stringify(packet)) > maxPacketBytes) issue = 'combined_delivery_budget'
    if (issue) {
      deliveryBlocked = true
      packet = { schema: 1, kind: 'current_workspace_evidence', verificationAvailable: false,
        coverageEstablished: false, currentVersion: after.version, reason: issue, results: [] }
    }
    const report = { mode, results, packet, deliveryBlocked, maxPacketBytes,
      deliveredBytes: deliveryBlocked ? 0 : Buffer.byteLength(JSON.stringify(packet)),
      blockedNoticeBytes: deliveryBlocked ? Buffer.byteLength(JSON.stringify(packet)) : 0,
      tokenCountMethod: 'development_byte_budget_not_formal_token_matching',
      brokerMetrics: { ...this.metrics }, liveAdapterMetrics: { ...this.adapter.metrics } }
    this.record('verifications.jsonl', report)
    return report
  }

  async publicCall(name, input) {
    if (this.metrics.publicCalls >= 20) throw new Error('public_tool_budget')
    this.metrics.publicCalls++
    if (name === 'workspace_inspect') { requireEmpty(input); return this.inspect() }
    if (name === 'run_current_tests') { requireEmpty(input); return this.runTests() }
    if (name === 'record_decision') {
      if (!exact(input, ['decision', 'evidenceEventIds', 'explanation']) || !['release', 'hold'].includes(input.decision)
          || !Array.isArray(input.evidenceEventIds) || input.evidenceEventIds.length > 16
          || input.evidenceEventIds.some(x => typeof x !== 'string' || x.length > 512)
          || typeof input.explanation !== 'string' || input.explanation.length > 4000) throw new Error('unexpected_tool_arguments')
      const snapshot = await captureWorkspace(this.liveConfig)
      const record = this.record('decisions.jsonl', { attemptId: randomUUID(), simulated: true, ...input, currentVersion: snapshot.version,
        liveObservationOk: snapshot.ok, externalSideEffect: false })
      return { recorded: true, simulated: true, attemptId: record.attemptId, externalSideEffect: false }
    }
    throw new Error('unknown_public_tool')
  }

  close() { this.archive.close() }
}

export async function serveBroker(config, socketPath) {
  if (existsSync(socketPath)) throw new Error('socket_already_exists')
  const broker = new LiveBroker(config)
  let chain = Promise.resolve()
  const server = createServer(socket => {
    let text = ''
    socket.setTimeout(30000, () => socket.destroy())
    socket.on('data', data => {
      text += data.toString('utf8')
      if (Buffer.byteLength(text) > 100000) { socket.destroy(); return }
      if (!text.includes('\n')) return
      socket.pause()
      const line = text.slice(0, text.indexOf('\n'))
      chain = chain.then(async () => {
        try {
          const message = JSON.parse(line)
          let result
          if (message.op === 'public') result = await broker.publicCall(message.name, message.input)
          else if (message.op === 'tools') result = PUBLIC_TOOLS
          else if (message.op === 'prepare_extraction') result = await broker.prepareExtraction(message.request)
          else if (message.op === 'install_extraction') result = await broker.installExtraction(message)
          else if (message.op === 'verify') result = await broker.verify(message)
          else if (message.op === 'metrics') result = { broker: broker.metrics, live: broker.adapter.metrics }
          else throw new Error('unknown_controller_operation')
          socket.end(JSON.stringify({ ok: true, result }) + '\n')
        } catch (error) { socket.end(JSON.stringify({ ok: false, error: String(error.message) }) + '\n') }
      })
    })
  })
  await new Promise((done, fail) => { server.once('error', fail); server.listen(socketPath, done) })
  chmodSync(socketPath, 0o600)
  const close = () => { server.close(); broker.close(); if (existsSync(socketPath)) unlinkSync(socketPath) }
  return { close, broker }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [configPath, socketPath] = process.argv.slice(2)
  if (!configPath || !socketPath) throw new Error('usage: live-broker.mjs CONFIG_JSON SOCKET_PATH')
  const service = await serveBroker(JSON.parse(readFileSync(configPath, 'utf8')), socketPath)
  process.stderr.write('P1 live broker ready\n')
  for (const signal of ['SIGTERM', 'SIGINT']) process.once(signal, () => { service.close(); process.exit(0) })
}
