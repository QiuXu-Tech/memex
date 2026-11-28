/**
 * Bounded DeepSeek extraction transport, not an implemented P1 method runner.
 *
 * Importing this module and inspectDeepSeek() make no requests. There is no CLI.
 * The completion factory requires a controller admission callback before fetch.
 * A callback receipt is a tested integration seam, NOT an authorization boundary
 * or proof that the canonical CNY100 cash ledger has been integrated. The caller
 * must durably enforce real scope, cash and attempt limits before returning it.
 * Nothing here creates native compaction, a shared reader, or a Raw-RAG baseline.
 * Credentials come only from the supplied process environment, never env files.
 */
import { createHash, randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { EXTRACTION_INSTRUCTIONS } from './claims.mjs'

const ORIGIN = 'https://api.deepseek.com'
const ENDPOINT = '/chat/completions'
const MODEL = 'deepseek-flash'
const PROMPT_PREFIX = `${EXTRACTION_INSTRUCTIONS}\n\nOBSERVABLE_INPUT_JSON\n`
const CODES = new Set([
  'deepseek_invalid_options', 'deepseek_invalid_config', 'deepseek_config_unavailable',
  'deepseek_authorizer_required', 'deepseek_credential_missing', 'deepseek_credential_invalid',
  'deepseek_prompt_contract_invalid', 'deepseek_request_bytes_exceeded',
  'deepseek_dispatch_not_admitted', 'deepseek_admission_failed', 'deepseek_timeout',
  'deepseek_network_error', 'deepseek_http_error', 'deepseek_redirect_refused',
  'deepseek_response_bytes_exceeded', 'deepseek_response_invalid', 'deepseek_model_mismatch',
  'deepseek_output_truncated', 'deepseek_tool_output_forbidden', 'deepseek_refusal',
  'deepseek_output_not_stopped', 'deepseek_output_invalid', 'deepseek_usage_invalid',
  'deepseek_internal_error',
])
export class DeepSeekError extends Error {
  constructor(code) {
    const safe = CODES.has(code) ? code : 'deepseek_internal_error'
    super(safe)
    this.name = 'DeepSeekError'
    this.code = safe
  }
}
const fail = code => { throw new DeepSeekError(code) }
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value)
  && [Object.prototype, null].includes(Object.getPrototypeOf(value))
const exact = (value, keys) => plain(value) && Object.keys(value).length === keys.length
  && keys.every(key => Object.hasOwn(value, key))
const subset = (value, keys) => plain(value) && Object.keys(value).every(key => keys.includes(key))
const bounded = (value, maximum) => Number.isSafeInteger(value) && value > 0 && value <= maximum
const count = value => Number.isSafeInteger(value) && value >= 0
const hashBytes = value => createHash('sha256').update(value).digest('hex')
const canonical = value => {
  if (Array.isArray(value)) return value.map(canonical)
  if (plain(value)) return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]))
  return value
}
const hashObject = value => hashBytes(JSON.stringify(canonical(value)))
function deepFreeze(value) {
  if (value && typeof value === 'object') {
    for (const child of Object.values(value)) deepFreeze(child)
    Object.freeze(value)
  }
  return value
}
function safeLabel(value, secret) {
  return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/.test(value)
    && !value.startsWith('sk-') && !(secret && value.includes(secret)) ? value : null
}
function containsCredential(text, secret) {
  // Scan encoded text as well as parsed objects: JSON duplicate keys can discard
  // a reflected value while leaving it in rawOutput retained by extractClaims().
  return text.includes(secret) || text.replace(/\\u([0-9a-f]{4})/gi,
    (_, digits) => String.fromCharCode(Number.parseInt(digits, 16))).includes(secret)
}

export function loadDeepSeekConfig() {
  try {
    return validateDeepSeekConfig(JSON.parse(readFileSync(new URL('./deepseek-config.json', import.meta.url), 'utf8')))
  } catch (error) {
    throw new DeepSeekError(error instanceof DeepSeekError ? error.code : 'deepseek_config_unavailable')
  }
}

