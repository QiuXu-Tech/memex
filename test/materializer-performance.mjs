import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { orderContextPages } from '../packages/memex-core/lib/context-events.js'
import { materializeContext } from '../packages/memex-core/lib/context-materializer.js'
import { orderContextPages as referenceOrder } from './reference/context-events.mjs'
import { materializeContext as referenceMaterialize } from './reference/context-materializer.mjs'
import { BENCHMARK_SEEDS, pagesFor, random } from './materializer-fixtures.mjs'

const freeze = pages => Object.freeze(pages.map(page => Object.freeze(page)))
function compareOrder(pages) {
  const before = [...pages]
  const expected = referenceOrder(pages), actual = orderContextPages(pages)
  assert.equal(actual.length, expected.length)
  for (let i = 0; i < actual.length; i++) assert.equal(actual[i], expected[i], `reference at ${i}`)
  assert.deepEqual(pages, before, 'input array must stay unchanged')
  return actual
}

function capture(fn) {
  try { return { result: fn() } } catch (error) { return { error: { name: error.name, message: error.message } } }
}

// Separate state for each implementation; compare every callback string,
// including rejected candidates and the callback which throws/returns NaN.
function compareMaterializers(input, mode = 'default') {
  const invoke = materialize => {
    const trace = []
    const tokenCounter = mode === 'default' ? undefined : text => {
      trace.push(text)
      if (mode === 'throw' && trace.length === 3) throw new Error('counter-stop')
      if (mode === 'invalid' && trace.length === 3) return NaN
      if (mode === 'nonmonotonic') return text.includes('needle') ? 1 : 10000
      if (mode === 'stateful') return Math.ceil(text.length / 4) + trace.length % 3
      return Math.ceil(Array.from(text).length / 3) + text.split('\n').length % 3
    }
    return { outcome: capture(() => materialize({ ...input, tokenCounter })), trace }
  }
  const expected = invoke(referenceMaterialize), actual = invoke(materializeContext)
  assert.deepEqual(actual, expected)
  return actual
}

test('frozen reference bodies match foundation sources after import relocation', () => {
  for (const [name, expected] of [
    ['context-events', '851ccc443ebec4ed99570aed77d1ddb3721761acf87345f260eb3679b2a324e0'],
    ['context-materializer', '6e44591c23ccdcd93095c3d48a7bb219e96469c73f530ccf1d16355ed0ebbab8'],
  ]) {
    const reference = readFileSync(new URL(`./reference/${name}.mjs`, import.meta.url), 'utf8')
    assert.ok(reference.startsWith('// Frozen reference: c3fa508e53043e40eb1022d3606f0d467219a6e2:'))
    const original = reference.split('\n').slice(3).join('\n')
      .replace("from '../../packages/memex-core/index.js'", "from '../index.js'")
      .replace("from './context-events.mjs'", "from './context-events.js'")
    assert.equal(createHash('sha256').update(original).digest('hex'), expected)
  }
})

