import assert from 'node:assert/strict'
import test from 'node:test'
import { EXTRACTION_INSTRUCTIONS, extractClaims } from '../scripts/paper1/claims.mjs'
import {
  createDeepSeekCompletion, inspectDeepSeek, loadDeepSeekConfig,
  normalizeDeepSeekUsage, validateDeepSeekConfig,
} from '../scripts/paper1/deepseek.mjs'

// All credentials, requests, responses and authorization receipts here are fixtures.
// Every completion receives an injected fetch; this suite never contacts a provider.
const KEY = 'sk-fixture-only-never-a-real-credential'
const env = { DEEPSEEK_API_KEY: KEY }
const input = { request: 'Can we publish release c1?', draft: 'The maintainer approved publishing commit c1.',
  context: 'Workspace demo; current artifact commit c1.', toolDescriptions: ['read logs'] }
const proposal = { claims: [{ type: 'operation_authorization', scope: 'demo', entity: 'release', version: 'c1',
  actor: 'maintainer', action: 'publish', basis: { field: 'draft', quote: 'approved publishing commit c1' },
  uncertainty: [] }], unresolved: [] }
const prompt = value => `${EXTRACTION_INSTRUCTIONS}\n\nOBSERVABLE_INPUT_JSON\n${JSON.stringify(value)}`
function responseBody(changes = {}) {
  return { id: 'chatcmpl-fixture', object: 'chat.completion', model: 'deepseek-flash',
    choices: [{ index: 0, finish_reason: 'stop', message: { role: 'assistant', content: JSON.stringify(proposal) } }],
    usage: { prompt_tokens: 100, completion_tokens: 8, total_tokens: 108,
      prompt_cache_hit_tokens: 20, prompt_cache_miss_tokens: 80 }, ...changes }
}
function response(body = responseBody(), options = {}) {
  return new Response(JSON.stringify(body), { status: 200,
    headers: { 'content-type': 'application/json', 'x-request-id': 'request-fixture' }, ...options })
}
function admit(intent) {
  return { schema_version: 1, kind: 'p1-dispatch-admission-receipt', decision: 'allow',
    dispatch_id: intent.dispatch_id, intent_sha256: intent.intent_sha256,
    request_sha256: intent.request_sha256, admission_id: 'fixture-admission' }
}
function fixture({ body, config = loadDeepSeekConfig(), environ = env, authorizeDispatch = admit, fetchImpl } = {}) {
  const calls = []
  const complete = createDeepSeekCompletion({ config, environ, authorizeDispatch,
    fetchImpl: fetchImpl ?? (async (...args) => { calls.push(args); return response(body) }) })
  return { complete, calls }
}
const code = expected => error => {
  assert.equal(error.code, expected)
  assert.equal(error.message, expected)
  assert.equal(error.cause, undefined)
  assert.ok(!String(error.stack).includes(KEY))
  return true
}

test('offline preflight preserves unresolved runtime gates and reports only credential presence', () => {
  const report = inspectDeepSeek({ environ: env })
  assert.equal(report.credential_present, true)
  assert.equal(report.credential_access_verified, false)
  assert.equal(report.live_dispatch_ready, false)
  assert.equal(report.provider_requests, 0)
  for (const gate of ['cash_controller_not_integrated', 'native_checkpoint_missing', 'shared_reader_and_tokenizer_not_frozen']) {
    assert.ok(report.blocking_gates.includes(gate))
  }
  assert.ok(!JSON.stringify(report).includes(KEY))
  assert.equal(inspectDeepSeek({ environ: {} }).credential_present, false)
})

test('factory requires an explicit controller authorizer and rejects extra transport fields', () => {
  for (const authorizeDispatch of [undefined, null, true]) {
    assert.throws(() => createDeepSeekCompletion({ environ: env, authorizeDispatch,
      fetchImpl: () => assert.fail('must not fetch') }), code('deepseek_authorizer_required'))
  }
  for (const field of ['tools', 'headers', 'evaluator', 'private', 'base_url']) {
    assert.throws(() => createDeepSeekCompletion({ environ: env, authorizeDispatch: admit,
      fetchImpl: () => assert.fail('must not fetch'), [field]: 'forbidden' }), code('deepseek_invalid_options'))
  }
})

