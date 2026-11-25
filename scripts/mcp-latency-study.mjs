// Local-only study. Usage: node scripts/mcp-latency-study.mjs BASELINE CANDIDATE NEW_OUTPUT.json
import { spawn, execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import { tmpdir, loadavg, platform, arch } from 'node:os'
import { basename, dirname, join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { createInterface } from 'node:readline'
import { syncBuiltinESMExports } from 'node:module'
import { performance } from 'node:perf_hooks'

const [base, candidate, output] = process.argv.slice(2)
if (!base || !candidate || !output) throw new Error('Usage: node scripts/mcp-latency-study.mjs BASELINE CANDIDATE NEW_OUTPUT.json')
const repos = { A: resolve(base), B: resolve(candidate) }
const sha = value => createHash('sha256').update(value).digest('hex')
const digest = value => sha(JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item))
const sessionId = 'study-visible'
const levels = ['l2', 'l3']
const repeats = 12, warmups = 4
const sequence = ['A', 'B', 'B', 'A']
const search = (query, limit = 8, openTop = false) => ({ name: 'memory_search', arguments: { query, limit, openTop } })
const open = id => ({ name: 'memory_open', arguments: { id, maxChars: 2000 } })
const entry = 'packages/memex-mcp/bin/server.mjs'
const core = 'packages/memex-core'
const codePaths = repo => [entry, 'packages/memex-mcp/package.json', ...fs.readdirSync(join(repo, core), { recursive: true })
  .map(path => join(core, path)).filter(path => fs.statSync(join(repo, path)).isFile())].sort()
const source = repo => Object.fromEntries(codePaths(repo).map(path => [path, sha(fs.readFileSync(join(repo, path)))]))
const statusOf = repo => {
  try {
    const git = fs.existsSync('/Library/Developer/CommandLineTools/usr/bin/git') ? '/Library/Developer/CommandLineTools/usr/bin/git' : 'git'
    return execFileSync(git, ['--no-optional-locks', '-C', repo, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
  } catch { return null }
}
const report = { status: 'RUNNING', repos, node: process.version, sqlite: process.versions.sqlite,
  platform: platform(), arch: arch(), scriptSha256: sha(fs.readFileSync(new URL(import.meta.url))),
  warmups, repeats, sequence, runs: [], probes: [], fixtures: [], startedAt: new Date().toISOString() }
const outputPath = resolve(output)
fs.mkdirSync(dirname(outputPath), { recursive: true })
fs.writeFileSync(outputPath, JSON.stringify(report, null, 2), { flag: 'wx' })
const save = () => fs.writeFileSync(outputPath, JSON.stringify(report, null, 2) + '\n')
const scratch = fs.mkdtempSync(join(tmpdir(), 'memex-mcp-study-'))
const staged = label => join(scratch, label)
const casesFor = n => [
  { id: 'unique', request: i => search(`entry${String(i % n).padStart(4, '0')}`), marker: i => `\n1. record-${i % n} [` },
  { id: 'common-repeat', request: () => search('sharedanchor', 32), marker: () => '32 results shown' },
  { id: 'miss', request: () => search('nonexistentxqz'), marker: () => 'No matching memory records.' },
  { id: 'body-only', request: () => search(`capsule${n - 1}`), marker: () => `\n1. record-${n - 1} [` },
  { id: 'open', request: i => open(`record-${i % n}`), marker: i => `archived evidence ${i % n}` },
  { id: 'open-top', request: () => search('entry0000', 8, true), marker: () => 'Top result preview' },
  { id: 'session-hidden-search', request: () => search('hiddenanchor'), marker: () => 'No matching memory records.' },
  { id: 'session-hidden-open', request: () => open('hidden-record'), error: true, marker: () => 'no record' },
  { id: 'workspace-hidden-search', request: () => search('outsideanchor'), marker: () => 'No matching memory records.' },
  { id: 'workspace-hidden-open', request: () => open('outside-record'), error: true, marker: () => 'no record' },
]
const importEngine = async repo => (await import(pathToFileURL(join(repo, core, 'lib/engine.js')))).AgentMemory
function fixture(AgentMemory, n) {
  const cwd = join(scratch, `workspace-${n}`), root = join(scratch, `store-${n}`)
  fs.mkdirSync(cwd)
  const engine = new AgentMemory({ cwd, root, sessionId, levels, agent: 'mcp-client' })
  const write = i => ({ id: `record-${i}`, kind: 'episode', scope: 'workspace', title: `sharedanchor entry${String(i).padStart(4, '0')}`,
    summary: 'Synthetic archive card about sharedanchor and archived evidence.', useWhen: 'verify sharedanchor archive',
    body: `## Current Work\narchived evidence ${i}\n\n${'证据 archive replay section\n'.repeat(20 + i % 12)}\nunique body capsule${i} ending.`,
    createdAt: 1_730_000_000_000 + i })
  const records = Array.from({ length: n }, (_, i) => write(i))
  const hidden = { id: 'hidden-record', kind: 'fact', scope: 'session', sessionId: 'study-other', workspaceKey: engine.workspaceKey,
    title: 'hiddenanchor', summary: 'hiddenanchor', body: 'hiddenanchor hidden-body', createdAt: 1_730_000_000_000 }
  const outside = { ...hidden, id: 'outside-record', scope: 'workspace', sessionId: '', workspaceKey: 'study-outside-workspace',
    title: 'outsideanchor', summary: 'outsideanchor', body: 'outsideanchor hidden-body' }
  try {
    for (const record of records) engine.write(record)
    engine.store.write(hidden)
    engine.store.write(outside)
    // Pin rank tie metadata independently of write scheduling. The fixture is
    // synthetic, private to this run, and is reused serially by both versions.
    engine.store.database().exec('UPDATE records SET updated_at = created_at')
  } finally { engine.close() }
  const cases = casesFor(n).map(spec => spec.id === 'common-repeat' && n < 32
    ? { ...spec, marker: () => `${n} results shown` } : spec)
  const requests = cases.map(spec => ({ id: spec.id, warm: Array.from({ length: warmups }, (_, i) => spec.request(i)),
    measured: Array.from({ length: repeats }, (_, i) => spec.request(i)), expectedError: spec.error === true }))
  report.fixtures.push({ n, fixtureSha256: digest({ records, hidden: { ...hidden, workspaceKey: undefined }, outside, updatedAt: 'createdAt' }), requestsSha256: digest(requests), requests })
  return { cwd, root, n, cases }
}

async function run(label, dataset, slot) {
  const { cwd, root, n, cases } = dataset
  const result = { label, slot, n, loadBefore: loadavg(), samples: [], stderr: '' }
  report.runs.push(result)
  const start = performance.now()
  const child = spawn(process.execPath, ['--preserve-symlinks-main', join(staged(label), entry), '--root', root, '--cwd', cwd, '--session', sessionId, '--levels', levels.join(',')],
    { cwd, env: { HOME: scratch, PATH: process.env.PATH, TMPDIR: scratch }, stdio: ['pipe', 'pipe', 'pipe'] })
  const lines = createInterface({ input: child.stdout })
  const iterator = lines[Symbol.asyncIterator]()
  const closed = new Promise(done => child.once('close', (code, signal) => done({ code, signal })))
  child.on('error', error => { result.spawnError = error.stack })
  child.stdin.on('error', error => { result.stdinError = error.stack })
  child.stderr.on('data', chunk => { result.stderr += chunk.toString() })
  const timer = setTimeout(() => { result.timeout = true; child.kill('SIGKILL') }, 15000)
  let id = 0
  const notify = (method, params) => child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method, params }) + '\n')
  async function rpc(method, params) {
    const request = { jsonrpc: '2.0', id: ++id, method, params }
    const at = performance.now()
    child.stdin.write(JSON.stringify(request) + '\n')
    const { value, done } = await iterator.next()
    const ms = performance.now() - at
    if (done) throw new Error(`${method}: MCP stdout closed`)
    const response = JSON.parse(value)
    if (response.id !== id || response.error || !response.result) throw new Error(`${method}: ${value}`)
    return { ms, response: response.result, bytes: Buffer.byteLength(value) + 1 }
  }
  try {
    const init = await rpc('initialize', { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'memex-local-study', version: '1' } })
    result.startupInitializeMs = performance.now() - start
    result.serverInfo = init.response.serverInfo
    notify('notifications/initialized', {})
    const listed = await rpc('tools/list', {})
    for (const name of ['memory_search', 'memory_open']) if (!listed.response.tools.some(tool => tool.name === name)) throw new Error(`Missing tool ${name}`)
    for (let i = 0; i < warmups + repeats; i++) for (let j = 0; j < cases.length; j++) {
      const spec = cases[(j + i) % cases.length], index = i < warmups ? i : i - warmups
      const request = spec.request(index)
      const sample = await rpc('tools/call', request)
      const text = sample.response.content?.map(block => block.text).join('\n') ?? ''
      const sampleRow = { case: spec.id, index, warmup: i < warmups, ms: sample.ms, bytes: sample.bytes, sha256: digest(sample.response) }
      result.samples.push(sampleRow)
      if (Boolean(sample.response.isError) !== Boolean(spec.error) || !text.includes(spec.marker(index)) || text.includes('hidden-body')) {
        result.badResponse = { case: spec.id, request, response: sample.response }
        throw new Error(`Unexpected ${spec.id} response: ${text}`)
      }
    }
  } catch (error) {
    result.error = error.stack
    throw error
  } finally {
    child.stdin.end()
    result.exit = await closed
    clearTimeout(timer)
    result.loadAfter = loadavg()
    save()
  }
  if (result.exit.code !== 0) throw new Error(`MCP worker exited ${JSON.stringify(result.exit)}`)
}