for (const seed of BENCHMARK_SEEDS) {
  test(`order differential: seed ${seed}, 100 finite primitive cases`, () => {
    const rng = random(seed)
    for (let c = 0; c < 100; c++) {
      const n = 1 + Math.floor(rng() * 80), streams = 1 + Math.floor(rng() * n)
      const pages = pagesFor({ n, streams, chars: 0 }, seed + c).map((page, i) => ({
        ...page, id: i % 7 === 0 ? 'duplicate' : i % 5 === 0 ? (i % 2 ? 'é' : 'e\u0301') : page.id,
        sessionId: [undefined, null, '', 0, false, `s-${i % streams}`][Math.floor(rng() * 6)],
        sequence: Math.floor(rng() * 8) - 4, blockIndex: Math.floor(rng() * 4),
        createdAt: Math.floor(rng() * 10) - 5,
      }))
      compareOrder(freeze(pages))
    }
  })

  test(`materializer differential: seed ${seed}, 100 full-output / counter-trace cases`, () => {
    const rng = random(seed + 901)
    for (let c = 0; c < 100; c++) {
      const n = 1 + Math.floor(rng() * 24), streams = 1 + Math.floor(rng() * n)
      const pages = freeze(pagesFor({ n, streams, chars: 8 + Math.floor(rng() * 128), tools: c % 3 === 0 }, seed + c)
        .map((page, i) => ({ ...page, id: i % 7 === 0 ? 'duplicate' : page.id,
          sequence: Math.floor(rng() * 5), blockIndex: i % 3, createdAt: Math.floor(rng() * 8),
          body: i % 5 === 0 ? `needle 汉😀\n\t\ufeff ${page.body} \n` : page.body,
        })))
      const input = { pages, budgetTokens: [0, 1, 45, 120, 2400][c % 5], reserveTokens: c % 7,
        variant: ['timeline-exact', 'edge-attention', 'context-specialist-v1'][c % 3],
        pinnedIds: c % 2 ? [pages[0].id] : [], alwaysIncludeIds: c % 3 ? [] : [pages.at(-1).id],
        enforceTotalBudget: c % 2 === 0, pageTokenCap: [0, 12, 40][c % 3],
        query: 'needle 汉', queryAlternatives: ['evidence'], diversify: c % 2 === 0,
        learnedTopK: 2, learnedPageMaxTokens: c % 2 ? 100 : 0 }
      if (c % 2) input.learnedRerank = { weights: [1, -1, 2, -2, 0, 0, 1], bias: -1 }
      else input.retrievedIds = [pages[0].recordId, pages.at(-1).recordId, pages[0].recordId]
      compareMaterializers(input, ['default', 'pure', 'nonmonotonic', 'stateful', 'throw', 'invalid'][c % 6])
    }
  })

  test(`indexed selection differential: seed ${seed}, 100 default-counter cases`, () => {
    const rng = random(seed + 4109)
    const keys = [undefined, null, NaN, -0, 0, '0', false, true, '', 'shared', Symbol.for('materializer-key')]
    for (let c = 0; c < 100; c++) {
      const n = 1 + Math.floor(rng() * 40)
      const pages = freeze(pagesFor({ n, streams: 1 + Math.floor(rng() * n), chars: 32, tools: true }, seed + c)
        .map((page, i) => ({ ...page,
          id: i % 11 === 0 ? 'duplicate' : page.id,
          sessionId: keys[Math.floor(rng() * keys.length)],
          toolCallId: keys[Math.floor(rng() * keys.length)],
          recordId: keys[Math.floor(rng() * keys.length)],
          type: ['message', 'tool_call', 'tool_result'][i % 3],
          createdAt: Math.floor(rng() * 10), sequence: Math.floor(rng() * 5),
        })))
      const input = { pages, budgetTokens: [0, 40, 120, 2400][c % 4], reserveTokens: c % 9,
        enforceTotalBudget: c % 2 === 0, pinnedIds: [pages[0].id], alwaysIncludeIds: [pages.at(-1).id],
        variant: ['timeline-exact', 'edge-attention', 'context-specialist-v1'][c % 3] }
      if (c % 2) Object.assign(input, { query: 'context evidence', queryAlternatives: ['汉'],
        learnedRerank: { weights: [1, -1, 2, -2, 0, 0, 1] }, learnedTopK: 3, diversify: c % 3 === 0 })
      else input.retrievedIds = [pages[0].recordId, pages.at(-1).recordId, pages[0].recordId, NaN, 'missing']
      compareMaterializers(input)
    }
  })

  test(`rendered-length boundaries: seed ${seed}, 100 fixtures at exact budget +/- 1`, () => {
    const rng = random(seed + 8031)
    const tails = ['', ' \t\r\n', '\u00a0\u3000\ufeff', '\u2028\u2029', '\u200b', '😀', '\ud800', '\udfff']
    for (let c = 0; c < 100; c++) {
      const n = 1 + Math.floor(rng() * 8)
      const pages = freeze(pagesFor({ n, streams: 1 + Math.floor(rng() * n), chars: 24 }, seed + c)
        .map((page, i) => ({ ...page,
          id: `${page.id}${i % 3 === 0 ? '\n汉😀' : ''}`,
          body: c % 7 === 0 ? null : `needle ${'x'.repeat(c % 4)}${tails[(c + i) % tails.length]}`,
          summary: i % 2 ? '' : 'summary fallback\n\t',
          title: [undefined, null, '', '汉😀\n title \t'][Math.floor(rng() * 4)],
          role: [undefined, null, '', 'tool', 0, false][Math.floor(rng() * 6)],
          useWhen: [undefined, null, '', 'when\n😀'][Math.floor(rng() * 4)],
          sequence: i, createdAt: Math.floor(rng() * 10),
          truncated: c % 3 === 0, sourceId: [undefined, null, '', 'source\n汉'][i % 4],
          tokenCount: c % 2 ? 1 : undefined,
        })))
      const input = { pages, reserveTokens: [0, 3.5, 20][c % 3],
        variant: ['timeline-exact', 'edge-attention', 'context-specialist-v1'][c % 3],
        pinnedIds: c % 3 === 0 ? [pages.at(-1).id] : [],
        alwaysIncludeIds: c % 4 === 0 ? [pages[0].id] : [],
        retrievedIds: [pages.at(-1).recordId, pages[0].recordId],
        enforceTotalBudget: c % 2 === 0, pageTokenCap: c % 5 === 0 ? 8 : 0,
        query: 'needle', queryAlternatives: ['fallback'] }
      const full = referenceMaterialize({ ...input, budgetTokens: 1000000 })
      for (const offset of [-1, 0, 1]) {
        const budgetTokens = Math.max(0, full.tokens + offset) + input.reserveTokens
        const { outcome } = compareMaterializers({ ...input, budgetTokens })
        assert.ok(outcome.result)
        const result = outcome.result
        assert.equal(result.tokens, result.text === '' ? 0 : Math.max(1, Math.ceil(result.text.length / 4)))
        if (input.enforceTotalBudget) assert.ok(result.tokens <= result.availableTokens)
      }
    }
  })
}