test('request stays bound to the official endpoint, exact model and finite limits', () => {
  const mutations = [c => { c.origin = 'https://other.invalid' }, c => { c.endpoint = '/embeddings' },
    c => { c.model = 'deepseek-chat' }, c => { c.max_tokens = 8193 }, c => { c.max_tokens = 0 },
    c => { c.limits.timeout_ms = 30001 }, c => { c.limits.timeout_ms = 0 },
    c => { c.max_retries = 1 }, c => { c.redirect = 'follow' }, c => { c.stream = true },
    c => { c.thinking.type = 'enabled' }, c => { c.tools = [] }, c => { c.limits.max_response_bytes = 0 }]
  for (const change of mutations) {
    const config = loadDeepSeekConfig(); change(config)
    assert.throws(() => validateDeepSeekConfig(config), code('deepseek_invalid_config'))
  }
})

test('missing or unsafe credentials fail before authorization and fetch', async () => {
  for (const [value, expected] of [[undefined, 'deepseek_credential_missing'], ['', 'deepseek_credential_missing'],
    ['short', 'deepseek_credential_invalid'], [KEY + '\nInjected: header', 'deepseek_credential_invalid']]) {
    const { complete, calls } = fixture({ environ: { DEEPSEEK_API_KEY: value },
      authorizeDispatch: () => assert.fail('must not authorize') })
    await assert.rejects(() => complete(prompt(input)), code(expected))
    assert.equal(calls.length, 0)
  }
})

test('denied, malformed, stale or request-unbound admission never reaches fetch', async () => {
  for (const admission of [() => null, () => ({ decision: 'deny' }), i => ({ ...admit(i), request_sha256: '0'.repeat(64) }),
    i => ({ ...admit(i), intent_sha256: '0'.repeat(64) }), i => ({ ...admit(i), dispatch_id: 'old-dispatch' }),
    i => ({ ...admit(i), api_key: KEY })]) {
    const { complete, calls } = fixture({ authorizeDispatch: admission })
    await assert.rejects(() => complete(prompt(input)), code('deepseek_dispatch_not_admitted'))
    assert.equal(calls.length, 0)
  }
  const { complete, calls } = fixture({ authorizeDispatch: () => { throw Error(KEY) } })
  await assert.rejects(() => complete(prompt(input)), code('deepseek_admission_failed'))
  assert.equal(calls.length, 0)
})

test('claims completion uses an immutable request-bound admission and emits distinct controller metadata', async () => {
  let intent
  const { complete, calls } = fixture({ authorizeDispatch: value => {
    intent = value; assert.equal(Object.isFrozen(value), true); return admit(value)
  } })
  const result = await extractClaims(input, complete)
  assert.equal(result.ok, true)
  assert.equal(result.coverageEstablished, false)
  assert.deepEqual(result.usage, { input_tokens: 100, cached_input_tokens: 20, output_tokens: 8 })
  assert.equal(calls.length, 1)
  const [url, options] = calls[0]
  assert.equal(url, 'https://api.deepseek.com/chat/completions')
  assert.equal(options.method, 'POST')
  assert.equal(options.redirect, 'error')
  assert.equal(options.credentials, 'omit')
  assert.equal(options.headers.Authorization, 'Bearer ' + KEY)
  const request = JSON.parse(options.body)
  assert.deepEqual(request.thinking, { type: 'disabled' })
  assert.deepEqual(request.response_format, { type: 'json_object' })
  assert.equal(request.model, 'deepseek-flash')
  assert.equal(request.max_tokens, 8192)
  assert.equal(request.stream, false)
  assert.equal(request.tools, undefined)
  assert.equal(intent.request_bytes, Buffer.byteLength(options.body))
  const [record] = complete.getControllerRecords()
  assert.equal(record.status, 'returned_for_claim_validation')
  assert.equal(record.request_sha256, intent.request_sha256)
  assert.equal(record.provider_request_id, 'request-fixture')
  assert.equal(record.provider_completion_id, 'chatcmpl-fixture')
  assert.equal(record.reported_model, 'deepseek-flash')
  assert.equal(record.canonical_cash_ledger_integrated, false)
  assert.equal(record.native_host, false)
  assert.ok(!JSON.stringify(record).includes(KEY))
  assert.ok(!JSON.stringify(record).includes(input.draft))
  record.usage.input_tokens = 999
  assert.equal(complete.getControllerRecords()[0].usage.input_tokens, 100)
})

