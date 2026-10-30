/** Reproduce the remaining query-specific archive-card omission in a fresh synthetic store. */
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { LocalStoreCore } from '../packages/memex-local/lib/store.js'
import { materializeStoreContext } from '../packages/memex-core/lib/context-pager.js'
const arg = (key) => { const i = process.argv.indexOf(`--${key}`); return i < 0 ? undefined : process.argv[i + 1] }
const root = arg('store'), output = arg('out')
if (!root || !output || existsSync(output)) throw new Error('usage: --store NEW_DIRECTORY --out NEW_FILE')
mkdirSync(root)
const store = new LocalStoreCore({ root, capacityTokens: 1_000_000, defaultLevels: { l2: false, l3: false } })
try {
  const body = '## Primary Request and Intent\n' + 'x'.repeat(6000) + '\nDEEPARCHIVECUE FACT_DEEP_ARCHIVE'
  const row = store.write({ id: 'synthetic-archive', kind: 'episode', title: 'DEEPARCHIVECUE archive', summary: 'archive for DEEPARCHIVECUE', body, tokens: 5000, workspaceKey: 'archive-probe', scope: 'workspace' })
  const result = materializeStoreContext({ store, workspaceKey: 'archive-probe', scopes: ['workspace'], query: 'DEEPARCHIVECUE', budgetTokens: 600, pageTokenCap: 100 })
  const out = { kind: 'synthetic-archive-card-omission', candidate: result.sources.some((x) => x.recordId === row.id), included: result.includedIds.includes(row.id), factPresent: result.text.includes('FACT_DEEP_ARCHIVE'), source: result.sources.find((x) => x.recordId === row.id)?.source, originalBodyHasFact: store.get(row.id).body.includes('FACT_DEEP_ARCHIVE'), budgetTokens: 600, pageTokenCap: 100, note: 'Query cue and fact occur deep in an oversized episode body; the card should retain a source-marked query-relevant excerpt.' }
  writeFileSync(output, JSON.stringify(out, null, 2)); console.log(JSON.stringify(out))
} finally { store.close() }
