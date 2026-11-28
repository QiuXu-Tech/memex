#!/usr/bin/env node
/** One explicitly requested, cash-reserved setup diagnostic. Never a paper trial.
 * Import/default CLI inspection makes no requests and reads no credential.
 * The exported core requires injected controller/persistence functions; the CLI
 * binds those to batch_limits.py and the canonical ledger in this source tree.
 * No credentials are passed to Python, artifacts, stdout, or raw error objects.
 */
import { createHash, randomUUID } from 'node:crypto'
import { constants, closeSync, existsSync, fstatSync, fsyncSync, lstatSync, mkdirSync,
  openSync, readFileSync, realpathSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { homedir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'
import { extractClaims } from './claims.mjs'
import { createDeepSeekCompletion, loadDeepSeekConfig } from './deepseek.mjs'

const CONFIG_PATH = fileURLToPath(new URL('./deepseek-diagnostic-config.json', import.meta.url))
const CONFIG_REF = 'scripts/paper1/deepseek-diagnostic-config.json'
const BALANCE_URL = 'https://api.deepseek.com/user/balance'
const LABEL = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/
const HEX = /^[a-f0-9]{64}$/
const CODES = new Set(['diagnostic_invalid_options', 'diagnostic_config_invalid', 'diagnostic_price_expired',
  'diagnostic_credential_missing', 'diagnostic_credential_invalid', 'diagnostic_credential_file_unsafe',
  'diagnostic_balance_unknown', 'diagnostic_balance_unavailable', 'diagnostic_billing_currency_unverified', 'diagnostic_ledger_error',
  'diagnostic_reservation_unconfirmed', 'diagnostic_operation_unconfirmed',
  'diagnostic_persistence_failed', 'diagnostic_extraction_failed', 'diagnostic_empty_claims',
  'diagnostic_invalid_cli', 'diagnostic_internal_error'])
export class DiagnosticError extends Error {
  constructor(code) { const safe = CODES.has(code) ? code : 'diagnostic_internal_error'; super(safe); this.code = safe; this.name = 'DiagnosticError' }
}
const fail = code => { throw new DiagnosticError(code) }
const plain = x => x !== null && typeof x === 'object' && !Array.isArray(x)
const exact = (x, fields) => plain(x) && Object.keys(x).length === fields.length && fields.every(k => Object.hasOwn(x, k))
const canonical = x => Array.isArray(x) ? x.map(canonical) : plain(x) ? Object.fromEntries(Object.keys(x).sort().map(k => [k, canonical(x[k])])) : x
const hash = x => createHash('sha256').update(x).digest('hex')
const hashObject = x => hash(JSON.stringify(canonical(x)))
const localDate = date => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)

export function loadDiagnosticConfig() {
  try {
    const config = JSON.parse(readFileSync(CONFIG_PATH, 'utf8'))
    if (!exact(config, ['schema_version', 'kind', 'provider', 'model', 'pricing', 'limits', 'input'])
      || config.schema_version !== 1 || config.kind !== 'p1-deepseek-setup-diagnostic-v1'
      || config.provider !== 'deepseek' || config.model !== 'deepseek-flash'
      || !exact(config.pricing, ['checked_date', 'timezone', 'validity', 'source', 'context_source',
        'maximum_input_tokens_for_reservation', 'peak_input_cny_per_million', 'peak_cached_input_cny_per_million', 'peak_output_cny_per_million',
        'calculated_maximum_cny', 'reserved_upper_bound_cny', 'basis'])
      || config.pricing.checked_date !== '2026-11-28' || config.pricing.timezone !== 'Asia/Shanghai'
      || config.pricing.validity !== 'same_local_calendar_day'
      || config.pricing.source !== 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/'
      || config.pricing.context_source !== 'https://api-docs.deepseek.com/api/list-models/'
      || config.pricing.maximum_input_tokens_for_reservation !== 1048576
      || config.pricing.peak_input_cny_per_million !== '2.00' || config.pricing.peak_output_cny_per_million !== '8.00'
      || config.pricing.peak_cached_input_cny_per_million !== '0.04'
      || config.pricing.calculated_maximum_cny !== '2.105344' || config.pricing.reserved_upper_bound_cny !== '3.00'
      || typeof config.pricing.basis !== 'string'
      || hashObject(config.limits) !== hashObject({ max_tokens: 1024, timeout_ms: 30000, max_request_bytes: 16384,
        max_response_bytes: 65536, generation_requests: 1, automatic_retries: 0 })
      || hashObject(config.input) !== hashObject({ request: 'Identify the claim requiring verification in this public diagnostic example.',
        draft: 'The maintainer approved publishing release c1 in project demo.',
        context: 'This is a synthetic API compatibility diagnostic. No publication or other operation should be executed.', toolDescriptions: [] })) fail('diagnostic_config_invalid')
    return config
  } catch { fail('diagnostic_config_invalid') }
}

export function inspectDiagnostic({ now = new Date() } = {}) {
  const config = loadDiagnosticConfig()
  return { schema_version: 1, kind: 'zero_call_deepseek_diagnostic_inspection', provider: config.provider, model: config.model,
    diagnostic_config_sha256: hash(readFileSync(CONFIG_PATH)), pricing_current: localDate(now) === config.pricing.checked_date,
    price_checked_date: config.pricing.checked_date, reserved_upper_bound_cny: config.pricing.reserved_upper_bound_cny,
    provider_requests: 0, credentials_read: false, diagnostic_live_access_verified: false,
    scientific_ready: false, all_arm_runtime_ready: false, native_host: false, native_compaction: false,
    note: 'Explicit --run checks account availability before any canonical cash reservation or generation.' }
}

export function loadDiagnosticCredential({ environ = {}, homeDirectory } = {}) {
  let value = environ?.DEEPSEEK_API_KEY
  if (value === undefined) {
    if (typeof homeDirectory !== 'string' || !isAbsolute(homeDirectory)) fail('diagnostic_credential_missing')
    const path = join(homeDirectory, '.config', 'memex', 'p1', 'credentials', 'deepseek_api_key')
    let fd
    try {
      for (let p = path; ; p = dirname(p)) {
        if (lstatSync(p).isSymbolicLink()) fail('diagnostic_credential_file_unsafe')
        if (dirname(p) === p) break
      }
      fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW)
      const st = fstatSync(fd)
      if (!st.isFile() || st.size > 1024 || (st.mode & 0o777) !== 0o600
        || (typeof process.getuid === 'function' && st.uid !== process.getuid())) fail('diagnostic_credential_file_unsafe')
      value = readFileSync(fd, 'utf8').trim()
    } catch (error) {
      if (error instanceof DiagnosticError) throw error
      fail(error?.code === 'ENOENT' ? 'diagnostic_credential_missing' : 'diagnostic_credential_file_unsafe')
    } finally { if (fd !== undefined) closeSync(fd) }
  }
  if (typeof value !== 'string' || !/^sk-[A-Za-z0-9_-]{16,509}$/.test(value)) fail('diagnostic_credential_invalid')
  return { DEEPSEEK_API_KEY: value }
}

