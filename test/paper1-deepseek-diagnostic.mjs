import assert from 'node:assert/strict'
import test from 'node:test'
import { createHash } from 'node:crypto'
import { chmodSync, cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { createCanonicalDiagnosticController, inspectDiagnostic, loadDiagnosticConfig,
  loadDiagnosticCredential, runDiagnostic } from '../scripts/paper1/deepseek-diagnostic.mjs'

// Every credential, balance and completion in this suite is an owned fixture.
// Real Python ledger integration is confined to a copied temporary repository.
const KEY = 'sk-diagnostic-fixture-not-a-real-key'
const env = { DEEPSEEK_API_KEY: KEY }
const now = () => new Date('2026-11-28T10:00:00Z')
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const config = loadDiagnosticConfig()
const body = () => ({ id: 'diagnostic-fixture', object: 'chat.completion', model: 'deepseek-flash',
  choices: [{ index: 0, finish_reason: 'stop', message: { role: 'assistant', content: JSON.stringify({
    claims: [{ type: 'operation_authorization', scope: 'demo', entity: 'release', version: 'c1',
      actor: 'maintainer', action: 'publish', basis: { field: 'draft', quote: 'approved publishing release c1' }, uncertainty: [] }], unresolved: [] }) } }],
  usage: { prompt_tokens: 100, completion_tokens: 20, total_tokens: 120, prompt_cache_hit_tokens: 40, prompt_cache_miss_tokens: 60 } })
const response = value => new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } })
function setup({ available = true, balanceResponse, completionBody, reserveOverride, eventOverride, finishOverride, persistOverride } = {}) {
  const order = [], reports = [], ledgerCalls = []
  const ledger = {
    reserve: async args => {
      order.push('reserve'); ledgerCalls.push({ kind: 'reserve', args })
      if (reserveOverride) return reserveOverride(args)
      return { dry_run: false, dispatch_allowed: true, reservation: { sha256: '1'.repeat(64), data: {
        ...args, kind: 'diagnostic', upper_bound_fen: 300, unit_key: null, public_sha256: null, wall_seconds: 30 } } }
    },
    event: async args => {
      order.push('event'); ledgerCalls.push({ kind: 'event', args })
      return eventOverride ? eventOverride(args) : { dispatch_allowed: true, reservation: { sha256: '2'.repeat(64), data: args } }
    },
    finish: async args => {
      order.push('finish'); ledgerCalls.push({ kind: 'finish', args })
      return finishOverride ? finishOverride(args) : { event: { sha256: '3'.repeat(64), data: { ...args, actual_added_cost_fen: null } } }
    },
  }
  const fetchImpl = async (url, options) => {
    assert.equal(options.redirect, 'error'); assert.equal(options.credentials, 'omit')
    assert.equal(options.headers.Authorization, 'Bearer ' + KEY)
    if (options.method === 'GET') {
      order.push('balance'); assert.equal(url, 'https://api.deepseek.com/user/balance')
      return balanceResponse ? balanceResponse() : response({ is_available: available, balance_infos: [{ currency: 'CNY', total_balance: 'PRIVATE_ACCOUNT_AMOUNT' }] })
    }
    order.push('generation'); assert.equal(url, 'https://api.deepseek.com/chat/completions')
    const request = JSON.parse(options.body)
    assert.equal(request.max_tokens, 1024); assert.equal(request.model, 'deepseek-flash')
    assert.deepEqual(request.thinking, { type: 'disabled' }); assert.equal(request.stream, false)
    assert.ok(!options.body.includes(KEY)); assert.ok(options.body.includes(config.input.draft))
    return response(completionBody ? completionBody() : body())
  }
  const persist = async report => { order.push('persist'); reports.push(report); if (persistOverride) await persistOverride(report) }
  return { args: { environ: env, fetchImpl, ledger, persist, now, attemptId: 'diagnostic-fixture-1' }, order, reports, ledgerCalls }
}

test('default inspection reads no credentials and declares no experiment readiness', () => {
  const inspected = inspectDiagnostic({ now: now() })
  assert.equal(inspected.provider_requests, 0); assert.equal(inspected.credentials_read, false)
  assert.equal(inspected.pricing_current, true); assert.equal(inspected.scientific_ready, false)
  const output = execFileSync(process.execPath, ['scripts/paper1/deepseek-diagnostic.mjs'], {
    cwd: root, encoding: 'utf8', env: { PATH: process.env.PATH, DEEPSEEK_API_KEY: KEY } })
  assert.ok(!output.includes(KEY)); assert.equal(JSON.parse(output).credentials_read, false)
})