function probe(AgentMemory, dataset, label) {
  const { cwd, root, n, cases } = dataset
  const engine = new AgentMemory({ cwd, root, sessionId, levels, agent: 'mcp-client' })
  const read = fs.readFileSync
  try {
    for (const spec of cases.filter(item => !item.id.includes('-hidden-'))) {
      const samples = []
      for (let i = 0; i < 8; i++) {
        const { name, arguments: args } = spec.request(i)
        let reads = 0, unique = new Set(), readMs = 0
        fs.readFileSync = (path, ...rest) => {
          if (typeof path !== 'string' || !path.startsWith(root + '/') || !path.endsWith('.md')) return read(path, ...rest)
          const start = performance.now()
          try { return read(path, ...rest) } finally { reads++; unique.add(path); readMs += performance.now() - start }
        }
        syncBuiltinESMExports()
        const start = performance.now()
        const result = name === 'memory_search' ? engine.search(args) : engine.open(args)
        const engineMs = performance.now() - start
        let openTopMs = 0
        if (args.openTop && result.hits.length > 0) {
          const beforeOpen = performance.now()
          engine.open({ id: result.hits[0].id, maxChars: 2000 })
          openTopMs = performance.now() - beforeOpen
        }
        if (i >= 2) samples.push({ engineMs, openTopMs, reads, uniquePaths: unique.size, readMs, hitCount: result?.hits?.length })
      }
      report.probes.push({ label, n, case: spec.id, samples })
    }
  } finally { fs.readFileSync = read; syncBuiltinESMExports(); engine.close() }
}