export function validateDeepSeekConfig(config) {
  try {
    if (!exact(config, ['schema_version', 'implementation', 'provider', 'origin', 'endpoint', 'model',
      'api_key_env', 'thinking', 'response_format', 'temperature', 'stream', 'max_tokens',
      'max_retries', 'redirect', 'limits', 'documentation'])
      || config.schema_version !== 1 || config.implementation !== 'p1-deepseek-extraction-transport-v1'
      || config.provider !== 'deepseek' || config.origin !== ORIGIN || config.endpoint !== ENDPOINT
      || config.model !== MODEL || config.api_key_env !== 'DEEPSEEK_API_KEY'
      || !exact(config.thinking, ['type']) || config.thinking.type !== 'disabled'
      || !exact(config.response_format, ['type']) || config.response_format.type !== 'json_object'
      || config.temperature !== 0 || config.stream !== false || config.max_retries !== 0
      || config.redirect !== 'error' || !bounded(config.max_tokens, 8192)
      || !exact(config.limits, ['max_request_bytes', 'max_response_bytes', 'timeout_ms'])
      || !bounded(config.limits.max_request_bytes, 262144)
      || !bounded(config.limits.max_response_bytes, 1048576)
      || !bounded(config.limits.timeout_ms, 30000)
      || !exact(config.documentation, ['checked_date', 'model_alias_target', 'api_source', 'pricing_source'])
      || config.documentation.checked_date !== '2026-11-28'
      || config.documentation.model_alias_target !== 'DeepSeek-V4.1-Flash-1017'
      || config.documentation.api_source !== 'https://api-docs.deepseek.com/api/create-chat-completion/'
      || config.documentation.pricing_source !== 'https://api-docs.deepseek.com/quick_start/pricing/') {
      fail('deepseek_invalid_config')
    }
    return config
  } catch {
    fail('deepseek_invalid_config')
  }
}

export function inspectDeepSeek(options = {}) {
  if (!subset(options, ['config', 'environ'])) fail('deepseek_invalid_options')
  const config = validateDeepSeekConfig(options.config ?? loadDeepSeekConfig())
  const environ = options.environ ?? process.env
  const present = typeof environ?.[config.api_key_env] === 'string' && environ[config.api_key_env].trim().length > 0
  return { schema_version: 1, kind: 'zero_call_deepseek_preflight', provider: 'deepseek', model: MODEL,
    endpoint: ORIGIN + ENDPOINT, config_sha256: hashObject(config), credential_present: present,
    credential_access_verified: false, environment_files_read: false, provider_requests: 0,
    live_dispatch_ready: false, native_host: false, canonical_cash_ledger_integrated: false,
    blocking_gates: ['cash_controller_not_integrated', 'native_checkpoint_missing',
      'shared_reader_and_tokenizer_not_frozen', 'all_arm_runtime_not_integrated',
      ...(present ? [] : ['deepseek_credential_missing'])],
    tokenizer_note: 'Byte limits are not exact model-token measurements.', actual_cost: null }
}

/** Cached input and reasoning output are subsets, never extra additive usage.
 * Missing counters remain unknown. Even a known miss count does not manufacture
 * a missing hit counter. Partial numeric observations are retained separately.
 */
export function normalizeDeepSeekUsage(usage) {
  if (usage === undefined || usage === null) return null
  if (!plain(usage)) fail('deepseek_usage_invalid')
  for (const key of ['prompt_tokens', 'completion_tokens', 'total_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens']) {
    if (Object.hasOwn(usage, key) && !count(usage[key])) fail('deepseek_usage_invalid')
  }
  const input = usage.prompt_tokens, output = usage.completion_tokens
  const hit = usage.prompt_cache_hit_tokens, miss = usage.prompt_cache_miss_tokens
  if ((count(input) && count(hit) && hit > input) || (count(input) && count(miss) && miss > input)
    || (count(input) && count(hit) && count(miss) && hit + miss !== input)
    || (count(input) && count(output) && Object.hasOwn(usage, 'total_tokens') && usage.total_tokens !== input + output)) {
    fail('deepseek_usage_invalid')
  }
  if (Object.hasOwn(usage, 'completion_tokens_details')) {
    const details = usage.completion_tokens_details
    if (!plain(details) || (Object.hasOwn(details, 'reasoning_tokens')
      && (!count(details.reasoning_tokens) || (count(output) && details.reasoning_tokens > output)))) {
      fail('deepseek_usage_invalid')
    }
  }
  return [input, hit, output].every(count)
    ? { input_tokens: input, cached_input_tokens: hit, output_tokens: output } : null
}