test('advancing queue stays before equal heads, independent of initial stream ordinal', () => {
  const pages = freeze([
    { id: 'a1', sessionId: 'a', sequence: 1, createdAt: 0 },
    { id: 'z', sessionId: 'a', sequence: 2, createdAt: 2, marker: 'a2' },
    { id: 'b1', sessionId: 'b', sequence: 1, createdAt: 1 },
    { id: 'z', sessionId: 'b', sequence: 2, createdAt: 2, marker: 'b2' },
  ])
  assert.deepEqual(compareOrder(pages).map(page => page.marker ?? page.id), ['a1', 'b1', 'b2', 'a2'])
})

test('Unicode-equivalent distinct IDs preserve the current stable queue tie', () => {
  const pages = freeze([
    { id: 'b-first', sessionId: 'b', sequence: 1, createdAt: 1 },
    { id: 'é', sessionId: 'b', sequence: 2, createdAt: 3 },
    { id: 'a-first', sessionId: 'a', sequence: 1, createdAt: 2 },
    { id: 'e\u0301', sessionId: 'a', sequence: 2, createdAt: 3 },
  ])
  assert.equal('é'.localeCompare('e\u0301'), 0)
  assert.deepEqual(compareOrder(pages).map(page => page.id), ['b-first', 'a-first', 'e\u0301', 'é'])
  compareMaterializers({ pages, budgetTokens: 10000 })
})

test('clock skew: full-order filtering is not selected-subset ordering', () => {
  const pages = freeze([
    { id: 'a1', sessionId: 'a', sequence: 1, createdAt: 10 },
    { id: 'a2', sessionId: 'a', sequence: 2, createdAt: 1 },
    { id: 'b1', sessionId: 'b', sequence: 1, createdAt: 5 },
  ])
  assert.deepEqual(compareOrder(pages).map(page => page.id), ['b1', 'a1', 'a2'])
  assert.deepEqual(compareOrder(pages.filter(page => page.id !== 'a1')).map(page => page.id), ['a2', 'b1'])
  compareMaterializers({ pages, pinnedIds: ['a2', 'b1'], budgetTokens: 120, enforceTotalBudget: true })
})

test('empty/single streams and missing/null/empty sessions retain identity and grouping', () => {
  compareOrder(freeze([]))
  compareOrder(freeze([{ id: 'only', sequence: 0 }]))
  const pages = freeze([
    { id: 'empty-late', sessionId: '', sequence: 2, createdAt: 1 },
    { id: 'empty-first', sessionId: '', sequence: 1, createdAt: 5 },
    { id: 'null-late', sessionId: null, sequence: 0, createdAt: 4 },
    { id: 'null-first', sessionId: null, sequence: 99, createdAt: 2 },
    { id: 'missing', sequence: 0, createdAt: 3 },
  ])
  assert.deepEqual(compareOrder(pages).map(page => page.id), ['null-first', 'missing', 'null-late', 'empty-first', 'empty-late'])
  compareOrder(freeze([{ id: 'b', sequence: 1 }, { id: 'a', sequence: 1 }]))
  const plain = Object.assign(Object.create(null), { id: 'plain', sequence: 0, createdAt: 0 })
  compareOrder(freeze([plain, { id: 'other', sequence: 1, createdAt: 1 }]))
})

