import { spawn } from 'node:child_process'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir, loadavg } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { performance } from 'node:perf_hooks'
import { LocalStoreCore } from '../packages/dsh-memory-core/lib/store.js'
import { memoryWorkspaceKey } from '../packages/dsh-memory-core/index.js'
import { resolveModelProfile, profileTokens } from '../packages/dsh-memory-core/lib/model-profiles.js'
import { buildCatalogInjection, buildMemoryManual } from '../packages/dsh-memory-core/lib/manual.js'

const N = process.execPath
const OUT = process.argv[2] ?? join(tmpdir(), 'dsh-memory-profile-validation.json')
const ROOT_GIT = resolve(fileURLToPath(new URL('..', import.meta.url)))
const REG = join(ROOT_GIT, 'test/register.mjs')
const MCP = join(ROOT_GIT, 'packages/dsh-memory-mcp/bin/server.mjs')
const CWD = join(tmpdir(), 'dsh-memory-profile-ws')
const SESSION = 'val-session'
const WS = memoryWorkspaceKey(CWD, SESSION)
const ROOT = join(tmpdir(), 'dsh-memory-profile-root')
const profiles = ['claude', 'claude-opus-5-5', 'claude-sonnet-5-5', 'claude-fable-5-1', 'claude-haiku-5-5', 'openai', 'gpt-6.1', 'gpt-6.1-terra', 'gpt-6-astra', 'deepseek', 'deepseek-flash', 'generic']

rmSync(ROOT, { recursive: true, force: true })
const core = new LocalStoreCore({ root: ROOT, capacityTokens: 1_000_000_000, sessionCapacityTokens: 100_000_000, defaultLevels: { l2: false, l3: false } })
// distractor + body-answer fixture (identifier-like answers in body)
const topics = ['deployment', 'billing', 'telemetry', 'migration', 'rollback', 'quota', 'sandbox', 'webhook']
for (let index = 0; index < 120; index += 1) {
  core.write({ kind: 'episode', title: `deployment retry budget incident INC-${index} report`, summary: `deployment retry budget incident INC-${index} review`, useWhen: 'read when continuing deployment retry budget work', body: `generic retrospective notes about ${topics[index % topics.length]} and retry policy`, workspaceKey: WS, scope: 'workspace', tokens: 30 })
}
const bodyAnswers = []
for (let index = 0; index < 120; index += 1) {
  bodyAnswers.push(core.write({ kind: 'fact', title: `turn ${index} note`, body: `The retry budget for incident INC-${index} is ANSWER-${index}-zq. Deployment retry budget context follows.`, workspaceKey: WS, scope: 'workspace', tokens: 30 }))
}
// title/summary facts with a unique cue (ordinary recall, hot + cold)
const titleAnswers = []
for (let index = 0; index < 60; index += 1) {
  titleAnswers.push(core.write({ kind: 'decision', title: `checkpoint decision CUE-${index} cache invalidation policy`, summary: `cache invalidation policy decision CUE-${index} keeps the previous deployment id`, useWhen: 'read when continuing cache invalidation work', body: `decision evidence for CUE-${index}`, workspaceKey: WS, scope: 'workspace', tokens: 25 }))
}
// cold tier: archive 60 body answers and 30 title facts
for (const card of bodyAnswers.slice(0, 60)) core.archiveCold(card.id)
for (const card of titleAnswers.slice(0, 30)) core.archiveCold(card.id)
core.close()

const bodyProbes = Array.from({ length: 40 }, (_, i) => ({ query: `incident INC-${60 + i} deployment retry budget answer token`, id: bodyAnswers[60 + i].id }))
const coldBodyProbes = Array.from({ length: 30 }, (_, i) => ({ query: `incident INC-${i} deployment retry budget cold answer`, id: bodyAnswers[i].id }))
const titleProbes = Array.from({ length: 40 }, (_, i) => ({ query: `cache invalidation policy decision CUE-${i}`, id: titleAnswers[i].id }))