test('transport accepts only the existing observable extraction prompt, without extra evaluator fields', async () => {
  for (const candidate of ['just answer this', prompt({ ...input, evaluator: 'answer key' }),
    prompt({ ...input, private: 'hidden' }), prompt({ ...input, context: [input.context] }),
    prompt({ ...input, request: KEY })]) {
    const { complete, calls } = fixture()
    await assert.rejects(() => complete(candidate), code('deepseek_prompt_contract_invalid'))
    assert.equal(calls.length, 0)
  }
  const { complete, calls } = fixture()
  await assert.rejects(() => extractClaims({ ...input, gold: 'forbidden' }, complete), /observable input/)
  assert.equal(calls.length, 0)
})

test('serialized request wrappers count toward the byte cap before authorization', async () => {
  const config = loadDeepSeekConfig(); config.limits.max_request_bytes = 100
  const { complete, calls } = fixture({ config, authorizeDispatch: () => assert.fail('must not authorize') })
  await assert.rejects(() => complete(prompt(input)), code('deepseek_request_bytes_exceeded'))
  assert.equal(calls.length, 0)
})

test('response stream bytes and content-length are bounded', async () => {
  for (const withLength of [false, true]) {
    const config = loadDeepSeekConfig(); config.limits.max_response_bytes = 100
    const { complete } = fixture({ config, fetchImpl: async () => response(responseBody(), withLength
      ? { headers: { 'content-type': 'application/json', 'content-length': '10000' } } : {}) })
    await assert.rejects(() => complete(prompt(input)), code('deepseek_response_bytes_exceeded'))
  }
})

test('an oversized declared response is cancelled before its body is read', async () => {
  const config = loadDeepSeekConfig(); config.limits.max_response_bytes = 100
  let cancelled = false
  const stream = new ReadableStream({ cancel() { cancelled = true } })
  const { complete } = fixture({ config, fetchImpl: async () => new Response(stream,
    { headers: { 'content-type': 'application/json', 'content-length': '10000' } }) })
  await assert.rejects(() => complete(prompt(input)), code('deepseek_response_bytes_exceeded'))
  assert.equal(cancelled, true)
})

test('timeout aborts a hung fetch and records one failure without retry', async () => {
  const config = loadDeepSeekConfig(); config.limits.timeout_ms = 15
  let calls = 0, signal
  const { complete } = fixture({ config, fetchImpl: async (_, options) => {
    calls++; signal = options.signal; return new Promise(() => {})
  } })
  await assert.rejects(() => complete(prompt(input)), code('deepseek_timeout'))
  assert.equal(signal.aborted, true)
  assert.equal(calls, 1)
  assert.equal(complete.getControllerRecords().length, 1)
  assert.equal(complete.getControllerRecords()[0].error_code, 'deepseek_timeout')
})

test('synchronous admission work cannot outrun the absolute deadline and then fetch', async () => {
  const config = loadDeepSeekConfig(); config.limits.timeout_ms = 5
  const { complete, calls } = fixture({ config, authorizeDispatch: intent => {
    const until = performance.now() + 25
    while (performance.now() < until) {}
    return admit(intent)
  } })
  await assert.rejects(() => complete(prompt(input)), code('deepseek_timeout'))
  assert.equal(calls.length, 0)
  assert.equal(complete.getControllerRecords()[0].fetch_started, false)
})

test('synchronous output parsing past the deadline is not recorded as success', async () => {
  const config = loadDeepSeekConfig(); config.limits.timeout_ms = 30
  const { complete } = fixture({ config })
  const originalParse = JSON.parse, output = JSON.stringify(proposal)
  let delayed = false
  JSON.parse = function (value, ...rest) {
    if (value === output) {
      delayed = true
      const until = performance.now() + 70
      while (performance.now() < until) {}
    }
    return originalParse(value, ...rest)
  }
  try {
    await assert.rejects(() => complete(prompt(input)), code('deepseek_timeout'))
  } finally {
    JSON.parse = originalParse
  }
  assert.equal(delayed, true)
  assert.equal(complete.getControllerRecords()[0].status, 'failed')
})

