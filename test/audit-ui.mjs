import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

const settle = () => new Promise(resolve => setImmediate(resolve))

test('F13: the actual panel ignores late bodies and continues the selected record', async () => {
  let definition, panel, cursor = 0
  const hooks = [], effects = [], pending = []
  const catalog = { ok: true, levels: { l3: true }, records: ['a', 'b'].map(id => ({ id, title: id, kind: 'fact', status: 'active' })) }
  const react = {
    Fragment: 'fragment',
    createElement: (type, props, ...children) => ({ type, props, children }),
    useState(initial) {
      const i = cursor++
      if (!(i in hooks)) hooks[i] = initial?.open === false ? { open: true, sessionId: 'test' } : initial
      return [hooks[i], next => { hooks[i] = typeof next === 'function' ? next(hooks[i]) : next }]
    },
    useRef(initial) { const i = cursor++; return hooks[i] ??= { current: initial } },
    useEffect(fn, deps) {
      const i = cursor++, previous = hooks[i]
      if (!previous || deps.some((v, j) => !Object.is(v, previous.deps[j]))) {
        effects.push(() => { previous?.cleanup?.(); hooks[i] = { deps, cleanup: fn() } })
      }
    },
  }
  runInNewContext(readFileSync(new URL('../packages/memex-ui/client.js', import.meta.url), 'utf8'), {
    window: { __ModuleLoader__: { load(value) { definition = value } }, addEventListener() {}, removeEventListener() {} },
    fetch: async url => {
      if (String(url).includes('memory.index')) return { ok: true, text: async () => JSON.stringify(catalog) }
      return new Promise(resolve => pending.push({ url: String(url), finish: body => resolve({ ok: true, text: async () => JSON.stringify({ ok: true, ...body }) }) }))
    },
    console,
  })
  definition.factory(() => react).apply({ effect() {}, slots: { inject(_name, callback) { callback() }, register(slot, component) { if (slot.id === 'memory-panel') panel = component } } })
  const render = () => { cursor = 0; const tree = panel(); while (effects.length) effects.shift()(); return tree }
  const rows = tree => {
    const found = []
    function visit(node) { if (!node || typeof node !== 'object') return; if (node.type?.name === 'MemoryRow') found.push(node); for (const child of (node.children ?? []).flat(Infinity)) visit(child) }
    visit(tree); return Object.fromEntries(found.map(row => [row.props.record.id, row.props]))
  }
  render(); await settle()
  rows(render()).a.onToggle()
  rows(render()).b.onToggle()
  pending[1].finish({ body: 'B-first', nextCharOffset: 7, truncated: true })
  await settle()
  pending[0].finish({ body: 'STALE-A', nextCharOffset: null, truncated: false })
  await settle()
  let current = rows(render()).b
  assert.equal(current.expanded, true)
  assert.equal(current.body, 'B-first')
  assert.equal(current.nextOffset, 7)
  current.onReadMore()
  assert.match(pending[2].url, /offset=7/)
  pending[2].finish({ body: '-last', nextCharOffset: null, truncated: false })
  await settle()
  current = rows(render()).b
  assert.equal(current.body, 'B-first-last')
  assert.equal(current.nextOffset, null)
  current.onToggle()
  assert.equal(rows(render()).b.expanded, false)
})