function numericUsage(usage) {
  if (!plain(usage)) return null
  const result = Object.fromEntries(['prompt_tokens', 'completion_tokens', 'total_tokens',
    'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens'].filter(key => count(usage[key])).map(key => [key, usage[key]]))
  if (count(usage.completion_tokens_details?.reasoning_tokens)) result.reasoning_tokens = usage.completion_tokens_details.reasoning_tokens
  return Object.keys(result).length ? result : null
}

function credential(environ) {
  const value = environ?.DEEPSEEK_API_KEY
  if (value === undefined || value === '') fail('deepseek_credential_missing')
  // Shape validation prevents whitespace/header injection; it is not an access check.
  if (typeof value !== 'string' || !/^sk-[A-Za-z0-9_-]{16,509}$/.test(value)) fail('deepseek_credential_invalid')
  return value
}

function validatePrompt(prompt, secret) {
  if (typeof prompt !== 'string' || !prompt.startsWith(PROMPT_PREFIX) || containsCredential(prompt, secret)) fail('deepseek_prompt_contract_invalid')
  try {
    const serialized = prompt.slice(PROMPT_PREFIX.length), input = JSON.parse(serialized)
    if (!exact(input, ['request', 'draft', 'context', 'toolDescriptions'])
      || !['request', 'draft', 'context'].every(key => typeof input[key] === 'string')
      || !Array.isArray(input.toolDescriptions) || !input.toolDescriptions.every(value => typeof value === 'string')
      || JSON.stringify(input) !== serialized) fail('deepseek_prompt_contract_invalid')
  } catch {
    fail('deepseek_prompt_contract_invalid')
  }
}

function validAdmission(receipt, intent, secret) {
  return exact(receipt, ['schema_version', 'kind', 'decision', 'dispatch_id', 'intent_sha256', 'request_sha256', 'admission_id'])
    && receipt.schema_version === 1 && receipt.kind === 'p1-dispatch-admission-receipt' && receipt.decision === 'allow'
    && receipt.dispatch_id === intent.dispatch_id && receipt.intent_sha256 === intent.intent_sha256
    && receipt.request_sha256 === intent.request_sha256 && safeLabel(receipt.admission_id, secret) !== null
}

function cancelResponse(response) {
  try {
    if (response?.body && !response.body.locked && typeof response.body.cancel === 'function') {
      Promise.resolve(response.body.cancel()).catch(() => {})
    }
  } catch {}
}

async function boundedBody(response, maximum, signal, checkDeadline) {
  checkDeadline()
  const length = response.headers?.get('content-length')
  if (length !== null && length !== undefined) {
    if (!/^\d+$/.test(length)) fail('deepseek_response_invalid')
    if (!Number.isSafeInteger(Number(length)) || Number(length) > maximum) fail('deepseek_response_bytes_exceeded')
  }
  if (!response.body || typeof response.body.getReader !== 'function') fail('deepseek_response_invalid')
  const reader = response.body.getReader()
  const cancel = () => { try { Promise.resolve(reader.cancel()).catch(() => {}) } catch {} }
  signal.addEventListener('abort', cancel, { once: true })
  const chunks = []; let bytes = 0
  try {
    while (true) {
      checkDeadline()
      const { done, value } = await reader.read()
      checkDeadline()
      if (done) break
      if (!(value instanceof Uint8Array)) fail('deepseek_response_invalid')
      bytes += value.byteLength
      if (bytes > maximum) { cancel(); fail('deepseek_response_bytes_exceeded') }
      chunks.push(value)
    }
    try { return new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks, bytes)) }
    catch { fail('deepseek_response_invalid') }
  } finally {
    signal.removeEventListener('abort', cancel)
    try { reader.releaseLock() } catch {}
  }
}

