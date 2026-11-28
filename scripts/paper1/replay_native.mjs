#!/usr/bin/env node
/** Bounded offline replay of the recorded native-smoke-02 command stream.
 * No host/model/API calls. Version assignment and claims are development inputs,
 * not an automatic live workspace binding or a paired performance experiment.
 */
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { EvidenceArchive } from './archive.mjs'
import { normalizeNodeTestEvent } from './normalize-node.mjs'
import { digest, verifyEvidence } from './verification.mjs'

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const ARTIFACTS = 'docs/research/p1-evidence-verification/artifacts'
const LOG_FILES = ['native-smoke-02/host/events.jsonl', 'native-smoke-02-resumed-final/host/events.jsonl']
const SUMMARY_FILE = 'native-smoke-02-resumed-final/summary.json'
const LIMITS = Object.freeze({ maxInputBytes: 1_048_576, maxLogRows: 2000, maxCommands: 32,
  maxEvidenceBytes: 16384, maxReferenceTokens: 16384, maxHits: 8, pageChars: 512 })
const sha256 = value => createHash('sha256').update(value).digest('hex')
const writeJson = (path, value) => writeFileSync(path, JSON.stringify(value, null, 2) + '\n')
const safeUtc = value => typeof value === 'string' && /(?:Z|\+00:00)$/.test(value) && Number.isFinite(Date.parse(value))

function boundedRead(path) {
  assert.ok(statSync(path).size <= LIMITS.maxInputBytes, 'input exceeds replay byte limit')
  const bytes = readFileSync(path)
  assert.ok(bytes.length <= LIMITS.maxInputBytes, 'input grew beyond replay byte limit')
  return bytes
}

