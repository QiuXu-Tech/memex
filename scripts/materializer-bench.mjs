// Offline paired benchmark. Baseline must contain the frozen core package.
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { performance } from 'node:perf_hooks'
import { serialize } from 'node:v8'
import assert from 'node:assert/strict'
import { BENCHMARK_CASES, BENCHMARK_SEEDS, inputFor, random } from '../test/materializer-fixtures.mjs'

const args = process.argv.slice(2)
const option = (name, fallback) => { const i = args.indexOf('--' + name); return i < 0 ? fallback : args[i + 1] }
const digest = value => createHash('sha256').update(Buffer.isBuffer(value) || typeof value === 'string' ? value : JSON.stringify(value)).digest('hex')
const median = xs => { const a = [...xs].sort((a, b) => a - b), m = Math.floor(a.length / 2); return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2 }
const quantile = (xs, q) => [...xs].sort((a, b) => a - b)[Math.min(xs.length - 1, Math.ceil(xs.length * q) - 1)]

if (args.includes('--worker')) {
  const root = path.resolve(option('root', '.')), seed = Number(option('seed', 11))
  const warmup = Number(option('warmup', 1)), samples = Number(option('samples', 3))
  const { orderContextPages } = await import(pathToFileURL(path.join(root, 'packages/memex-core/lib/context-events.js')))
  const { materializeContext } = await import(pathToFileURL(path.join(root, 'packages/memex-core/lib/context-materializer.js')))
  const results = []
  for (const spec of BENCHMARK_CASES) {
    const input = inputFor(spec, seed)
    const original = structuredClone(input.pages), references = new Set(input.pages)
    const invoke = spec.kind === 'order' ? () => orderContextPages(input.pages) : () => materializeContext(input)
    for (let i = 0; i < warmup; i++) invoke()
    global.gc?.()
    const times = [], cpu = [], outputHashes = []
    let output
    for (let i = 0; i < samples; i++) {
      const before = process.cpuUsage(), start = performance.now()
      output = invoke()
      times.push(performance.now() - start)
      const used = process.cpuUsage(before); cpu.push((used.user + used.system) / 1000)
      assert.deepStrictEqual(input.pages, original)
      if (spec.kind === 'order') assert.ok(output.every(page => references.has(page)))
      outputHashes.push(digest(serialize(output)))
    }
    assert.equal(new Set(outputHashes).size, 1, 'pure benchmark output changed between samples')
    results.push({ name: spec.name, fixtureSha256: digest(serialize({ ...input, tokenCounter: spec.custom ? 'codepoint-line-v1' : null })), wallMs: times, cpuMs: cpu,
      outputSha256: outputHashes[0], sampleOutputSha256: outputHashes,
      rssBytes: process.memoryUsage().rss, included: spec.kind === 'order' ? output.length : output.includedIds.length })
  }
  console.log(JSON.stringify({ seed, node: process.version, v8: process.versions.v8, icu: process.versions.icu,
    loadAverage: os.loadavg(), peakRssKiB: process.resourceUsage().maxRSS, results }))
} else {
  const baseline = path.resolve(option('baseline', '')), candidate = path.resolve(option('candidate', '.'))
  const out = path.resolve(option('out', 'materializer-bench.json')), replicates = Number(option('replicates', 2))
  if (!args.includes('--baseline')) throw new Error('--baseline frozen source directory is required')
  fs.mkdirSync(path.dirname(out), { recursive: true })
  const sourceHashes = root => Object.fromEntries(fs.readdirSync(path.join(root, 'packages/memex-core'), { recursive: true }).sort()
    .filter(file => fs.statSync(path.join(root, 'packages/memex-core', file)).isFile())
    .map(file => [file, digest(fs.readFileSync(path.join(root, 'packages/memex-core', file)))]))
  const sourcesBefore = { baseline: sourceHashes(baseline), candidate: sourceHashes(candidate), benchmark: digest(fs.readFileSync(fileURLToPath(import.meta.url))),
    fixtures: digest(fs.readFileSync(new URL('../test/materializer-fixtures.mjs', import.meta.url))) }
  const records = [], workerRuns = []
  const persist = () => { fs.writeFileSync(out + '.partial.json.tmp', JSON.stringify({ sourcesBefore, cases: BENCHMARK_CASES, workerRuns, records }, null, 2)); fs.renameSync(out + '.partial.json.tmp', out + '.partial.json') }
  const script = fileURLToPath(import.meta.url)
  let pair = 0
  for (const seed of BENCHMARK_SEEDS) for (let replicate = 0; replicate < replicates; replicate++) {
    const order = pair % 2 === 0 ? ['baseline', 'candidate'] : ['candidate', 'baseline']
    for (const version of order) {
      const startedAt = new Date().toISOString()
      const child = spawnSync(process.execPath, ['--expose-gc', script, '--worker', '--root', version === 'baseline' ? baseline : candidate, '--seed', String(seed)],
        { encoding: 'utf8', timeout: 60000, maxBuffer: 2 * 1024 * 1024 })
      workerRuns.push({ pair, replicate, seed, version, startedAt, finishedAt: new Date().toISOString(), exit: child.status, signal: child.signal, error: child.error?.message, stdout: child.stdout, stderr: child.stderr })
      persist()
      if (child.status !== 0 || child.error) {
        fs.writeFileSync(out + '.failure.json', JSON.stringify({ pair, seed, replicate, version, exit: child.status, error: child.error?.message, stderr: child.stderr, records }, null, 2))
        throw new Error(`benchmark worker failed: ${version}, seed ${seed}; retained ${out}.failure.json`)
      }
      try { records.push({ pair, replicate, version, ...JSON.parse(child.stdout) }) } catch (error) { persist(); throw error }
      persist()
    }
    console.error(`paired worker ${++pair}/${BENCHMARK_SEEDS.length * replicates}, seed ${seed}`)
  }
  const summary = []
  for (const spec of BENCHMARK_CASES) {
    const ratios = [], differences = [], relativeChanges = [], cpuRatios = [], baselineTimes = [], candidateTimes = [], baselineWorkerMedians = []
    for (let i = 0; i < pair; i++) {
      const a = records.find(r => r.pair === i && r.version === 'baseline').results.find(r => r.name === spec.name)
      const b = records.find(r => r.pair === i && r.version === 'candidate').results.find(r => r.name === spec.name)
      if (a.fixtureSha256 !== b.fixtureSha256 || a.outputSha256 !== b.outputSha256) {
        fs.writeFileSync(out + '.failure.json', JSON.stringify({ case: spec.name, pair: i, records }, null, 2))
        throw new Error(`differential mismatch: ${spec.name}, pair ${i}`)
      }
      const am = median(a.wallMs), bm = median(b.wallMs)
      if (!(am > 0 && bm > 0 && Number.isFinite(am) && Number.isFinite(bm))) throw new Error('invalid wall sample')
      ratios.push(am / bm); differences.push(bm - am); relativeChanges.push((bm - am) / am); baselineWorkerMedians.push(am)
      const ac = median(a.cpuMs), bc = median(b.cpuMs); cpuRatios.push(ac > 0 && bc > 0 ? ac / bc : null)
      baselineTimes.push(...a.wallMs); candidateTimes.push(...b.wallMs)
    }
    const geometric = xs => Math.exp(xs.reduce((a, x) => a + Math.log(x), 0) / xs.length)
    const rng = random(90421), bootstrap = []
    for (let i = 0; i < 2000; i++) {
      const sample = []
      for (const _ of BENCHMARK_SEEDS) {
        const offset = Math.floor(rng() * BENCHMARK_SEEDS.length) * replicates
        for (let j = 0; j < replicates; j++) sample.push(ratios[offset + Math.floor(rng() * replicates)])
      }
      bootstrap.push(median(sample))
    }
    summary.push({ name: spec.name, pairedWorkerCount: ratios.length, outputParity: true,
      pairedMedianSpeedup: median(ratios), speedupGeomean: geometric(ratios), speedup95CI: [quantile(bootstrap, .025), quantile(bootstrap, .975)],
      pairedMedianDeltaMs: median(differences), pairedMedianRelativeChange: median(relativeChanges),
      smallRegressionBoundMs: Math.max(.2, .1 * median(baselineWorkerMedians)),
      cpuSpeedupGeomean: cpuRatios.every(x => x !== null && Number.isFinite(x)) ? geometric(cpuRatios) : null,
      cpuUndefinedPairs: cpuRatios.filter(x => x === null).length, baselineMedianMs: median(baselineTimes), candidateMedianMs: median(candidateTimes),
      baselineP95Ms: quantile(baselineTimes, .95), candidateP95Ms: quantile(candidateTimes, .95), pairSpeedups: ratios })
  }
  const sourcesAfter = { ...sourcesBefore, baseline: sourceHashes(baseline), candidate: sourceHashes(candidate), benchmark: digest(fs.readFileSync(script)),
    fixtures: digest(fs.readFileSync(new URL('../test/materializer-fixtures.mjs', import.meta.url))) }
  assert.deepStrictEqual(sourcesAfter, sourcesBefore, 'source or harness drift invalidates the run')
  const result = { syntheticOnly: true, node: process.version, platform: process.platform, arch: process.arch,
    seeds: BENCHMARK_SEEDS, replicates, warmupPerWorker: 1, samplesPerWorker: 3,
    bootstrap: 'hierarchical paired resampling: five synthetic seed clusters, then paired workers; descriptive CI, not production inference',
    p95: 'descriptive pooled 30-call quantile per version, not independent tail-latency evidence',
    sourcesBefore, sourcesAfter, cases: BENCHMARK_CASES, workerRuns, records, summary }
  fs.mkdirSync(path.dirname(out), { recursive: true }); fs.writeFileSync(out, JSON.stringify(result, null, 2) + '\n')
  console.log(JSON.stringify(summary.map(({ name, speedupGeomean, speedup95CI, baselineMedianMs, candidateMedianMs }) => ({ name, speedupGeomean, speedup95CI, baselineMedianMs, candidateMedianMs })), null, 2))
}