test('late authorization after timeout cannot start a provider request', async () => {
  const config = loadDeepSeekConfig(); config.limits.timeout_ms = 10
  const { complete, calls } = fixture({ config, authorizeDispatch: async intent => {
    await new Promise(resolve => setTimeout(resolve, 25)); return admit(intent)
  } })
  await assert.rejects(() => complete(prompt(input)), code('deepseek_timeout'))
  await new Promise(resolve => setTimeout(resolve, 35))
  assert.equal(calls.length, 0)
  assert.equal(complete.getControllerRecords()[0].fetch_started, false)
})

test('response-reading timeout cancels the stream without making another request', async () => {
  const config = loadDeepSeekConfig(); config.limits.timeout_ms = 15
  let calls = 0, cancelled = false
  const stream = new ReadableStream({ cancel() { cancelled = true } })
  const { complete } = fixture({ config, fetchImpl: async () => {
    calls++
    return new Response(stream, { headers: { 'content-type': 'application/json' } })
  } })
  await assert.rejects(() => complete(prompt(input)), code('deepseek_timeout'))
  assert.equal(calls, 1)
  assert.equal(cancelled, true)
})

test('transport and HTTP failures never expose provider error text or retry', async () => {
  for (const [fetchImpl, expected] of [[async () => { throw Error(KEY) }, 'deepseek_network_error'],
    [async () => response({ error: { message: KEY } }, { status: 401 }), 'deepseek_http_error']]) {
    let calls = 0
    const { complete } = fixture({ fetchImpl: (...args) => { calls++; return fetchImpl(...args) } })
    await assert.rejects(() => complete(prompt(input)), code(expected))
    assert.equal(calls, 1)
    assert.ok(!JSON.stringify(complete.getControllerRecords()).includes(KEY))
  }
})

test('redirected responses and unexpected response destinations are rejected', async () => {
  for (const changed of [{ redirected: true }, { url: 'https://other.invalid/chat/completions' }]) {
    const { complete } = fixture({ fetchImpl: async () => {
      const res = response(); for (const [key, value] of Object.entries(changed)) Object.defineProperty(res, key, { value })
      return res
    } })
    await assert.rejects(() => complete(prompt(input)), code('deepseek_redirect_refused'))
  }
})

test('missing usage remains null and never becomes zero measured cost', async () => {
  for (const usage of [undefined, null, {}, { prompt_tokens: 100, completion_tokens: 8 },
    { prompt_tokens: 100, completion_tokens: 8, prompt_cache_miss_tokens: 100 }]) {
    assert.equal(normalizeDeepSeekUsage(usage), null)
    const { complete } = fixture({ body: responseBody({ usage }) })
    const result = await complete(prompt(input))
    assert.equal(result.usage, null)
    assert.equal(result.controllerMetadata.usage_complete, false)
    assert.equal(result.controllerMetadata.actual_cost, null)
  }
})

test('cache and reasoning counters remain subsets, with impossible provider partitions rejected', () => {
  const valid = responseBody().usage
  for (const change of [{ prompt_tokens: -1 }, { completion_tokens: 1.5 }, { prompt_cache_hit_tokens: 101 },
    { prompt_cache_miss_tokens: 81 }, { total_tokens: 109 }, { prompt_cache_hit_tokens: '20' },
    { completion_tokens_details: { reasoning_tokens: 9 } }]) {
    assert.throws(() => normalizeDeepSeekUsage({ ...valid, ...change }), code('deepseek_usage_invalid'))
  }
  assert.deepEqual(normalizeDeepSeekUsage({ ...valid, completion_tokens_details: { reasoning_tokens: 4 } }),
    { input_tokens: 100, cached_input_tokens: 20, output_tokens: 8 })
})

test('invalid live usage and output exceeding requested max_tokens fail transparently', async () => {
  for (const usage of [{ ...responseBody().usage, prompt_cache_hit_tokens: 101 },
    { ...responseBody().usage, completion_tokens: 8193, total_tokens: 8293 }]) {
    const { complete } = fixture({ body: responseBody({ usage }) })
    await assert.rejects(() => complete(prompt(input)), code('deepseek_usage_invalid'))
  }
})