function commandText(command) {
  const match = command.match(/^\/(?:[^\s/]+\/)*(?:zsh|bash|sh) -lc (['"])([^\r\n]*)\1$/)
  return (match ? match[2] : command).trim().replace(/[\t ]+/g, ' ')
}

/** Read actual terminal events; summary commands are cross-checks, never substitutes. */
export function loadReplayInputs(smokeRoot) {
  const summaryBytes = boundedRead(join(smokeRoot, SUMMARY_FILE))
  const summary = JSON.parse(summaryBytes)
  assert.equal(summary.kind, 'native_host_integration_smoke')
  assert.equal(summary.confirmatory, false)
  assert.equal(typeof summary.thread_id, 'string')
  const inputFiles = [{ path: SUMMARY_FILE, sha256: sha256(summaryBytes), bytes: summaryBytes.length }]
  const rows = LOG_FILES.flatMap(path => {
    const bytes = boundedRead(join(smokeRoot, path))
    inputFiles.push({ path, sha256: sha256(bytes), bytes: bytes.length })
    const lines = bytes.toString('utf8').split('\n').filter(line => line.trim())
    assert.ok(lines.length <= LIMITS.maxLogRows, 'event row budget exceeded')
    return lines.map((raw, index) => ({ row: JSON.parse(raw), path, line: index + 1, raw }))
  })
  const commands = rows.filter(({ row }) => row.event === 'item/completed' && row.item?.type === 'commandExecution')
  assert.ok(commands.length > 0 && commands.length <= LIMITS.maxCommands)
  assert.equal(new Set(commands.map(({ row }) => row.item.id)).size, commands.length, 'duplicate command event')
  const versions = Object.fromEntries(summary.source_versions.map(v => [v.stage, v.sha256]))
  for (const stage of ['original', 'changed']) assert.match(versions[stage] ?? '', /^[a-f0-9]{64}$/)
  assert.notEqual(versions.original, versions.changed)
  const turns = new Map(summary.turns.map(turn => [turn.phase, turn]))
  const stageForPhase = { prelude: 'original', interleaved_update: 'changed', continuation: 'changed' }
  for (const { row } of commands) {
    assert.ok(safeUtc(row.utc), 'completed command lacks original UTC')
    assert.equal(row.threadId, summary.thread_id)
    assert.ok(stageForPhase[row.phase], 'unmapped command phase')
    const turn = turns.get(row.phase)
    assert.equal(row.turnId, turn?.turn_id)
    const recorded = turn.commands.filter(item => item.id === row.item.id)
    assert.equal(recorded.length, 1, 'terminal command absent or duplicated in controller summary')
    for (const key of ['command', 'exitCode', 'aggregatedOutput', 'status']) {
      assert.deepEqual(row.item[key], recorded[0][key], `summary/log mismatch: ${key}`)
    }
    assert.ok(['completed', 'failed'].includes(row.item.status), 'nonterminal command')
  }
  assert.equal(summary.turns.reduce((n, turn) => n + turn.commands.length, 0), commands.length,
    'summary/log terminal command coverage differs')

  // Cross-check the controller's known source versions against real cat and shasum outputs.
  const bindings = Object.entries({ prelude: 'original', interleaved_update: 'changed' }).map(([phase, stage]) => {
    const select = command => commands.filter(({ row }) => row.phase === phase && commandText(row.item.command) === command)
    const contents = select('cat sum.mjs')
    const readbacks = select('shasum -a 256 sum.mjs')
    assert.equal(contents.length, 1)
    assert.equal(readbacks.length, 1)
    assert.equal(contents[0].row.item.exitCode, 0)
    assert.equal(readbacks[0].row.item.exitCode, 0)
    assert.equal(sha256(contents[0].row.item.aggregatedOutput), versions[stage], 'controller version/content mismatch')
    assert.equal(readbacks[0].row.item.aggregatedOutput.trim(), `${versions[stage]}  sum.mjs`, 'hash readback mismatch')
    return { stage, artifact: 'sum.mjs', sha256: versions[stage], contentEventId: contents[0].row.item.id,
      readbackEventId: readbacks[0].row.item.id, readbackUtc: readbacks[0].row.utc }
  })
  const selected = []
  const inventory = []
  for (const entry of commands.sort((a, b) => Date.parse(a.row.utc) - Date.parse(b.row.utc))) {
    const { row } = entry
    const stage = stageForPhase[row.phase]
    const capture = { threadId: row.threadId, scope: 'native-smoke-02', observedAt: row.utc,
      sourceSequence: selected.length + 1, artifactBefore: versions[stage], artifactAfter: versions[stage] }
    const parsed = normalizeNodeTestEvent(row.item, capture)
    inventory.push({ file: entry.path, line: entry.line, utc: row.utc, phase: row.phase,
      eventId: row.item.id, command: row.item.command, terminalStatus: row.item.status,
      exitCode: row.item.exitCode, selected: parsed.source !== null, parserIssue: parsed.issue,
      outputSha256: typeof row.item.aggregatedOutput === 'string' ? sha256(row.item.aggregatedOutput) : null })
    if (!parsed.source) {
      assert.ok(!commandText(row.item.command).includes('--test'), 'relevant test event could not be normalized')
      continue
    }
    parsed.source.transport = { nativeLog: entry.path, line: entry.line, phase: row.phase,
      threadId: row.threadId, turnId: row.turnId, utc: row.utc, completedAtMs: row.completedAtMs,
      artifactBindingMode: 'offline_controller_summary_version_mapping', artifact: 'sum.mjs',
      versionStage: stage, summaryPath: SUMMARY_FILE, summarySha256: sha256(summaryBytes),
      independentLiveBeforeAfterMeasurements: false, liveWorkspaceRevalidation: false }
    assert.equal(parsed.source.text, row.item.aggregatedOutput, 'normalization changed saved stdout')
    selected.push({ ...entry, capture, source: parsed.source })
  }
  assert.equal(selected.length, 2, 'this bounded replay requires both recorded supported test events')
  assert.deepEqual(selected.map(x => x.row.phase), ['prelude', 'continuation'])
  assert.equal(selected[0].source.entity, selected[1].source.entity)
  assert.equal(selected[0].source.sourceId, selected[1].source.sourceId)
  assert.ok(Date.parse(bindings[0].readbackUtc) < Date.parse(bindings[1].readbackUtc))
  assert.ok(Date.parse(bindings[1].readbackUtc) < Date.parse(selected[1].row.utc))
  const requests = Object.fromEntries(['prelude', 'interleaved_update', 'continuation'].map(phase => {
    const matches = rows.filter(({ row }) => row.phase === phase && row.event === 'item/completed' && row.item?.type === 'userMessage')
    assert.equal(matches.length, 1, 'ambiguous original phase request')
    const content = matches[0].row.item.content
    assert.ok(content.every(part => part.type === 'text' && typeof part.text === 'string'))
    return [phase, { text: content.map(part => part.text).join('\n'), file: matches[0].path,
      line: matches[0].line, utc: matches[0].row.utc }]
  }))
  return { summary, inputFiles, versions, bindings, selected, inventory, requests }
}

function validatePublicArchives(repositoryRoot, paths) {
  const program = `import importlib.util,json,sys\nfrom pathlib import Path\nsys.dont_write_bytecode=True\np=Path(sys.argv[1])\ns=importlib.util.spec_from_file_location('p1_rawrag_validation',p)\nm=importlib.util.module_from_spec(s)\ns.loader.exec_module(m)\nc=m.load_config()\nrows=[]\nfor name in sys.argv[2:]:\n d=m.read_json_bounded(Path(name),c['limits']['max_archive_bytes'])\n m.validate_archive(d,c['limits'])\n rows.append({'file':Path(name).name,'sources':len(d['sources']),'valid':True})\nprint(json.dumps({'validator':'rawrag_adapter.validate_archive','archives':rows,'modelCalls':0}))\n`
  const result = spawnSync('python3', ['-c', program, join(repositoryRoot, 'scripts/paper1/rawrag_adapter.py'), ...paths],
    { encoding: 'utf8', timeout: 15000, maxBuffer: 65536, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } })
  assert.equal(result.status, 0, `offline public-archive validation failed: ${result.stderr}`)
  return JSON.parse(result.stdout)
}

function renderReport(report) {
  const table = report.decisions.map(d => `| ${d.id} | ${d.result.outcome} | ${d.result.status} | ${d.result.reason} | ${d.result.reused} | ${d.result.metrics.opens} |`).join('\n')
  const events = report.sources.map(s => `| ${s.phase} | ${s.utc} | ${s.exitCode} | ${s.status} | ${s.stdoutBytes} |`).join('\n')
  return `# Bounded offline replay of native-smoke-02

Status: **development integration replay; no model calls; no performance estimate**. Recorded on the user's local date 28 November 2026; original event UTC timestamps remain 27 November 2026.

## Actual inputs and scope

The replay reads the two saved host event logs and the resumed controller summary. It selects terminal \`item/completed\` command events, including the command whose terminal status is \`failed\`. The two supported Node/TAP executions are preserved completely. Other command events remain listed in \`command-inventory.json\`; original failed infrastructure attempts remain in the native-smoke directories and are not rewritten.

| Recorded phase | Original observation UTC | Exit code | Parsed test state | Saved stdout bytes |
|---|---|---:|---|---:|
${events}

Artifact mapping is **offline and known**: the controller summary maps prelude to the original \`sum.mjs\` digest and continuation to the changed digest. Actual \`cat sum.mjs\` and \`shasum -a 256 sum.mjs\` receipts independently agree with those values. The equal before/after hashes supplied to normalization are assigned from that mapping; they are not two independently observed live measurements around each execution. The digest covers \`sum.mjs\`, not a complete workspace or environment. Claim objects are manually constructed development inputs. No automatic model extraction or live object-state polling is established.

Every normalized source uses the actual log row's \`utc\`, not a fixed test-helper timestamp. The supplied logs already contain path redactions such as \`<RUN_ROOT>\`; this replay makes no further edits to their saved stdout. Source sequence 1/2 is the explicitly constructed order of these two completed test-state snapshots, not a claim that the host emitted those sequence numbers.

## Actual verifier outcomes

| Replay check | API outcome | API status | Reason | Reused | Original opens |
|---|---|---|---|---|---:|
${table}

**API interpretation:** \`supported\` means that the returned state has evidence. Therefore \`supported / failed\` supports the fact that the later test failed; it never means the tests passed or release was authorized. All packets have \`authorizesExecution=false\`.

The changed-version check before rerun uses the same one-event archive as the original check and a manually supplied changed digest. Its refusal is a version mismatch, not evidence of automatic workspace-change detection. After ingestion of the real later failure, the archive head changes and the old passing receipt cannot revive the earlier result. Historical queries are outside this API's current-snapshot replay.

## Storage and shared sources

Normalization feeds the real \`EvidenceArchive\`, which writes Memex L2 originals, searches them, and opens paginated records. \`memex-l2/\` retains this local store. \`archive-roundtrip.json\` records exact source and stdout equality after reopening. No mocked archive or retrieval callback is used.

The public exports are \`source-archive-prefix.json\` (one original test event) and \`source-archive.json\` (both actual test events). Both pass the repository's \`rawrag_adapter.validate_archive\` using its frozen limits. \`comparison-inputs.json\` gives B and D the **same source path and hash at each snapshot**, with the original logged phase request. Raw-RAG itself is **not run**; this is input compatibility, not a B-versus-D result. The public archives contain source metadata and original output, not development claims or scoring labels.

Completeness is asserted only for the two-file, supported Node/TAP execution stream admitted in this replay. It is not a complete natural-language lifecycle reconstruction, a claim about unobserved external changes, or a complete host-history corpus. Unsupported non-test commands are inventoried rather than treated as proof of test execution.

## Bounds and reproduction

The replay is limited to ${LIMITS.maxInputBytes} bytes per input, ${LIMITS.maxLogRows} rows per log, ${LIMITS.maxCommands} completed commands, two supported test events, and ${report.decisions.length} verifier calls. Each call permits ${LIMITS.maxHits} hits and ${LIMITS.maxEvidenceBytes} evidence bytes. The token guard is the verifier's conservative UTF-8-byte upper bound (${LIMITS.maxReferenceTokens}); reported referenceTokens are not tokenizer measurements. There are no model, embedding, reranker, or network calls.

From the repository root, run into a **new** output directory:

\`\`\`bash
node scripts/paper1/replay_native.mjs --output ${ARTIFACTS}/replay/native-smoke-02-rerun
node --test test/paper1-replay.mjs
\`\`\`

The script refuses to overwrite an existing output directory. Source archive content, UTC, output hashes, and decision states are reproducible; archive epochs and local storage metadata are run identities and may differ. Full decisions and traces are in \`replay-results.json\`. Input file hashes, manual artifact mapping, and captures are in \`input-manifest.json\`. Original user requests are copied without rewriting into \`requests/\`.

These checks exercise an offline development interface. They do not establish live native-host evidence delivery, automatic claim extraction, host decision improvement, Raw-RAG superiority, a paired trial, or a paper result.
`
}

export async function runReplay({ repositoryRoot = REPO, smokeRoot = join(REPO, ARTIFACTS, 'native-smoke'),
  outputDir = join(REPO, ARTIFACTS, 'replay/native-smoke-02') } = {}) {
  const data = loadReplayInputs(smokeRoot)
  outputDir = resolve(outputDir)
  assert.equal(existsSync(outputDir), false, 'output directory already exists; select a new directory')
  mkdirSync(dirname(outputDir), { recursive: true })
  mkdirSync(outputDir)
  const sources = data.selected.map(x => x.source)
  writeFileSync(join(outputDir, 'native-test-events.jsonl'), data.selected.map(x => x.raw).join('\n') + '\n')
  writeJson(join(outputDir, 'command-inventory.json'), data.inventory)
  writeJson(join(outputDir, 'input-manifest.json'), { schema: 1, inputRoot: relative(repositoryRoot, smokeRoot),
    files: data.inputFiles, threadId: data.summary.thread_id, bounds: LIMITS,
    artifactBindingMode: 'offline_known_controller_version_mapping_not_live_polling', bindings: data.bindings,
    captures: data.selected.map(x => ({ eventId: x.source.eventId, capture: x.capture,
      independentLiveBeforeAfterMeasurements: false })) })
  mkdirSync(join(outputDir, 'requests'))
  for (const [phase, request] of Object.entries(data.requests)) writeFileSync(join(outputDir, 'requests', `${phase}.txt`), request.text)
  const claim = version => ({ type: 'test_result', scope: sources[0].scope, entity: sources[0].entity, version })
  const originalClaim = claim(data.versions.original)
  const changedClaim = claim(data.versions.changed)
  writeJson(join(outputDir, 'claims.development.json'), { schema: 1,
    mode: 'manual_development_inputs_not_model_extraction', original: originalClaim, changed: changedClaim })
  const archive = new EvidenceArchive({ root: join(outputDir, 'memex-l2'), cwd: repositoryRoot,
    sessionId: data.summary.thread_id, pageChars: LIMITS.pageChars })
  const decisions = []
  const call = async (id, proposed, now, cached = null) => {
    const result = await verifyEvidence({ claim: proposed, now, cached, mode: 'selective',
      maxEvidenceBytes: LIMITS.maxEvidenceBytes, maxReferenceTokens: LIMITS.maxReferenceTokens, maxHits: LIMITS.maxHits }, archive)
    decisions.push({ id, claimInput: proposed, now, result })
    return result
  }
  try {
    archive.ingest([sources[0]], { recordId: 'native-replay-prelude' })
    archive.setSynchronized(true)
    const prefixView = await archive.readView(originalClaim)
    writeJson(join(outputDir, 'source-archive-prefix.json'), { schema: 1, taskId: 'native-smoke-02-test-stream',
      snapshot: { cutoff: data.bindings[0].readbackUtc, watermark: prefixView.watermark, complete: true }, sources: [sources[0]] })
    const initial = await call('original_pass', originalClaim, data.bindings[0].readbackUtc)
    const reused = await call('unchanged_original_reuse', originalClaim, data.bindings[0].readbackUtc, initial.receipt)
    const stale = await call('changed_version_before_rerun', changedClaim, data.bindings[1].readbackUtc, initial.receipt)
    archive.ingest([sources[1]], { recordId: 'native-replay-continuation' })
    archive.setSynchronized(true)
    const fullView = await archive.readView(changedClaim)
    writeJson(join(outputDir, 'source-archive.json'), { schema: 1, taskId: 'native-smoke-02-test-stream',
      snapshot: { cutoff: sources[1].observedAt, watermark: fullView.watermark, complete: true }, sources })
    const failure = await call('later_actual_failure', changedClaim, sources[1].observedAt, initial.receipt)
    const oldAfterFailure = await call('old_version_after_later_failure', originalClaim, sources[1].observedAt, initial.receipt)
    assert.equal(initial.outcome, 'supported'); assert.equal(initial.status, 'passed')
    assert.equal(reused.outcome, 'supported'); assert.equal(reused.status, 'passed'); assert.equal(reused.reused, true)
    assert.equal(stale.outcome, 'abstain'); assert.equal(stale.reason, 'version_mismatch'); assert.equal(stale.reused, false)
    assert.equal(failure.outcome, 'supported'); assert.equal(failure.status, 'failed'); assert.equal(failure.reused, false)
    assert.equal(oldAfterFailure.outcome, 'abstain'); assert.equal(oldAfterFailure.reason, 'version_mismatch')
    assert.notEqual(prefixView.watermark, fullView.watermark)
    assert.ok(decisions.every(x => x.result.authorizesExecution === false))
    const hits = await archive.search({ ...changedClaim, query: [changedClaim.scope, changedClaim.entity, changedClaim.type].join(' '), limit: LIMITS.maxHits })
    assert.equal(hits.length, sources.length)
    const roundtrip = []
    for (const hit of hits) {
      const opened = await archive.open(hit)
      const source = sources.find(s => s.eventId === hit.eventId)
      assert.deepEqual(opened, source)
      roundtrip.push({ eventId: hit.eventId, locator: hit, sourceSha256: digest(opened),
        stdoutSha256: sha256(opened.text), stdoutBytes: Buffer.byteLength(opened.text), exactOriginalPreserved: true })
    }
    writeJson(join(outputDir, 'archive-roundtrip.json'), roundtrip)
    writeJson(join(outputDir, 'catalog-final.json'), archive.catalog())
    const validation = validatePublicArchives(repositoryRoot,
      [join(outputDir, 'source-archive-prefix.json'), join(outputDir, 'source-archive.json')])
    writeJson(join(outputDir, 'public-archive-validation.json'), validation)
    const comparison = ['prelude', 'interleaved_update', 'continuation'].map(phase => {
      const archiveFile = phase === 'continuation' ? 'source-archive.json' : 'source-archive-prefix.json'
      const common = { sourceArchive: archiveFile, archiveSha256: sha256(readFileSync(join(outputDir, archiveFile))),
        originalRequest: `requests/${phase}.txt`, requestSha256: sha256(data.requests[phase].text) }
      return { phase, B_rawrag: { ...common, execution: 'not_run' }, D_typed: { ...common,
        execution: 'offline_manual_claim_replay_only' } }
    })
    writeJson(join(outputDir, 'comparison-inputs.json'), { schema: 1, pairedExperiment: false, snapshots: comparison })
    const report = { schema: 1, kind: 'bounded_offline_native_log_replay', confirmatory: false, modelCalls: 0,
      automaticClaimExtraction: false, liveWorkspaceBinding: false, rawragExecuted: false,
      inputFiles: data.inputFiles, bounds: LIMITS, publicArchiveValidation: validation,
      sources: data.selected.map(x => ({ eventId: x.source.eventId, phase: x.row.phase, utc: x.row.utc,
        exitCode: x.source.exitCode, status: x.source.status, version: x.source.version,
        stdoutBytes: Buffer.byteLength(x.source.text), stdoutSha256: sha256(x.source.text) })),
      decisions, checks: { twoActualTestEventsPreserved: true, rawragSchemaAccepted: true,
        sharedArchivePaths: true, originalSupported: true, changedVersionRejected: true,
        failureFactSupportedWithoutPassAssertion: true, oldReceiptNotRevived: true } }
    writeJson(join(outputDir, 'replay-results.json'), report)
    writeFileSync(join(outputDir, 'REPORT.md'), renderReport(report))
    return report
  } catch (error) {
    writeJson(join(outputDir, 'replay-error.json'), { status: 'failed', message: error.message, decisions })
    throw error
  } finally { archive.close() }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2)
  if (args.includes('--help')) {
    console.log('node scripts/paper1/replay_native.mjs [--output NEW_DIRECTORY] [--smoke-root SAVED_NATIVE_SMOKE_DIRECTORY]')
  } else {
    const options = {}
    while (args.length) {
      const flag = args.shift()
      assert.ok(['--output', '--smoke-root'].includes(flag) && args[0], 'unknown or incomplete argument')
      options[flag === '--output' ? 'outputDir' : 'smokeRoot'] = resolve(args.shift())
    }
    const result = await runReplay(options)
    console.log(JSON.stringify({ kind: result.kind, modelCalls: result.modelCalls,
      sources: result.sources.length, decisions: result.decisions.map(x => ({ check: x.id,
        outcome: x.result.outcome, status: x.result.status, reason: x.result.reason, reused: x.result.reused })),
      publicArchiveValidation: result.publicArchiveValidation }, null, 2))
  }
}
