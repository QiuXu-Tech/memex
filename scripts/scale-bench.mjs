/**
 * Synthetic scale benchmark for the extra-context store.
 *
 * Generates a throwaway database (no live data touched) and measures the paths
 * that matter at pool scale: open/migrate, writes, hot/cold capacity split,
 * catalog/search/list/grep/get latency, cold compression and cold GC.
 *
 * Usage:
 *   node scripts/scale-bench.mjs                    # 1000 records, 10k tokens each (≈10M tokens, pool capacity = total)
 *   node scripts/scale-bench.mjs --records 2000 --tokens 5000
 *   node scripts/scale-bench.mjs --target 0.6 --gc 0.5
 */
import { mkdtempSync, rmSync, statSync, readdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { performance } from 'node:perf_hooks'
import { LocalStoreCore } from '../packages/dsh-memory-local/lib/store.js'

const arg = (name, fallback) => {
  const index = process.argv.indexOf(`--${name}`)
  return index >= 0 ? Number(process.argv[index + 1]) : fallback
}
const RECORDS = Math.max(1, arg('records', 1000))
const TOKENS = Math.max(10, arg('tokens', 10_000))
const CAPACITY = Math.max(RECORDS * TOKENS, arg('capacity', RECORDS * TOKENS))
const TARGET = Math.min(Math.max(arg('target', 0.3), 0.01), 0.95)
const GC_KEEP = Math.min(Math.max(arg('gc', 0.5), 0), 1)
console.log(`scale: ${RECORDS} records × ${TOKENS} tokens (${(RECORDS * TOKENS / 1_000_000).toFixed(1)}M tokens), pool capacity ${(CAPACITY / 1_000_000).toFixed(1)}M, target ratio ${TARGET}, gc keep ${GC_KEEP}`)

const root = mkdtempSync(join(tmpdir(), 'mem-scale-'))
const core = new LocalStoreCore({ root, capacityTokens: CAPACITY, sessionCapacityTokens: 10_000_000, defaultLevels: { l2: false, l3: false } })
const workspaceKey = 'bench-wk'
const sessionId = 'bench-session'
const body = 'x'.repeat(Math.max(400, TOKENS * 4))
const timing = (label, fn, runs = 5) => {
  const times = []
  let out
  for (let i = 0; i < runs; i += 1) {
    const started = performance.now()
    out = fn()
    times.push(performance.now() - started)
  }
  times.sort((a, b) => a - b)
  console.log(`${label}: median ${times[Math.floor(runs / 2)].toFixed(2)}ms p95 ${times[Math.max(0, times.length - 2)].toFixed(2)}ms`)
  return out
}
const dirSize = (dir) => {
  let bytes = 0
  const walk = (current) => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const path = join(current, entry.name)
      if (entry.isDirectory()) walk(path)
      else bytes += statSync(path).size
    }
  }
  try { walk(dir) } catch {}
  return bytes
}

try {
  const writeStart = performance.now()
  for (let index = 0; index < RECORDS; index += 1) {
    core.write({
      kind: index % 5 === 0 ? 'episode' : index % 3 === 0 ? 'fact' : 'artifact',
      title: `bench record ${index} topic ${index % 50}`,
      summary: `synthetic summary ${index} alpha beta gamma`,
      useWhen: `read when continuing topic ${index % 50}`,
      body,
      tokens: TOKENS,
      workspaceKey,
      sessionId,
      scope: 'workspace',
    })
  }
  console.log(`write: ${RECORDS} records / ${(RECORDS * TOKENS / 1_000_000).toFixed(1)}M tokens in ${((performance.now() - writeStart) / 1000).toFixed(1)}s`)
  console.log(`db after write: ${(statSync(join(root, 'index.db')).size / 1048576).toFixed(1)} MiB, records dir ${(dirSize(join(root, 'records')) / 1048576).toFixed(1)} MiB`)
  console.log('== reads ==')
  timing('facets', () => core.facets({ workspaceKey, scope: 'workspace' }))
  timing('list 20', () => core.list({ workspaceKey, scope: 'workspace', limit: 20 }))
  timing('catalog', () => core.catalog({ workspaceKey, scopes: ['workspace'], maxChars: 2400 }))
  timing('search title term "topic 7"', () => core.search({ query: 'topic 7', workspaceKey, scope: 'workspace', limit: 8 }))
  timing('search ascii "alpha beta"', () => core.search({ query: 'alpha beta', workspaceKey, scope: 'workspace', limit: 8 }))
  timing('search CJK "记忆"', () => core.search({ query: '记忆', workspaceKey, scope: 'workspace', limit: 8 }))
  timing('grep body "xxxxxxxx"', () => core.grep({ pattern: 'xxxx', workspaceKey, scope: 'workspace', limit: 20 }))
  const sample = core.list({ workspaceKey, scope: 'workspace', limit: 1 })[0]
  timing('get record', () => core.get(sample.id))

  console.log('== compression ==')
  const coldStart = performance.now()
  const cold = core.compressCold({ workspaceKey, scope: 'workspace', targetRatio: TARGET, minAgeMs: 0, limit: RECORDS })
  console.log(`compressCold: moved ${cold.coldMoved.length} records, freed ${(cold.freedTokens / 1_000_000).toFixed(2)}M tokens in ${((performance.now() - coldStart) / 1000).toFixed(2)}s`)
  const after = core.facets({ workspaceKey, scope: 'workspace' })
  console.log(`hot ${(after.hotTokens / 1_000_000).toFixed(2)}M / cold ${(after.coldTokens / 1_000_000).toFixed(2)}M tokens; cold files ${(dirSize(join(root, 'cold')) / 1048576).toFixed(1)} MiB; db ${(statSync(join(root, 'index.db')).size / 1048576).toFixed(1)} MiB`)
  timing('search after cold (card fields)', () => core.search({ query: 'alpha beta', workspaceKey, scope: 'workspace', limit: 8 }))
  timing('catalog after cold', () => core.catalog({ workspaceKey, scopes: ['workspace'], maxChars: 2400 }))

  console.log('== cold gc ==')
  const gcStart = performance.now()
  const gc = core.gcCold({ workspaceKey, scope: 'workspace', keepTokens: Math.floor(after.coldTokens * GC_KEEP) })
  console.log(`gcCold: removed ${gc.removed.length} records, freed ${(gc.freedTokens / 1_000_000).toFixed(2)}M cold tokens in ${((performance.now() - gcStart) / 1000).toFixed(2)}s`)
  console.log(`db after gc: ${(statSync(join(root, 'index.db')).size / 1048576).toFixed(1)} MiB`)
} finally {
  core.close()
  rmSync(root, { recursive: true, force: true })
}