function parseResponse(text, config, context, secret) {
  if (containsCredential(text, secret)) fail('deepseek_response_invalid')
  let body
  try { body = JSON.parse(text) } catch { fail('deepseek_response_invalid') }
  if (!plain(body) || body.object !== 'chat.completion') fail('deepseek_response_invalid')
  context.provider_usage = numericUsage(body.usage)
  context.usage = normalizeDeepSeekUsage(body.usage)
  context.usage_complete = context.usage !== null
  if (count(body.usage?.completion_tokens) && body.usage.completion_tokens > config.max_tokens) fail('deepseek_usage_invalid')
  const toolMarker = object => ['tool_calls', 'function_call', 'server_tool_calls', 'tools'].some(key => Object.hasOwn(object, key))
  if (toolMarker(body)) fail('deepseek_tool_output_forbidden')
  if (body.model !== config.model) fail('deepseek_model_mismatch')
  context.reported_model = body.model
  context.provider_completion_id = safeLabel(body.id, secret)
  if (!context.provider_completion_id || !Array.isArray(body.choices) || body.choices.length !== 1) fail('deepseek_response_invalid')
  const choice = body.choices[0], message = choice?.message
  if (!plain(choice) || choice.index !== 0 || !plain(message) || message.role !== 'assistant') fail('deepseek_response_invalid')
  if (toolMarker(choice) || toolMarker(message)) fail('deepseek_tool_output_forbidden')
  if (choice.finish_reason === 'length') fail('deepseek_output_truncated')
  if (['tool_calls', 'function_call'].includes(choice.finish_reason)) fail('deepseek_tool_output_forbidden')
  if (choice.finish_reason === 'content_filter' || (message.refusal !== undefined && message.refusal !== null && message.refusal !== '')) fail('deepseek_refusal')
  if (choice.finish_reason !== 'stop') fail('deepseek_output_not_stopped')
  if (message.reasoning_content !== undefined && message.reasoning_content !== null && message.reasoning_content !== '') fail('deepseek_response_invalid')
  const output = message.content
  if (typeof output !== 'string' || !output.trim()) fail('deepseek_output_invalid')
  if (containsCredential(output, secret)) fail('deepseek_response_invalid')
  let parsed
  try { parsed = JSON.parse(output) } catch { fail('deepseek_output_invalid') }
  // A JSON-string response can contain a second layer of escaped credentials.
  // Check decoded fields before extractClaims() can expose them to its caller.
  if (JSON.stringify(parsed).includes(secret)) fail('deepseek_response_invalid')
  if (!exact(parsed, ['claims', 'unresolved']) || !Array.isArray(parsed.claims) || parsed.claims.length > 16
    || !Array.isArray(parsed.unresolved) || !parsed.unresolved.every(value => typeof value === 'string')) fail('deepseek_output_invalid')
  // The existing extractClaims() remains responsible for typed claims and grounding.
  return output
}