const runSearchEval = (profileId) => {
  const profile = resolveModelProfile(profileId)
  const store = new LocalStoreCore({ root: ROOT, capacityTokens: 1_000_000_000, sessionCapacityTokens: 100_000_000, defaultLevels: { l2: false, l3: false } })
  try {
    const evaluate = (probes, limit = 5) => {
      let hit1 = 0
      let hit5 = 0
      let tokens = 0
      for (const probe of probes) {
        const result = store.search({ query: probe.query, workspaceKey: WS, scope: 'workspace', limit, rerank: profile.rerank, maxTerms: profile.queryTerms?.maxTerms })
        const rank = result.hits.findIndex((card) => card.id === probe.id)
        if (rank === 0) hit1 += 1
        if (rank >= 0) hit5 += 1
        const cardText = result.hits.map((card) => `${card.title} ${card.summary ?? ''} ${card.useWhen ?? ''}`).join(' ')
        tokens += profileTokens(cardText, profile) + profileTokens(result.hits[rank]?.summary ?? '', profile)
      }
      return { hit1: hit1 / probes.length, hit5: hit5 / probes.length, tokensPerAnswer: Math.round(tokens / probes.length) }
    }
    const catalog = buildCatalogInjection(profile, store.catalog({ workspaceKey: WS, scopes: ['workspace'], maxChars: 60000 }))
    const manual = buildMemoryManual(profile, { agent: 'validation', root: ROOT, levels: profile.levels })
    const facets = store.facets({ workspaceKey: WS, scopes: ['workspace'] })
    return {
      profile: profileId,
      profileId: profile.id,
      window: profile.windowTokens,
      charsPerToken: profile.charsPerToken,
      catalogTokens: profile.catalogTokens,
      recallTokens: profile.recallTokens,
      injectedCatalogTokens: profileTokens(catalog, profile),
      injectedCatalogBytes: Buffer.byteLength(catalog),
      manualTokens: profileTokens(manual, profile),
      bodyProbes: evaluate(bodyProbes),
      coldBodyProbes: evaluate(coldBodyProbes),
      titleProbes: evaluate(titleProbes),
      longHorizon: { turns: 50, catalogTokensPerTurn: profileTokens(catalog, profile), cumulativeCatalogTokens: profileTokens(catalog, profile) * 50 },
      facets: { hot: facets.hotCount, cold: facets.coldCount },
    }
  } finally {
    store.close()
  }
}

const spawnMCP = (profileId) => new Promise((resolve) => {
  const started = performance.now()
  const child = spawn(N, ['--import', REG, MCP, '--root', ROOT, '--agent', 'validation', '--model', profileId, '--levels', 'l3', '--cwd', CWD, '--session', SESSION], { stdio: ['pipe', 'pipe', 'pipe'] })
  let buffer = ''
  let initMs
  let firstSearchMs
  const stamp = { init: undefined, search: undefined }
  const t0 = performance.now()
  child.stdout.setEncoding('utf8')
  child.stdout.on('data', (chunk) => {
    buffer += chunk
    let index = buffer.indexOf('\n')
    while (index >= 0) {
      const line = buffer.slice(0, index).trim(); buffer = buffer.slice(index + 1); index = buffer.indexOf('\n')
      if (!line) continue
      const message = JSON.parse(line)
      if (message.id === 1) {
        initMs = performance.now() - t0
        const tSearch = performance.now()
        child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'memory_search', arguments: { query: 'incident INC-0 deployment retry budget answer token' } } })}\n`)
        stamp.search = tSearch
      } else if (message.id === 2) {
        firstSearchMs = performance.now() - stamp.search
        child.stdin.end()
        resolve({ initMs: +initMs.toFixed(1), firstSearchMs: +firstSearchMs.toFixed(1), totalMs: +(performance.now() - started).toFixed(1), searchTextChars: message.result?.content?.[0]?.text?.length ?? 0 })
      }
    }
  })
  child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize', params: {} })}\n`)
  setTimeout(() => { try { child.kill() } catch {} resolve({ initMs: null, firstSearchMs: null, timeout: true }) }, 30000)
})

const results = { profiles: [], coldStart: [] }
for (const profileId of profiles) results.profiles.push(runSearchEval(profileId))
for (const profileId of profiles) {
  const runs = []
  for (let i = 0; i < 3; i += 1) runs.push(await spawnMCP(profileId))
  results.coldStart.push({ profile: profileId, runs })
}
const output = { format: 1, generatedAt: new Date().toISOString(), load: loadavg(), results }
writeFileSync(OUT, `${JSON.stringify(output, null, 2)}\n`)
console.log(JSON.stringify({ out: OUT, profiles: results.profiles.length, coldStart: results.coldStart.length, load: loadavg() }, null, 2))
