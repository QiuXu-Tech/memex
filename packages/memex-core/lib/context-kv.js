/**
 * KV/attention host seam (context-materialization step 4).
 *
 * API-only agents cannot expose paged KV blocks, attention sinks or prefix
 * cache keys. This module defines the explicit capability contract and a mock
 * host for tests: callers negotiate capabilities, then either page exact spans
 * through the host or fall back to the text materializer. No undocumented host
 * internals are probed; unsupported hosts fail closed.
 */
export const CONTEXT_HOST_CAPABILITIES = Object.freeze({
  pagedKV: 'paged-kv',
  attentionSinks: 'attention-sinks',
  prefixCache: 'prefix-cache',
  tokenSpans: 'token-spans',
})

export const CONTEXT_KV_VERSION = '0.12.0'

/** Negotiate a host's declared capabilities; unknown/absent ones are unavailable. */
export function negotiateContextHost(host) {
  const declared = new Set(Array.isArray(host?.capabilities) ? host.capabilities : [])
  const capabilities = Object.fromEntries(Object.values(CONTEXT_HOST_CAPABILITIES).map((capability) => [capability, declared.has(capability)]))
  return {
    host: host ?? null,
    capabilities,
    canPageKV: capabilities[CONTEXT_HOST_CAPABILITIES.pagedKV] && capabilities[CONTEXT_HOST_CAPABILITIES.tokenSpans],
    canPrefix: capabilities[CONTEXT_HOST_CAPABILITIES.prefixCache],
    canAttentionSinks: capabilities[CONTEXT_HOST_CAPABILITIES.attentionSinks],
  }
}

/** Test host: simulates paged KV blocks and prefix-cache keys. */
export class MockKvContextHost {
  constructor({ capabilities = Object.values(CONTEXT_HOST_CAPABILITIES), blockTokens = 256 } = {}) {
    this.capabilities = capabilities
    this.blockTokens = blockTokens
    this.blocks = new Map()
    this.prefixes = new Map()
    this.pages = new Map()
  }
  createBlock(id, text) { this.blocks.set(id, { id, text, tokens: Math.ceil(String(text).length / 4) }); return id }
  registerPrefix(key, blockIds) { this.prefixes.set(key, [...blockIds]); return key }
  pageIn(span, blockIds) { this.pages.set(span, [...blockIds]); return this.pages.get(span) }
  pageOut(span) { return this.pages.delete(span) }
  resolvePrefix(key) { return [...(this.prefixes.get(key) ?? [])] }
  stats() { return { blocks: this.blocks.size, prefixes: this.prefixes.size, pages: this.pages.size } }
}

/**
 * If the host declares paged KV + token spans, map materialized page spans to
 * KV blocks; otherwise return the deterministic text fallback unchanged.
 */
export function materializeWithHost(materialized, host, { prefixKey, spans = [] } = {}) {
  const negotiation = negotiateContextHost(host)
  if (negotiation.canPageKV !== true) return { mode: 'text-fallback', negotiation, materialized }
  const paged = []
  for (const [index, span] of (Array.isArray(spans) ? spans : []).entries()) {
    const blockId = `${prefixKey ?? 'ctx'}:block:${index}`
    host.createBlock?.(blockId, span.text ?? '')
    host.pageIn?.(span.id ?? `span-${index}`, [blockId])
    paged.push({ span: span.id ?? `span-${index}`, blockId })
  }
  if (negotiation.canPrefix) host.registerPrefix?.(prefixKey ?? 'ctx', paged.map((entry) => entry.blockId))
  return { mode: 'kv-paging', negotiation, materialized, paged }
}