export function createDeepSeekCompletion(options = {}) {
  if (!subset(options, ['config', 'environ', 'fetchImpl', 'authorizeDispatch'])) fail('deepseek_invalid_options')
  if (typeof options.authorizeDispatch !== 'function') fail('deepseek_authorizer_required')
  const config = deepFreeze(structuredClone(validateDeepSeekConfig(options.config ?? loadDeepSeekConfig())))
  const environ = options.environ ?? process.env, fetchImpl = options.fetchImpl ?? globalThis.fetch
  if (typeof fetchImpl !== 'function') fail('deepseek_invalid_options')
  const authorizeDispatch = options.authorizeDispatch, records = []

  const complete = async prompt => {
    const started = performance.now(), deadline = started + config.limits.timeout_ms
    const secret = credential(environ)
    if (typeof prompt === 'string' && Buffer.byteLength(prompt) > config.limits.max_request_bytes) fail('deepseek_request_bytes_exceeded')
    validatePrompt(prompt, secret)
    const body = JSON.stringify({ model: config.model, messages: [{ role: 'user', content: prompt }],
      thinking: config.thinking, response_format: config.response_format, temperature: config.temperature,
      stream: false, max_tokens: config.max_tokens })
    const bytes = Buffer.byteLength(body)
    if (bytes > config.limits.max_request_bytes) fail('deepseek_request_bytes_exceeded')
    const initialIntent = { schema_version: 1, kind: 'p1-deepseek-extraction-intent', dispatch_id: randomUUID(),
      provider: 'deepseek', model: config.model, endpoint: ORIGIN + ENDPOINT,
      request_sha256: hashBytes(body), request_bytes: bytes, max_output_tokens: config.max_tokens,
      max_response_bytes: config.limits.max_response_bytes, timeout_ms: config.limits.timeout_ms }
    const intent = deepFreeze({ ...initialIntent, intent_sha256: hashObject(initialIntent) })
    const context = { schema_version: 1, kind: 'p1-deepseek-controller-record', provider: 'deepseek',
      requested_model: config.model, reported_model: null, dispatch_id: intent.dispatch_id,
      request_sha256: intent.request_sha256, intent_sha256: intent.intent_sha256, config_sha256: hashObject(config),
      admission_id: null, fetch_started: false, http_status: null, provider_request_id: null, provider_completion_id: null,
      usage: null, provider_usage: null, usage_complete: false, actual_cost: null,
      canonical_cash_ledger_integrated: false, native_host: false, native_compaction: false }
    const controller = new AbortController()
    // Timers alone cannot stop a synchronously blocking callback or JSON parse:
    // their microtask continuation can otherwise dispatch before timers resume.
    const checkDeadline = () => {
      if (controller.signal.aborted || performance.now() >= deadline) {
        controller.abort()
        fail('deepseek_timeout')
      }
    }
    let timer
    const expired = new Promise((_, reject) => { timer = setTimeout(() => {
      controller.abort(); reject(new DeepSeekError('deepseek_timeout'))
    }, Math.max(0, deadline - performance.now())) })
    const work = async () => {
      checkDeadline()
      let receipt
      try { receipt = await authorizeDispatch(intent) } catch { checkDeadline(); fail('deepseek_admission_failed') }
      checkDeadline()
      if (!validAdmission(receipt, intent, secret)) fail('deepseek_dispatch_not_admitted')
      context.admission_id = receipt.admission_id
      let response
      checkDeadline()
      context.fetch_started = true
      try {
        response = await fetchImpl(ORIGIN + ENDPOINT, { method: 'POST', redirect: 'error', credentials: 'omit',
          headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + secret },
          body, signal: controller.signal })
      } catch { checkDeadline(); fail('deepseek_network_error') }
      try {
        checkDeadline()
        if (!response || !Number.isInteger(response.status) || response.status < 100 || response.status > 599) fail('deepseek_response_invalid')
        context.http_status = response.status
        if (response.redirected === true || (response.url && response.url !== ORIGIN + ENDPOINT)) fail('deepseek_redirect_refused')
        context.provider_request_id = safeLabel(response.headers?.get('x-request-id'), secret)
        if (response.status < 200 || response.status >= 300) fail('deepseek_http_error')
        if (!/^application\/json(?:;|$)/i.test(response.headers?.get('content-type') ?? '')) fail('deepseek_response_invalid')
        const text = await boundedBody(response, config.limits.max_response_bytes, controller.signal, checkDeadline)
        checkDeadline()
        const result = parseResponse(text, config, context, secret)
        checkDeadline()
        return result
      } finally {
        cancelResponse(response)
      }
    }
    try {
      const text = await Promise.race([work(), expired])
      checkDeadline()
      const record = deepFreeze({ ...context, status: 'returned_for_claim_validation', error_code: null,
        elapsed_ms: Math.ceil(performance.now() - started) })
      records.push(record)
      return { text, usage: structuredClone(record.usage), controllerMetadata: structuredClone(record) }
    } catch (error) {
      const safe = new DeepSeekError(performance.now() >= deadline ? 'deepseek_timeout'
        : error instanceof DeepSeekError ? error.code : 'deepseek_response_invalid')
      records.push(deepFreeze({ ...context, status: 'failed', error_code: safe.code,
        elapsed_ms: Math.ceil(performance.now() - started) }))
      throw safe
    } finally {
      clearTimeout(timer)
      controller.abort()
    }
  }
  Object.defineProperty(complete, 'getControllerRecords', { value: () => structuredClone(records) })
  return complete
}