test('expired pricing blocks before any metadata, reservation or generation request', async () => {
  const fixture = setup(); fixture.args.now = () => new Date('2026-11-28T16:00:00Z')
  const result = await runDiagnostic(fixture.args)
  assert.equal(result.error_code, 'diagnostic_price_expired')
  assert.equal(result.read_only_requests_started, 0); assert.equal(result.generation_requests_started, 0)
  assert.deepEqual(fixture.ledgerCalls, []); assert.deepEqual(fixture.order, ['persist'])
})

test('unavailable balance records a block without reserving any cash or attempt', async () => {
  const fixture = setup({ available: false }); const result = await runDiagnostic(fixture.args)
  assert.equal(result.status, 'blocked'); assert.equal(result.error_code, 'diagnostic_balance_unavailable')
  assert.equal(result.generation_requests_started, 0); assert.equal(result.reservation_attempted, false)
  assert.deepEqual(fixture.ledgerCalls, []); assert.deepEqual(fixture.order, ['balance', 'persist'])
  assert.ok(!JSON.stringify(result).includes('PRIVATE_ACCOUNT_AMOUNT'))
})

test('unknown, malformed, redirected and oversized balance responses fail closed', async () => {
  const responses = [() => response({}), () => new Response(KEY, { status: 401 }),
    () => new Response('{', { headers: { 'content-type': 'application/json' } }),
    () => ({ status: 200, redirected: true, body: { cancel() {} } }),
    () => new Response('x'.repeat(17000), { headers: { 'content-type': 'application/json' } }),
    () => { throw new Error(KEY) }]
  for (const balanceResponse of responses) {
    const fixture = setup({ balanceResponse }); const result = await runDiagnostic(fixture.args)
    assert.equal(result.error_code, 'diagnostic_balance_unknown'); assert.equal(result.generation_requests_started, 0)
    assert.deepEqual(fixture.ledgerCalls, []); assert.ok(!JSON.stringify(result).includes(KEY))
  }
})

test('hung balance fetch is bounded even when fixture ignores the abort signal', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const fixture = setup({ balanceResponse: () => new Promise(() => {}) })
  const pending = runDiagnostic(fixture.args)
  await Promise.resolve(); t.mock.timers.tick(15001)
  const result = await pending
  assert.equal(result.error_code, 'diagnostic_balance_unknown'); assert.deepEqual(fixture.ledgerCalls, [])
})

test('available USD or unknown-currency accounts cannot use the CNY reservation basis', async () => {
  for (const balance_infos of [undefined, [], [{ currency: 'USD' }], [{ currency: 'CNY' }, { currency: 'USD' }]]) {
    const fixture = setup({ balanceResponse: () => response({ is_available: true, balance_infos }) })
    const result = await runDiagnostic(fixture.args)
    assert.equal(result.error_code, 'diagnostic_billing_currency_unverified')
    assert.deepEqual(fixture.ledgerCalls, []); assert.equal(result.generation_requests_started, 0)
  }
})

test('one diagnostic persists request-bound cash and operation before a generation', async () => {
  const fixture = setup(); const result = await runDiagnostic(fixture.args)
  assert.equal(result.status, 'completed'); assert.equal(result.generation_requests_started, 1)
  assert.equal(result.reservation_confirmed, true); assert.equal(result.operation_confirmed, true)
  assert.equal(result.ledger_finish, 'confirmed'); assert.equal(result.reserved_upper_bound_cny, '3.00')
  assert.equal(result.actual_added_cost_cny, null); assert.equal(result.standardized_peak_cost_estimate_cny, '0.00028160')
  assert.equal(result.scientific_ready, false); assert.equal(result.research_sample, false)
  assert.deepEqual(fixture.order, ['balance', 'reserve', 'event', 'persist', 'generation', 'persist', 'finish', 'persist'])
  const reservation = fixture.ledgerCalls[0].args, operation = fixture.ledgerCalls[1].args
  assert.equal(reservation.binding.config_sha256, result.transport_config_sha256)
  assert.equal(operation.operation_id, reservation.binding.dispatch_id)
  assert.equal(reservation.billing_basis.evidence.ref, 'scripts/paper1/deepseek-diagnostic-config.json')
  assert.ok(!JSON.stringify(fixture.reports).includes(KEY)); assert.ok(!JSON.stringify(result).includes('PRIVATE_ACCOUNT_AMOUNT'))
})