async function accountAvailable(environ, fetchImpl) {
  const controller = new AbortController()
  const deadline = performance.now() + 15000
  const check = () => { if (controller.signal.aborted || performance.now() >= deadline) fail('diagnostic_balance_unknown') }
  let timer
  const expired = new Promise((_, reject) => { timer = setTimeout(() => {
    controller.abort(); reject(new DiagnosticError('diagnostic_balance_unknown'))
  }, 15000) })
  let response, reader
  const cancel = () => { try { Promise.resolve(reader ? reader.cancel() : response?.body?.cancel()).catch(() => {}) } catch {} }
  try {
    const work = async () => {
      try {
        check()
        response = await fetchImpl(BALANCE_URL, { method: 'GET', redirect: 'error', credentials: 'omit',
          headers: { Accept: 'application/json', Authorization: 'Bearer ' + environ.DEEPSEEK_API_KEY }, signal: controller.signal })
        check()
        if (response.status !== 200 || response.redirected || (response.url && response.url !== BALANCE_URL)
          || !/^application\/json(?:;|$)/i.test(response.headers?.get('content-type') ?? '') || !response.body) fail('diagnostic_balance_unknown')
        const length = response.headers?.get('content-length')
        if (length !== null && length !== undefined && (!/^\d+$/.test(length) || Number(length) > 16384)) fail('diagnostic_balance_unknown')
        reader = response.body.getReader()
        const chunks = []; let bytes = 0
        while (true) {
          check()
          const { done, value } = await reader.read()
          check()
          if (done) break
          if (!(value instanceof Uint8Array)) fail('diagnostic_balance_unknown')
          bytes += value.byteLength
          if (bytes > 16384 || controller.signal.aborted) fail('diagnostic_balance_unknown')
          chunks.push(value)
        }
        const body = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks, bytes)))
        check()
        if (!plain(body) || typeof body.is_available !== 'boolean') fail('diagnostic_balance_unknown')
        // CNY pricing cannot silently reserve for a USD/unknown billing account.
        // Do not retain or output amounts from the private balance response.
        if (body.is_available && (!Array.isArray(body.balance_infos) || body.balance_infos.length !== 1
          || !plain(body.balance_infos[0]) || body.balance_infos[0].currency !== 'CNY')) fail('diagnostic_billing_currency_unverified')
        return body.is_available
      } finally { cancel() }
    }
    return await Promise.race([work(), expired])
  } catch (error) {
    fail(error instanceof DiagnosticError && error.code === 'diagnostic_billing_currency_unverified'
      ? error.code : 'diagnostic_balance_unknown')
  }
  finally {
    clearTimeout(timer); controller.abort()
    cancel()
  }
}