test('truncation, tools, refusal and empty or malformed JSON are not successful completions', async () => {
  const cases = [
    [{ finish_reason: 'length' }, {}, 'deepseek_output_truncated'],
    [{ finish_reason: 'tool_calls' }, {}, 'deepseek_tool_output_forbidden'],
    [{}, { tool_calls: [] }, 'deepseek_tool_output_forbidden'],
    [{}, { function_call: {} }, 'deepseek_tool_output_forbidden'],
    [{}, { refusal: 'refused' }, 'deepseek_refusal'],
    [{}, { content: '   ' }, 'deepseek_output_invalid'],
    [{}, { content: '{}' }, 'deepseek_output_invalid'],
    [{}, { content: 'not JSON' }, 'deepseek_output_invalid'],
    [{}, { content: JSON.stringify({ ...proposal, evaluator: 'hidden' }) }, 'deepseek_output_invalid'],
    [{}, { content: JSON.stringify({ claims: [], unresolved: [KEY] }) }, 'deepseek_response_invalid'],
  ]
  for (const [choiceChange, messageChange, expected] of cases) {
    const body = responseBody()
    Object.assign(body.choices[0], choiceChange)
    Object.assign(body.choices[0].message, messageChange)
    const { complete } = fixture({ body })
    await assert.rejects(() => complete(prompt(input)), code(expected))
    assert.equal(complete.getControllerRecords()[0].status, 'failed')
  }
})

test('reported model must match the frozen request and response shape must be singular', async () => {
  for (const [body, expected] of [[responseBody({ model: 'deepseek-chat' }), 'deepseek_model_mismatch'],
    [responseBody({ choices: [] }), 'deepseek_response_invalid'],
    [responseBody({ choices: [...responseBody().choices, ...responseBody().choices] }), 'deepseek_response_invalid']]) {
    const { complete } = fixture({ body })
    await assert.rejects(() => complete(prompt(input)), code(expected))
  }
})

test('server tool markers at the response or choice level are rejected as well', async () => {
  for (const location of ['response', 'choice']) {
    const body = responseBody()
    ;(location === 'response' ? body : body.choices[0]).server_tool_calls = [{ type: 'search' }]
    const { complete } = fixture({ body })
    await assert.rejects(() => complete(prompt(input)), code('deepseek_tool_output_forbidden'))
  }
})

test('escaped credential reflection is rejected after JSON decoding', async () => {
  const body = responseBody()
  body.choices[0].message.content = JSON.stringify({ claims: [], unresolved: [KEY] })
  const text = JSON.stringify(body).replace(KEY, '\\u0073' + KEY.slice(1))
  assert.ok(!text.includes(KEY))
  const { complete } = fixture({ fetchImpl: async () => new Response(text, { headers: { 'content-type': 'application/json' } }) })
  await assert.rejects(() => complete(prompt(input)), code('deepseek_response_invalid'))
  assert.ok(!JSON.stringify(complete.getControllerRecords()).includes(KEY))
})

test('credential reflection encoded inside the claims JSON is rejected before the claims parser sees it', async () => {
  const escaped = Array.from(KEY, character => '\\u' + character.charCodeAt(0).toString(16).padStart(4, '0')).join('')
  const output = JSON.stringify({ claims: [], unresolved: [KEY] }).replace(KEY, escaped)
  const body = responseBody(); body.choices[0].message.content = output
  assert.ok(!output.includes(KEY))
  assert.ok(!JSON.stringify(body).includes(KEY))
  const { complete } = fixture({ body })
  await assert.rejects(() => complete(prompt(input)), code('deepseek_response_invalid'))
  assert.ok(!JSON.stringify(complete.getControllerRecords()).includes(KEY))
})

test('duplicate JSON fields cannot hide an encoded credential in retained raw output', async () => {
  const escaped = Array.from(KEY, character => '\\u' + character.charCodeAt(0).toString(16).padStart(4, '0')).join('')
  const output = '{"claims":[],"unresolved":["' + escaped + '"],"unresolved":[]}'
  assert.ok(!JSON.stringify(JSON.parse(output)).includes(KEY))
  const body = responseBody(); body.choices[0].message.content = output
  const { complete } = fixture({ body })
  await assert.rejects(() => complete(prompt(input)), code('deepseek_response_invalid'))
})

test('existing claims grounding still rejects an ungrounded DeepSeek proposal', async () => {
  const bad = structuredClone(proposal); bad.claims[0].basis.quote = 'invented authorization'
  const body = responseBody(); body.choices[0].message.content = JSON.stringify(bad)
  const { complete, calls } = fixture({ body })
  const result = await extractClaims(input, complete)
  assert.equal(calls.length, 1)
  assert.equal(result.ok, false)
  assert.equal(result.reason, 'invalid_extraction')
  assert.equal(result.coverageEstablished, false)
})