test('rejected or unconfirmed reservation never finishes an existing unrelated attempt', async () => {
  for (const reserveOverride of [() => { throw new Error('attempt_already_reserved_do_not_redispatch') }, () => ({ dispatch_allowed: true })]) {
    const fixture = setup({ reserveOverride }); const result = await runDiagnostic(fixture.args)
    assert.equal(result.reservation_attempted, true); assert.equal(result.reservation_confirmed, false)
    assert.equal(result.ledger_finish, 'not_attempted_unconfirmed_reservation'); assert.equal(result.generation_requests_started, 0)
    assert.deepEqual(fixture.ledgerCalls.map(x => x.kind), ['reserve'])
  }
})

test('wrong operation receipt cannot dispatch and closes only its confirmed reservation', async () => {
  const fixture = setup({ eventOverride: args => ({ dispatch_allowed: true, reservation: { sha256: '2'.repeat(64), data: { ...args, operation_id: 'other' } } }) })
  const result = await runDiagnostic(fixture.args)
  assert.equal(result.status, 'failed'); assert.equal(result.generation_requests_started, 0)
  assert.equal(result.reservation_confirmed, true); assert.equal(result.ledger_finish, 'confirmed')
  assert.deepEqual(fixture.ledgerCalls.map(x => x.kind), ['reserve', 'event', 'finish'])
})

test('a reservation callback returning after transport timeout cannot mutate the returned record or start an operation', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let release, reservedArgs
  const fixture = setup({ reserveOverride: args => { reservedArgs = args; return new Promise(resolve => { release = resolve }) } })
  const pending = runDiagnostic(fixture.args)
  for (let i = 0; i < 30 && !release; i++) await Promise.resolve()
  assert.equal(typeof release, 'function')
  t.mock.timers.tick(30001)
  const result = await pending
  const before = JSON.stringify(result)
  release({ dry_run: false, dispatch_allowed: true, reservation: { sha256: '1'.repeat(64), data: {
    ...reservedArgs, kind: 'diagnostic', upper_bound_fen: 300, unit_key: null, public_sha256: null, wall_seconds: 30 } } })
  for (let i = 0; i < 5; i++) await Promise.resolve()
  assert.deepEqual(fixture.ledgerCalls.map(x => x.kind), ['reserve'])
  assert.equal(result.generation_requests_started, 0); assert.equal(JSON.stringify(result), before)
})

test('unguarded or empty actual extraction is failure, without retry or cost settlement', async () => {
  for (const content of [JSON.stringify({ claims: [], unresolved: [] }), JSON.stringify({ claims: [{ ...JSON.parse(body().choices[0].message.content).claims[0], basis: { field: 'draft', quote: 'invented' } }], unresolved: [] })]) {
    const fixture = setup({ completionBody: () => { const value = body(); value.choices[0].message.content = content; return value } })
    const result = await runDiagnostic(fixture.args)
    assert.equal(result.status, 'failed'); assert.equal(result.generation_requests_started, 1)
    assert.equal(result.actual_added_cost_cny, null); assert.equal(fixture.order.filter(x => x === 'generation').length, 1)
    assert.equal(fixture.ledgerCalls.at(-1).args.status, 'failed')
  }
})

test('failed settlement confirmation cannot be reported as a completed diagnostic', async () => {
  const fixture = setup({ finishOverride: () => { throw new Error(KEY) } })
  const result = await runDiagnostic(fixture.args)
  assert.equal(result.status, 'failed'); assert.equal(result.ledger_finish, 'unconfirmed')
  assert.equal(result.error_code, 'diagnostic_ledger_error'); assert.equal(result.actual_added_cost_cny, null)
  assert.ok(!JSON.stringify(result).includes(KEY))
})