/** Controller seam used by fixtures and the CLI; it never chooses a source task. */
export async function runDiagnostic({ environ, fetchImpl, ledger, persist, now = () => new Date(),
  attemptId = 'deepseek-diagnostic-' + randomUUID() } = {}) {
  if (!plain(environ) || typeof fetchImpl !== 'function' || !plain(ledger)
    || !['reserve', 'event', 'finish'].every(k => typeof ledger[k] === 'function') || typeof persist !== 'function'
    || typeof now !== 'function' || !LABEL.test(attemptId) || attemptId.startsWith('sk-')) fail('diagnostic_invalid_options')
  const secret = loadDiagnosticCredential({ environ }).DEEPSEEK_API_KEY
  if (attemptId.includes(secret)) fail('diagnostic_invalid_options')
  const config = loadDiagnosticConfig()
  const transport = loadDeepSeekConfig()
  transport.max_tokens = config.limits.max_tokens
  transport.limits = { max_request_bytes: config.limits.max_request_bytes, max_response_bytes: config.limits.max_response_bytes,
    timeout_ms: config.limits.timeout_ms }
  const evidence = { ref: CONFIG_REF, sha256: hash(readFileSync(CONFIG_PATH)) }
  const report = { schema_version: 1, kind: 'p1-deepseek-setup-diagnostic', attempt_id: attemptId,
    observed_at: now().toISOString(), provider: 'deepseek', model: 'deepseek-flash',
    diagnostic_config_sha256: evidence.sha256, transport_config_sha256: hashObject(transport),
    input_sha256: hashObject(config.input), status: 'blocked', error_code: null, balance_available: null,
    read_only_requests_started: 0, generation_requests_started: 0, reservation_attempted: false,
    reservation_confirmed: false, operation_confirmed: false, ledger_finish: 'not_needed',
    reserved_upper_bound_cny: null, actual_added_cost_cny: null, standardized_peak_cost_estimate_cny: null,
    scientific_ready: false, all_arm_runtime_ready: false, native_host: false, native_compaction: false,
    research_sample: false, automatic_retries: 0, extraction: null, controller_records: [] }
  let complete, admissionOpen = true
  const admissionStillOpen = () => { if (!admissionOpen) fail('diagnostic_reservation_unconfirmed') }
  const save = async () => {
    try { await persist(structuredClone(report)) } catch { fail('diagnostic_persistence_failed') }
  }
  try {
    if (localDate(now()) !== config.pricing.checked_date) fail('diagnostic_price_expired')
    report.read_only_requests_started = 1
    report.balance_available = await accountAvailable(environ, fetchImpl)
    if (!report.balance_available) fail('diagnostic_balance_unavailable')
    complete = createDeepSeekCompletion({ config: transport, environ, fetchImpl,
      authorizeDispatch: async intent => {
        admissionStillOpen()
        if (localDate(now()) !== config.pricing.checked_date) fail('diagnostic_price_expired')
        const binding = { provider: intent.provider, model: intent.model, endpoint: intent.endpoint,
          dispatch_id: intent.dispatch_id, intent_sha256: intent.intent_sha256, request_sha256: intent.request_sha256,
          config_sha256: report.transport_config_sha256 }
        report.reservation_attempted = true
        const reserved = await ledger.reserve({ attempt_id: attemptId, binding, upper_bound_cny: '3.00',
          billing_basis: { kind: 'priced_upper_bound', evidence } })
        admissionStillOpen()
        const data = reserved?.reservation?.data
        if (reserved?.dry_run !== false || reserved?.dispatch_allowed !== true || data?.attempt_id !== attemptId
          || data?.kind !== 'diagnostic' || data?.upper_bound_fen !== 300 || data?.wall_seconds !== 30
          || data?.unit_key !== null || data?.public_sha256 !== null
          || hashObject(data?.billing_basis) !== hashObject({ kind: 'priced_upper_bound', evidence })
          || hashObject(data?.binding) !== hashObject(binding) || !HEX.test(reserved?.reservation?.sha256 ?? '')) fail('diagnostic_reservation_unconfirmed')
        report.reservation_confirmed = true; report.reserved_upper_bound_cny = '3.00'
        const event = await ledger.event({ attempt_id: attemptId, kind: 'provider_request', operation_id: intent.dispatch_id })
        admissionStillOpen()
        const operation = event?.reservation?.data
        if (event?.dispatch_allowed !== true || operation?.attempt_id !== attemptId || operation?.kind !== 'provider_request'
          || operation?.operation_id !== intent.dispatch_id || !HEX.test(event?.reservation?.sha256 ?? '')) fail('diagnostic_operation_unconfirmed')
        report.operation_confirmed = true
        await save()
        admissionStillOpen()
        return { schema_version: 1, kind: 'p1-dispatch-admission-receipt', decision: 'allow',
          dispatch_id: intent.dispatch_id, intent_sha256: intent.intent_sha256, request_sha256: intent.request_sha256,
          admission_id: 'ledger-' + event.reservation.sha256 }
      } })
    const result = await extractClaims(config.input, complete)
    admissionOpen = false
    report.controller_records = complete.getControllerRecords()
    report.generation_requests_started = report.controller_records.filter(r => r.fetch_started).length
    report.extraction = { ok: result.ok === true, claim_count: result.claims.length, coverage_established: false,
      claims: result.ok ? result.claims : [], unresolved: result.ok ? result.unresolved : [],
      output_sha256: typeof result.rawOutput === 'string' ? hash(result.rawOutput) : null }
    const usage = report.controller_records[0]?.usage
    if (usage && usage.input_tokens > config.pricing.maximum_input_tokens_for_reservation) fail('diagnostic_extraction_failed')
    if (usage) report.standardized_peak_cost_estimate_cny = (((usage.input_tokens - usage.cached_input_tokens) * 2
      + usage.cached_input_tokens * 0.04 + usage.output_tokens * 8) / 1e6).toFixed(8)
    if (!result.ok) fail('diagnostic_extraction_failed')
    if (!result.claims.length) fail('diagnostic_empty_claims')
    report.status = 'completed'
  } catch (error) {
    admissionOpen = false
    report.status = report.reservation_attempted ? 'failed' : 'blocked'
    report.error_code = error instanceof DiagnosticError ? error.code : 'diagnostic_internal_error'
    if (complete) {
      report.controller_records = complete.getControllerRecords()
      report.generation_requests_started = report.controller_records.filter(r => r.fetch_started).length
    }
  }
  // Persist observed outcome before finalizing. A persistence/finish failure must
  // leave the cash held; no retry or zero-cost settlement is fabricated.
  await save()
  if (report.reservation_attempted && !report.reservation_confirmed) {
    report.ledger_finish = 'not_attempted_unconfirmed_reservation'
    await save()
  }
  if (report.reservation_confirmed) {
    try {
      const closed = await ledger.finish({ attempt_id: attemptId, status: report.status === 'completed' ? 'completed' : 'failed' })
      const data = closed?.event?.data
      if (data?.attempt_id !== attemptId || data?.status !== (report.status === 'completed' ? 'completed' : 'failed')
        || data?.actual_added_cost_fen !== null || !HEX.test(closed?.event?.sha256 ?? '')) fail('diagnostic_ledger_error')
      report.ledger_finish = 'confirmed'
    } catch {
      report.ledger_finish = 'unconfirmed'; report.status = 'failed'; report.error_code = 'diagnostic_ledger_error'
    }
    await save()
  }
  return report
}