test('nonfinite, nonnumeric and nonprimitive keys retain legacy results/errors', () => {
  for (const field of ['sequence', 'blockIndex', 'createdAt']) {
    for (const value of [NaN, Infinity, -Infinity, undefined, null, '2', false, 1n, Symbol('key'), { valueOf: () => 2 }]) {
      const pages = freeze([
        { id: 'a', sequence: 1, createdAt: 0, [field]: value },
        { id: 'b', sequence: 2, createdAt: 1 },
        { id: 'c', sequence: 0, createdAt: 2 },
      ])
      assert.deepEqual(capture(() => orderContextPages(pages)), capture(() => referenceOrder(pages)))
    }
  }
  for (const id of [undefined, null, 1, new String('a')]) {
    const pages = [{ id, sequence: 0 }, { id: 'b', sequence: 0 }]
    assert.deepEqual(capture(() => orderContextPages(pages)), capture(() => referenceOrder(pages)))
  }
})

test('accessor, Proxy and coercion fallback preserves observed access/callback trace', () => {
  for (const kind of ['getter', 'proxy', 'coercion', 'prototype']) {
    const invoke = order => {
      const trace = []
      let first = { id: 'a', sessionId: 'a', sequence: 1, createdAt: 2 }
      if (kind === 'getter') Object.defineProperty(first, 'createdAt', { get() { trace.push('time'); return 2 } })
      if (kind === 'proxy') first = new Proxy(first, { get(target, key, receiver) { trace.push(String(key)); return Reflect.get(target, key, receiver) } })
      if (kind === 'coercion') first.createdAt = { valueOf() { trace.push('coerce'); return 2 } }
      if (kind === 'prototype') first = Object.assign(Object.create({ get createdAt() { trace.push('inherited-time'); return 2 } }), { id: 'a', sessionId: 'a', sequence: 1 })
      const outcome = capture(() => order([first, { id: 'b', sessionId: 'b', sequence: 1, createdAt: 1 }, { id: 'c', sessionId: 'c', sequence: 1, createdAt: 3 }]).map(page => page.id))
      return { outcome, trace }
    }
    assert.deepEqual(invoke(orderContextPages), invoke(referenceOrder), kind)
  }
})

test('atomic tool groups, orphans and cross-session IDs match complete baseline metadata', () => {
  const pages = freeze([
    { id: 'call', sessionId: 's', sequence: 1, createdAt: 20, type: 'tool_call', toolCallId: 't', body: 'needle '.repeat(100) },
    { id: 'result', sessionId: 's', sequence: 2, createdAt: 10, type: 'tool_result', toolCallId: 't', body: 'answer' },
    { id: 'orphan', sessionId: 'other', sequence: 1, createdAt: 1, type: 'tool_result', toolCallId: 't', body: 'orphan' },
  ])
  for (const budgetTokens of [0, 60, 2000]) for (const enforceTotalBudget of [true, false]) {
    for (const mode of ['default', 'pure', 'nonmonotonic', 'stateful', 'throw', 'invalid']) {
      compareMaterializers({ pages, budgetTokens, enforceTotalBudget, alwaysIncludeIds: ['call'], pinnedIds: ['result'] }, mode)
    }
  }
})

test('dependency matching keeps strict-equality behavior for unusual session/tool IDs', () => {
  for (const sessionId of [undefined, null, '', NaN, -0, 0, '0']) {
    for (const toolCallId of [undefined, null, NaN, -0, 0, '0']) {
      const pages = freeze([
        { id: 'call', sessionId, toolCallId, type: 'tool_call', sequence: 1, createdAt: 2, body: 'needle' },
        { id: 'result', sessionId, toolCallId, type: 'tool_result', sequence: 2, createdAt: 1, body: 'result' },
        { id: 'other', sessionId: 'other', toolCallId, type: 'tool_result', sequence: 1, createdAt: 0, body: 'other' },
      ])
      for (const mode of ['default', 'stateful']) {
        compareMaterializers({ pages, budgetTokens: 1000, retrievedIds: ['call', 'call'], enforceTotalBudget: true }, mode)
      }
    }
  }
})

