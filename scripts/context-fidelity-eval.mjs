#!/usr/bin/env node
// Offline structural-fidelity evaluation for context materialization (step 5).
// No provider calls: checks canonical-event round-trip, chronology, stable
// prefix, pager canonical coverage and KV-host negotiation behavior.
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { LocalStoreCore } from '../packages/memex-core/lib/store.js'
import { canonicalEventsFromDsh, deserializeContextEvent, serializeContextEvent } from '../packages/memex-core/lib/context-events.js'
import { materializeStoreContext } from '../packages/memex-core/lib/context-pager.js'
import { materializeContext } from '../packages/memex-core/lib/context-materializer.js'
import { MockKvContextHost, negotiateContextHost, materializeWithHost } from '../packages/memex-core/lib/context-kv.js'
import { memoryWorkspaceKey } from '../packages/memex-core/index.js'

const OUT = process.argv.includes('--out') ? process.argv[process.argv.indexOf('--out') + 1] : 'docs/assets/benchmarks/context-fidelity.json'
const root = mkdtempSync(join(tmpdir(), 'memex-fidelity-'))
const store = new LocalStoreCore({ root, capacityTokens: 1_000_000, sessionCapacityTokens: 1_000_000, defaultLevels: { l2: false, l3: false } })
const workspaceKey = memoryWorkspaceKey('/tmp/fidelity-ws', 'fidelity')
const record = store.write({ kind: 'episode', title: 'fidelity record', body: 'rendered fallback body', workspaceKey, scope: 'workspace', tokens: 10 })
const raw = [
  { seq: 2, message: { role: 'user', content: [{ type: 'text', text: 'exact user event' }] } },
  { seq: 3, message: { role: 'assistant', content: [{ type: 'tool-call', id: 'call-1', name: 'memory_search', arguments: { query: 'billing retry' } }] } },
  { seq: 4, message: { role: 'tool', content: [{ type: 'text', text: 'tool result text' }] } },
  { seq: 5, message: { role: 'assistant', content: [{ type: 'text', text: 'final assistant text' }] } },
]
const canonical = canonicalEventsFromDsh(raw, { sessionId: 'fidelity', recordId: record.id })
store.appendContextEvents({ recordId: record.id, events: canonical })
const listed = store.listContextEvents(record.id)
const roundTrip = listed.map((event) => {
  const decoded = deserializeContextEvent(serializeContextEvent(event))
  return decoded.checksum === event.checksum && decoded.content === event.content && decoded.role === event.role
})
const pager = materializeStoreContext({ store, workspaceKey, scopes: ['workspace'], budgetTokens: 4000 })
const first = materializeContext({ pages: listed.map((event) => ({ id: event.id, body: event.content, sequence: event.sequence, title: `${event.role}/${event.type}` })), budgetTokens: 4000 })
const second = materializeContext({ pages: listed.map((event) => ({ id: event.id, body: event.content, sequence: event.sequence, title: `${event.role}/${event.type}` })), budgetTokens: 4000 })
const positions = listed.map((event) => pager.text.indexOf(event.content))
const chronology = positions.every((position, index) => position >= 0 && (index === 0 || position > positions[index - 1]))
const mockHost = new MockKvContextHost()
const paged = materializeWithHost(first, mockHost, { prefixKey: 'fidelity-prefix', spans: listed.map((event) => ({ id: event.id, text: event.content })) })
const stats = mockHost.stats()
const capable = negotiateContextHost(mockHost)
const fallback = negotiateContextHost({ capabilities: [] })
const report = {
  generatedAt: new Date().toISOString(),
  kind: 'context-fidelity-offline',
  checks: {
    canonicalEvents: canonical.length,
    persistedEvents: listed.length,
    eventRoundTripExact: roundTrip.every(Boolean),
    chronologyExact: chronology,
    stablePrefixDeterministic: first.stablePrefixHash === second.stablePrefixHash,
    pagerCanonicalSources: pager.sources.filter((source) => source.source === 'canonical').length,
    pagerUsesCanonicalEvents: pager.text.includes('exact user event') && pager.text.includes('tool result text'),
  },
  kv: {
    capableCanPageKV: capable.canPageKV,
    capableCanPrefix: capable.canPrefix,
    textOnlyFailsClosed: fallback.canPageKV === false,
    mockBlocks: stats.blocks,
    mockMode: paged.mode,
  },
  caveats: ['Offline structural fidelity only; no provider/model calls.', 'Transformer context specialist is an interface slot (heuristic/linear baseline), not a trained model.', 'KV paging is a mock host contract; real hosts must opt in.'],
}
writeFileSync(OUT, JSON.stringify(report, null, 2) + '\n')
store.close()
rmSync(root, { recursive: true, force: true })
console.log(JSON.stringify(report, null, 2))