function safeDirectory(path, create = false) {
  if (create && !existsSync(path)) { safeDirectory(dirname(path), true); mkdirSync(path, { mode: 0o700 }) }
  for (let p = path; ; p = dirname(p)) {
    const st = lstatSync(p)
    if (st.isSymbolicLink() || !st.isDirectory()) fail('diagnostic_persistence_failed')
    if (dirname(p) === p) break
  }
}
function durableJSON(path, value) {
  let fd
  const temporary = path + '.' + randomUUID() + '.tmp'
  try {
    fd = openSync(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600)
    writeFileSync(fd, JSON.stringify(value, null, 2) + '\n'); fsyncSync(fd); closeSync(fd); fd = undefined
    renameSync(temporary, path)
    const directory = openSync(dirname(path), constants.O_RDONLY); try { fsyncSync(directory) } finally { closeSync(directory) }
  } catch { fail('diagnostic_persistence_failed') }
  finally { if (fd !== undefined) closeSync(fd) }
}

export function createCanonicalDiagnosticController({ repoRoot, attemptId, execute = execFileSync } = {}) {
  if (typeof repoRoot !== 'string' || !isAbsolute(repoRoot) || !LABEL.test(attemptId) || typeof execute !== 'function') fail('diagnostic_invalid_options')
  const resultRoot = join(repoRoot, 'docs/research/p1-evidence-verification/artifacts/deepseek-diagnostics')
  safeDirectory(resultRoot, true)
  const directory = join(resultRoot, attemptId)
  mkdirSync(directory, { mode: 0o700 }); safeDirectory(directory)
  const call = args => {
    try {
      const text = execute('python3', ['-I', '-S', '-B', join(repoRoot, 'scripts/paper1/batch_limits.py'), '--repo-root', repoRoot, ...args],
        { cwd: repoRoot, env: { PATH: process.env.PATH ?? '/usr/bin:/bin', PYTHONDONTWRITEBYTECODE: '1' },
          encoding: 'utf8', timeout: 5000, maxBuffer: 1048576, stdio: ['ignore', 'pipe', 'pipe'] })
      return JSON.parse(text)
    } catch { fail('diagnostic_ledger_error') }
  }
  return { receipt: relative(repoRoot, join(directory, 'result.json')).split(sep).join('/'),
    persist: report => durableJSON(join(directory, 'result.json'), report),
    ledger: {
      reserve: args => {
        if (args.attempt_id !== attemptId) fail('diagnostic_invalid_options')
        durableJSON(join(directory, 'binding.json'), args.binding)
        durableJSON(join(directory, 'billing-basis.json'), args.billing_basis)
        return call(['reserve-diagnostic', '--attempt-id', attemptId, '--binding', join(directory, 'binding.json'),
          '--upper-bound-cny', args.upper_bound_cny, '--billing-basis', join(directory, 'billing-basis.json'), '--run'])
      },
      event: args => call(['event', '--attempt-id', attemptId, '--kind', 'provider_request', '--operation-id', args.operation_id]),
      finish: args => call(['finish', '--attempt-id', attemptId, '--status', args.status]),
    } }
}

