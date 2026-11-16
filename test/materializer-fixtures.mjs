export const BENCHMARK_SEEDS = [11, 29, 47, 83, 101]

export function random(seed) {
  let state = seed >>> 0
  return () => { state ^= state << 13; state ^= state >>> 17; state ^= state << 5; return (state >>> 0) / 4294967296 }
}

export function pagesFor({ n, streams, chars, tools = false }, seed) {
  const rng = random(seed)
  const pages = Array.from({ length: n }, (_, i) => {
    const stream = i % streams, sequence = Math.floor(i / streams)
    const page = { id: `p-${String(i).padStart(6, '0')}`, recordId: `r-${Math.floor(i / 4)}`, sequence,
      blockIndex: 0, createdAt: sequence * 100 + stream + (sequence % 9 === 0 ? -200 : 0),
      title: `Note ${i}`, body: ('context 汉😀 evidence '.repeat(Math.ceil(chars / 23))).slice(0, chars), role: i % 2 ? 'user' : 'assistant' }
    if (streams !== n) page.sessionId = `s-${stream}`
    if (tools && sequence % 3 < 2) {
      page.type = sequence % 3 === 0 ? 'tool_call' : 'tool_result'
      page.toolCallId = `t-${stream}-${Math.floor(sequence / 3)}`
    }
    return page
  })
  for (let i = pages.length - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [pages[i], pages[j]] = [pages[j], pages[i]] }
  return pages
}

export const BENCHMARK_CASES = [
  { name: 'order-singletons', kind: 'order', n: 5000, streams: 5000, chars: 0 },
  { name: 'order-streams', kind: 'order', n: 5000, streams: 64, chars: 0 },
  { name: 'materialize-wide', n: 512, streams: 512, chars: 512, budget: 1000000 },
  { name: 'materialize-tight', n: 2048, streams: 64, chars: 256, budget: 2400 },
  { name: 'materialize-small', n: 24, streams: 8, chars: 128, budget: 2400 },
  { name: 'materialize-custom', n: 128, streams: 8, chars: 64, budget: 2400, custom: true },
  { name: 'materialize-tools', n: 512, streams: 8, chars: 64, budget: 50000, tools: true },
]

export function inputFor(spec, seed) {
  const input = { pages: pagesFor(spec, seed), budgetTokens: spec.budget, enforceTotalBudget: true }
  if (spec.custom) input.tokenCounter = text => Math.ceil(Array.from(text).length / 3) + (text.split('\n').length % 3)
  return input
}