test('dynamic input fallback preserves access, coercion, iterator and counter traces', () => {
  for (const kind of ['input-getter', 'page-getter', 'page-proxy', 'key-object', 'body-object', 'coercion-throw', 'reranker-proxy', 'iterator', 'custom-mutation']) {
    const invoke = materialize => {
      const trace = []
      const pages = [
        { id: 'a', recordId: 'r-a', sessionId: 's', toolCallId: 't', type: 'tool_call', sequence: 1, createdAt: 2, title: 'needle', body: 'call' },
        { id: 'b', recordId: 'r-b', sessionId: 's', toolCallId: 't', type: 'tool_result', sequence: 2, createdAt: 1, title: 'needle', body: 'result' },
        { id: 'c', recordId: 'r-c', sequence: 1, createdAt: 0, body: 'ordinary' },
      ]
      const input = { pages, budgetTokens: 1000, retrievedIds: ['r-b', 'r-b', 'r-a'], enforceTotalBudget: true }
      if (kind === 'input-getter') Object.defineProperty(input, 'enforceTotalBudget', { get() { trace.push('enforce'); return true } })
      if (kind === 'page-getter') Object.defineProperty(pages[0], 'recordId', { enumerable: true, get() { trace.push('record-id'); return 'r-a' } })
      if (kind === 'page-proxy') pages[0] = new Proxy(pages[0], { get(target, key, receiver) { trace.push(`page:${String(key)}`); return Reflect.get(target, key, receiver) } })
      if (kind === 'key-object') {
        const key = { toString() { trace.push('key-string'); return 'shared' } }
        pages[0].toolCallId = key; pages[1].toolCallId = key
      }
      if (kind === 'body-object' || kind === 'coercion-throw') {
        let count = 0
        pages[0].body = { toString() {
          trace.push(`body:${++count}`)
          if (kind === 'coercion-throw' && count === 3) throw new Error('body-stop')
          return `needle-${count}`
        } }
      }
      if (kind === 'reranker-proxy') {
        input.query = 'needle'
        input.learnedRerank = new Proxy({ weights: [1, 0, 1], bias: 0 }, { get(target, key, receiver) { trace.push(`rank:${String(key)}`); return Reflect.get(target, key, receiver) } })
      }
      if (kind === 'iterator') input.retrievedIds[Symbol.iterator] = function* () {
        for (const id of ['r-b', 'r-b', 'r-a']) { trace.push(`yield:${id}`); yield id }
      }
      if (kind === 'custom-mutation') {
        let version = 0
        pages[0].body = { toString() { trace.push(`render:${version}`); return `needle-${version}` } }
        input.tokenCounter = text => { trace.push(`counter:${text}`); version++; return Math.ceil(text.length / 4) + version % 2 }
      }
      return { outcome: capture(() => materialize(input)), trace }
    }
    assert.deepEqual(invoke(materializeContext), invoke(referenceMaterialize), kind)
  }
})

test('conservative guard accepts no new failure from unused cyclic/deep/shared data', () => {
  const pages = freeze([{ id: 'a', sequence: 1, body: 'a' }, { id: 'b', sequence: 2, body: 'b' }])
  const cyclic = { pages, budgetTokens: 1000 }; cyclic.unused = cyclic
  compareMaterializers(cyclic)
  let deep = null
  for (let i = 0; i < 10000; i++) deep = { unused: deep }
  compareMaterializers({ pages, budgetTokens: 1000, unused: deep })
  const shared = ['a']
  compareMaterializers({ pages, budgetTokens: 1000, pinnedIds: shared, alwaysIncludeIds: shared })
})