async function main(argv) {
  if (argv.length === 0 || (argv.length === 1 && argv[0] === '--inspect')) {
    console.log(JSON.stringify(inspectDiagnostic(), null, 2)); return 0
  }
  if (argv.length !== 1 || argv[0] !== '--run') fail('diagnostic_invalid_cli')
  if (!inspectDiagnostic().pricing_current) fail('diagnostic_price_expired')
  const environ = loadDiagnosticCredential({ environ: process.env, homeDirectory: realpathSync(homedir()) })
  const attemptId = 'deepseek-diagnostic-' + randomUUID()
  const repoRoot = realpathSync(fileURLToPath(new URL('../../', import.meta.url)))
  const controller = createCanonicalDiagnosticController({ repoRoot, attemptId })
  const result = await runDiagnostic({ environ, fetchImpl: globalThis.fetch, ledger: controller.ledger,
    persist: controller.persist, attemptId })
  console.log(JSON.stringify({ ...result, receipt: controller.receipt }, null, 2))
  return result.status === 'completed' ? 0 : 2
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).then(code => { process.exitCode = code }, error => {
    console.log(JSON.stringify({ status: 'blocked', error_code: error instanceof DiagnosticError ? error.code : 'diagnostic_internal_error',
      scientific_ready: false, actual_added_cost_cny: null }))
    process.exitCode = 2
  })
}
