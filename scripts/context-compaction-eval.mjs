#!/usr/bin/env node
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { parseArgs } from 'node:util'
import { estimateTokens, memoryWorkspaceKey } from '../packages/memex-core/index.js'
import { registerCheckpointPolicy } from '../packages/memex-checkpoint/lib/checkpoint.js'
import LocalMemoryStore from '../packages/memex-local/index.js'
import { registerMemoryTools } from '../packages/memex-tool/lib/tools.js'
import { createFakeContext } from '../test/fake-ctx.mjs'
import { compactionTrajectories } from './context-compaction-fixture.mjs'

const { values: { out } } = parseArgs({ options: { out: { type: 'string' } } })
const BUDGETS = [1200, 2400]
const ARMS = ['rolling-summary', 'search-open', 'canonical-pager', 'query-ranked-pager']
const RERANKER = JSON.parse(readFileSync(new URL('../packages/memex-core/lib/lexical-reranker.json', import.meta.url), 'utf8'))
const MODEL_TASK = 'Use only the supplied evidence. Answer the question in one or two sentences and cite the source reference in square brackets when it supports the answer. If the evidence is missing or insufficient, say UNKNOWN and explain what is missing. Distinguish original user instructions and tool receipts from assistant handoffs.'
const BODY_OF = (event) => (event.data.message ?? event.data).content[0].text
const tokens = (text) => text.length === 0 ? 0 : estimateTokens(text)
const combine = (...sections) => sections.filter(Boolean).join('\n\n')
const fits = (text, budget) => tokens(text) <= budget

function rollSummary(previous, region) {
  const shortEvents = region.filter((event) => BODY_OF(event).length <= 280)
  const lines = shortEvents.map((event) => `${(event.data.message ?? event.data).role}: ${BODY_OF(event)}`)
  return [...previous, ...lines].slice(-4)
}