test('all JS trailing whitespace, retained non-whitespace and final-page changes match exact budgets', () => {
  const endings = ['\t', '\n', '\v', '\f', '\r', ' ', '\u00a0', '\u1680',
    ...Array.from({ length: 11 }, (_, i) => String.fromCharCode(0x2000 + i)),
    '\u2028', '\u2029', '\u202f', '\u205f', '\u3000', '\ufeff',
    '\u0085', '\u180e', '\u200b', '\u2060', '😀', '\ud800', '\udfff']
  for (const tail of endings) {
    const pages = freeze([
      { id: 'old', sessionId: 'a', sequence: 1, createdAt: 10, body: `one${tail}` },
      { id: 'backwards', sessionId: 'a', sequence: 2, createdAt: 1, body: tail, title: '' },
      { id: 'other', sessionId: 'b', sequence: 1, createdAt: 5, body: `two${tail}`, role: null, useWhen: null },
    ])
    // Every subset may order differently from a filtered full stream. Test
    // internal whitespace becoming final (and vice versa) at the fit boundary.
    for (let mask = 1; mask < 8; mask++) {
      const subset = pages.filter((_, i) => mask & (1 << i))
      const full = referenceMaterialize({ pages: subset, budgetTokens: 10000 })
      for (const offset of [-1, 0, 1]) compareMaterializers({ pages: subset,
        budgetTokens: full.tokens + offset, enforceTotalBudget: true,
        pinnedIds: [subset.at(-1).id], retrievedIds: [subset[0].id] })
    }
  }
})

test('empty-body accounting, null fallback and empty budget probes retain separate token semantics', () => {
  for (const body of [undefined, null, '', ' \t\n', false, 0]) {
    const pages = freeze([{ id: 'empty-body', sequence: 1, body, summary: '' }])
    const { outcome } = compareMaterializers({ pages, budgetTokens: 1000 })
    assert.equal(outcome.result.budgetBreakdown.pageTokens, Math.max(1, Math.ceil(String(body ?? '').length / 4)))
  }
  for (const budgetTokens of [0, 1]) {
    assert.equal(compareMaterializers({ pages: [], budgetTokens }).outcome.result.tokens, 0)
    const pages = freeze([{ id: 'empty-group', sequence: 1, type: 'message', toolCallId: NaN }])
    const { outcome } = compareMaterializers({ pages, budgetTokens, enforceTotalBudget: true })
    assert.equal(outcome.result.tokens, 0)
    assert.deepEqual(outcome.result.omittedIds, budgetTokens === 0 ? ['empty-group'] : [])
  }
})

test('atomic tools, excerpts and core/pinned hard/soft probes agree at the complete rendered boundary', () => {
  const pages = freeze([
    { id: 'call', sessionId: 's', sequence: 1, createdAt: 20, type: 'tool_call', toolCallId: 't', body: '汉😀 '.repeat(70) + 'needle END \t\ufeff' },
    { id: 'result', sessionId: 's', sequence: 2, createdAt: 10, type: 'tool_result', toolCallId: 't', body: '\r\n\u3000', title: null, role: 'tool' },
    { id: 'ordinary', sequence: 1, createdAt: 15, body: 'ordinary\n\t', useWhen: null },
  ])
  for (const pageTokenCap of [0, 20]) for (const enforceTotalBudget of [false, true]) {
    for (const force of ['none', 'core', 'pinned']) {
      const input = { pages, pageTokenCap, enforceTotalBudget, query: 'needle', reserveTokens: 7,
        alwaysIncludeIds: force === 'core' ? ['call'] : [], pinnedIds: force === 'pinned' ? ['result'] : [] }
      const full = referenceMaterialize({ ...input, budgetTokens: 10000 })
      for (const budgetTokens of [0, 7, full.tokens + 6, full.tokens + 7, full.tokens + 8]) {
        for (const mode of ['default', 'pure', 'stateful', 'throw', 'invalid']) compareMaterializers({ ...input, budgetTokens }, mode)
      }
    }
  }
})

test('symbol fields preserve legacy rendering results or exceptions on the full-render path', () => {
  for (const field of ['body', 'summary', 'title', 'role', 'useWhen', 'sourceId', 'recordId', 'toolCallId', 'sessionId']) {
    const pages = freeze([{ id: 'symbol', sequence: 1, truncated: true, [field]: Symbol('value') }, { id: 'other', sequence: 2, body: '' }])
    for (const mode of ['default', 'stateful']) compareMaterializers({ pages, budgetTokens: 1000 }, mode)
  }
})

test('invalid budgets preserve exceptions before token callbacks', () => {
  for (const budgetTokens of [NaN, Infinity, -1]) {
    const actual = compareMaterializers({ pages: [], budgetTokens }, 'stateful')
    assert.equal(actual.outcome.error.name, 'RangeError')
    assert.deepEqual(actual.trace, [])
  }
})