test('private credential loader accepts only fixture env or owned mode0600 regular file', t => {
  const directory = mkdtempSync(join(tmpdir(), 'p1-diagnostic-key-fixture-')); t.after(() => rmSync(directory, { recursive: true, force: true }))
  const target = join(directory, '.config/memex/p1/credentials/deepseek_api_key')
  mkdirSync(dirname(target), { recursive: true, mode: 0o700 }); writeFileSync(target, KEY + '\n', { mode: 0o600 })
  assert.deepEqual(loadDiagnosticCredential({ environ: env }), env)
  assert.deepEqual(loadDiagnosticCredential({ environ: {}, homeDirectory: directory }), env)
  chmodSync(target, 0o644)
  assert.throws(() => loadDiagnosticCredential({ environ: {}, homeDirectory: directory }), /diagnostic_credential_file_unsafe/)
  rmSync(target); writeFileSync(target + '-real', KEY, { mode: 0o600 }); symlinkSync(target + '-real', target)
  assert.throws(() => loadDiagnosticCredential({ environ: {}, homeDirectory: directory }), /diagnostic_credential_file_unsafe/)
  assert.throws(() => loadDiagnosticCredential({ environ: { DEEPSEEK_API_KEY: KEY + '\n' }, homeDirectory: directory }), /diagnostic_credential_invalid/)
})

test('canonical CLI controller scrubs credential environment and uses explicit ledger commands', async t => {
  const directory = mkdtempSync(join(tmpdir(), 'p1-diagnostic-controller-')); t.after(() => rmSync(directory, { recursive: true, force: true }))
  const calls = [], attemptId = 'controller-fixture'
  const controller = createCanonicalDiagnosticController({ repoRoot: directory, attemptId,
    execute: (binary, args, options) => { calls.push({ binary, args, options }); return '{}' } })
  await controller.ledger.reserve({ attempt_id: attemptId, binding: { example: 'fixture' }, billing_basis: {}, upper_bound_cny: '3.00' })
  await controller.ledger.event({ operation_id: 'dispatch-fixture' })
  await controller.ledger.finish({ status: 'failed' })
  assert.equal(calls.length, 3)
  for (const call of calls) { assert.equal(call.options.env.DEEPSEEK_API_KEY, undefined); assert.equal(call.options.timeout, 5000); assert.ok(!JSON.stringify(call).includes(KEY)) }
  assert.ok(calls[0].args.includes('reserve-diagnostic')); assert.ok(calls[0].args.includes('--run'))
  assert.ok(calls[1].args.includes('event')); assert.ok(!calls[1].args.includes('--run'))
  await controller.persist({ safe: true }); assert.deepEqual(JSON.parse(readFileSync(join(directory, controller.receipt))), { safe: true })
})

test('real canonical ledger integration uses only a copied fixture tree and preserves old prefix', async t => {
  const directory = mkdtempSync(join(tmpdir(), 'p1-diagnostic-ledger-fixture-')); t.after(() => rmSync(directory, { recursive: true, force: true }))
  const auth = 'docs/research/p1-evidence-verification/artifacts/authorized-batch1'
  for (const path of ['scripts/paper1/batch_limits.py', 'scripts/paper1/deepseek-diagnostic-config.json', auth + '/authorization.json', auth + '/ledger']) {
    mkdirSync(dirname(join(directory, path)), { recursive: true }); cpSync(join(root, path), join(directory, path), { recursive: true })
  }
  const journal = auth + '/ledger/events.jsonl', original = readFileSync(join(root, journal))
  const originalHash = createHash('sha256').update(original).digest('hex')
  const controller = createCanonicalDiagnosticController({ repoRoot: directory, attemptId: 'diagnostic-real-cli-fixture' })
  const fixture = setup()
  const result = await runDiagnostic({ ...fixture.args, attemptId: 'diagnostic-real-cli-fixture', ledger: controller.ledger, persist: controller.persist })
  assert.equal(result.status, 'completed'); assert.equal(result.generation_requests_started, 1)
  const status = JSON.parse(execFileSync('python3', ['-I', '-S', '-B', join(directory, 'scripts/paper1/batch_limits.py'), '--repo-root', directory, 'status'], { encoding: 'utf8' }))
  assert.equal(status.native_attempts_reserved, 2); assert.equal(status.method_units_reserved, 0)
  assert.equal(status.committed_cash_upper_bound, '3.00'); assert.equal(status.actual_added_cash_total, null)
  assert.ok(readFileSync(join(directory, journal)).subarray(0, original.length).equals(original))
  assert.equal(createHash('sha256').update(readFileSync(join(root, journal))).digest('hex'), originalHash)
})