async function readTools(tool, query, common, budget) {
  const search = await tool('memory_search', { query, limit: 2 })
  const recordIds = [...search.matchAll(/^- (mem_[0-9a-f]+) \[/gm)].map((match) => match[1])
  const answers = fits(combine(common, search), budget) ? [search] : []
  let openCalls = 0
  for (const id of answers.length ? recordIds : []) {
    const envelopeAllowance = 850
    const remaining = budget * 4 - combine(common, ...answers).length - envelopeAllowance
    if (remaining < 2000) break // The rendered DSH tool has a 2,000-character minimum.
    const page = await tool('memory_open', { id, maxChars: Math.floor(remaining / Math.max(1, recordIds.length - openCalls)) })
    openCalls += 1
    if (fits(combine(common, ...answers, page), budget)) answers.push(page)
  }
  return { context: combine(common, ...answers), recordIds, toolCalls: 1 + openCalls }
}

function score(probe, arm, context, extra = {}) {
  const grounded = context.includes(probe.expected.receipt)
  const visibleLures = probe.lures.filter((lure) => context.includes(lure))
  return {
    arm,
    grounded,
    visibleLures,
    misleadingOnly: visibleLures.length > 0 && !grounded,
    estimatedEvidenceTokens: tokens(context),
    ...extra,
  }
}

async function roundTrip(tool, recordId, region) {
  for (const [index, event] of region.entries()) {
    let content = ''
    let charOffset = 0
    do {
      const page = JSON.parse(await tool('memory_open', { id: recordId, eventIndex: index + 1, charOffset, maxChars: 2000 }))
      assert.equal(page.sequence, event.seq)
      assert.equal(page.recordId, recordId)
      assert.equal(page.eventIndex, index + 1)
      assert.equal(page.eventCount, region.length)
      assert.equal(page.charOffset, charOffset)
      assert.ok(page.nextCharOffset === null || page.nextCharOffset > charOffset)
      content += page.content
      charOffset = page.nextCharOffset
    } while (charOffset !== null)
    assert.equal(content, JSON.stringify(event), `Source event ${event.seq} must round-trip exactly`)
  }
}

const root = mkdtempSync(join(tmpdir(), 'memex-context-compaction-'))
const rows = []
const archives = []
const packets = []
const keys = []
try {
  for (const trajectory of compactionTrajectories()) {
    const cwd = join(root, trajectory.id, 'project')
    mkdirSync(cwd, { recursive: true })
    const ctx = createFakeContext({ services: { llm: undefined } })
    const memory = new LocalMemoryStore(ctx, { root: join(root, trajectory.id, 'memory') })
    const session = { id: trajectory.id, header: { cwd } }
    const workspaceKey = memoryWorkspaceKey(cwd, session.id)
    await memory.enableLevel(session.id, 'l3')
    const policy = registerCheckpointPolicy(ctx, memory, { cardModel: 'off', autoRecall: false })
    registerMemoryTools(ctx, memory)
    const tool = (name, args) => ctx.tool(name).execute(args, { agent: { session } })
    let summary = []
    try {
      for (const [index, { region, tail, probes }] of trajectory.boundaries.entries()) {
        const boundary = index + 1
        const compactionId = `boundary-${boundary}`
        summary = rollSummary(summary, region)
        const regionTokens = tokens(region.map(BODY_OF).join('\n'))
        for (const event of region) await ctx.emit('session/event', session, event)
        await ctx.emit('session/event', session, {
          seq: region.at(-1).seq + 1,
          type: 'compaction/summary',
          data: { compactionId, shadowedSeqs: region.map(({ seq }) => seq), shadowedTokenCount: regionTokens,
            summary: [{ type: 'text', text: summary.join('\n') }] },
        })
        await policy.drain()
        const recordId = await memory.wasArchived(session.id, compactionId, { requireComplete: true })
        assert.ok(recordId, `Missing complete checkpoint for ${trajectory.id}/${compactionId}`)
        await roundTrip(tool, recordId, region)
        archives.push({ trajectory: trajectory.id, boundary, recordId, shadowed: region.length, estimatedRegionTokens: regionTokens, roundTripExact: region.length })
        const common = `Rolling handoff:\n${summary.join('\n')}\n\nRetained user message:\n${tail.receipt}`
        for (const budget of BUDGETS) for (const probe of probes) {
          const baseline = score(probe, ARMS[0], common)
          const available = budget - tokens(common) - 1
          const pagerRequest = {
            workspaceKey, scopes: ['workspace'], sessionId: session.id,
            query: probe.question, variant: 'timeline-exact', budgetTokens: available, pageTokenCap: 145,
            enforceTotalBudget: true,
          }
          const pagers = [
            [ARMS[2], await memory.materializeContext(pagerRequest)],
            [ARMS[3], await memory.materializeContext({ ...pagerRequest, learnedRerank: RERANKER, learnedTopK: 4 })],
          ]
          assert.ok(fits(common, budget))
          const pagedContexts = pagers.map(([arm, page]) => {
            const context = combine(common, page.text)
            assert.ok(fits(context, budget), `${arm} evidence exceeds ${budget} estimated tokens`)
            return { arm, context, pageIds: page.includedIds }
          })
          const { context: searchContext, ...searchDetails } = await readTools(tool, probe.question, common, budget)
          assert.ok(fits(searchContext, budget), `Tool evidence exceeds ${budget} estimated tokens`)
          const options = [
            baseline,
            score(probe, ARMS[1], searchContext, searchDetails),
            ...pagedContexts.map(({ arm, context, pageIds }) => score(probe, arm, context, { pageIds })),
          ]
          rows.push({ trajectory: trajectory.id, boundary, budget, probe: probe.id, evidenceRef: probe.expected.ref, expectedSequence: probe.expected.event.seq, options })
          if (out && budget === 2400 && ((boundary === 2 && probe.id === 'retained-tail') ||
            (boundary === 3 && ['old-constraint', 'latest-readback', 'verification-status', 'explicit-unknown', 'clipped-receipt'].includes(probe.id)))) {
            for (const { arm, context } of [{ arm: ARMS[0], context: common }, pagedContexts[1]]) {
              const id = createHash('sha256').update(JSON.stringify([trajectory.id, boundary, probe.id, arm])).digest('hex').slice(0, 12)
              packets.push({ id, question: probe.question, evidence: context })
              keys.push({ id, trajectory: trajectory.id, boundary, probe: probe.id, arm, source: probe.expected.receipt, sourceRole: (probe.expected.event.data.message ?? probe.expected.event.data).role, lures: probe.lures,
                sourceVisible: context.includes(probe.expected.receipt) })
            }
          }
        }
      }
      assert.deepEqual(ctx.logs.filter((line) => line.level === 'warn' || line.level === 'error'), [])
    } finally {
      policy.dispose()
      await ctx.dispose()
    }
  }
} finally {
  rmSync(root, { force: true, recursive: true })
}

const aggregate = BUDGETS.flatMap((budget) => ARMS.map((arm) => {
  const results = rows.filter((row) => row.budget === budget).map((row) => row.options.find((option) => option.arm === arm))
  return {
    budget,
    arm,
    probes: results.length,
    grounded: results.filter((result) => result.grounded).length,
    misleadingOnly: results.filter((result) => result.misleadingOnly).length,
    groundedWithLures: results.filter((result) => result.grounded && result.visibleLures.length > 0).length,
    evidenceTokensMean: Math.round(results.reduce((sum, result) => sum + result.estimatedEvidenceTokens, 0) / results.length),
    evidenceTokensMax: Math.max(...results.map((result) => result.estimatedEvidenceTokens)),
  }
}))
const report = { kind: 'synthetic-repeated-compaction', accounting: 'UTF-16 code units / 4, rounded up', archives, aggregate, rows }
if (out) {
  mkdirSync(out, { recursive: true })
  const write = (name, value) => writeFileSync(join(out, name), JSON.stringify(value, null, 2) + '\n', { flag: 'wx' })
  write('results.json', report)
  write('answer-packets.json', { instructions: MODEL_TASK, packets: packets.sort((left, right) => left.id.localeCompare(right.id)) })
  write('answer-key.json', { keys: keys.sort((left, right) => left.id.localeCompare(right.id)) })
}
console.log(JSON.stringify({ kind: report.kind, archives: archives.length, roundTripExact: archives.reduce((sum, entry) => sum + entry.roundTripExact, 0), aggregate }, null, 2))