const median = values => {
  const sorted = [...values].sort((a, b) => a - b), k = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[k] : (sorted[k - 1] + sorted[k]) / 2
}
try {
  report.head = Object.fromEntries(Object.entries(repos).map(([label, repo]) => [label, statusOf(repo)]))
  report.sourceBefore = Object.fromEntries(Object.entries(repos).map(([label, repo]) => [label, source(repo)]))
  for (const [label, repo] of Object.entries(repos)) {
    // Link the measured packages in scratch space, like workspace bootstrap,
    // without writing node_modules into either measured checkout.
    fs.mkdirSync(join(staged(label), 'packages'), { recursive: true })
    fs.mkdirSync(join(staged(label), 'node_modules/@qiuxu'), { recursive: true })
    fs.symlinkSync(join(repo, 'packages/memex-mcp'), join(staged(label), 'packages/memex-mcp'), 'dir')
    fs.symlinkSync(join(repo, core), join(staged(label), 'node_modules/@qiuxu/memex-core'), 'dir')
  }
  const [Base, Candidate] = await Promise.all([importEngine(repos.A), importEngine(repos.B)])
  const datasets = [fixture(Base, 12), fixture(Base, 512)]
  save()
  for (const dataset of datasets) for (const [slot, label] of sequence.entries()) await run(label, dataset, slot)
  report.summary = []
  for (const { n, cases } of datasets) for (const spec of cases) {
    const workers = report.runs.filter(item => item.n === n).map(item => item.samples.filter(s => s.case === spec.id && !s.warmup))
    for (const group of workers) for (const [i, sample] of group.entries()) {
      if (sample.sha256 !== workers[0][i].sha256) throw new Error(`Complete MCP result mismatch for n=${n}, ${spec.id}, sample ${i}`)
    }
    const medians = workers.map(worker => median(worker.map(s => s.ms)))
    const pairs = [[0, 1], [3, 2]].map(([a, b]) => ({ baselineMs: medians[a], candidateMs: medians[b], deltaMs: medians[b] - medians[a], reduction: 1 - medians[b] / medians[a] }))
    report.summary.push({ n, case: spec.id, outputParity: true, pairs, pairedMedianDeltaMs: median(pairs.map(p => p.deltaMs)), pairedMedianReduction: median(pairs.map(p => p.reduction)) })
  }
  for (const dataset of datasets) for (const [label, Engine] of [['A', Base], ['B', Candidate]]) probe(Engine, dataset, label)
  report.sourceAfter = Object.fromEntries(Object.entries(repos).map(([label, repo]) => [label, source(repo)]))
  if (digest(report.sourceBefore) !== digest(report.sourceAfter)) throw new Error('Repository sources changed during measurement')
  report.status = 'PASS'
} catch (error) {
  report.status = 'FAIL'; report.firstError = error.stack
  process.exitCode = 1
} finally {
  fs.rmSync(scratch, { recursive: true, force: true })
  report.finishedAt = new Date().toISOString()
  save()
  console.log(`${report.status} ${basename(outputPath)}: ${report.runs.length} MCP workers, ${report.probes.length} phase groups`)
  if (report.firstError) console.error(report.firstError)
}
