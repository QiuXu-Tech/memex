import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { AgentMemory } from '../packages/memex-core/lib/engine.js'

test('opt-in MCP search can open the matching original source outside its rendered card', () => {
  const fixture = mkdtempSync(join(tmpdir(), 'memex-source-locator-'))
  const cwd = join(fixture, 'workspace')
  const root = join(fixture, 'store')
  mkdirSync(cwd)
  const makeEngine = sessionId => new AgentMemory({ root, cwd, sessionId, levels: ['l2', 'l3'] })
  const visible = makeEngine('study')
  const foreign = makeEngine('other')
  try {
    const raw = { type: 'commandExecution', aggregatedOutput: '𝔄'.repeat(2_500) + ' QUEUECAPSULE77 evidence: failed, exit 17' }
    for (const [engine, id] of [[visible, 'visible'], [foreign, 'foreign']]) {
      engine.write({ id, scope: 'session', kind: 'episode', title: 'QUEUECAPSULE77 diagnostic',
        body: 'Rendered diagnostic excludes the tool receipt.', provenance: { shadowedSeqs: [20, 21] }, trust: 'untrusted' })
      engine.store.appendContextEvents({ recordId: id, events: [
        { sequence: 20, role: 'assistant', content: 'Draft handoff claims success.', attachments: [{ rawEvent: { role: 'assistant', text: 'Draft handoff claims success.' } }] },
        { sequence: 21, role: 'tool', content: raw.aggregatedOutput, attachments: [{ rawEvent: raw }] },
      ] })
    }
    const invoke = (...requests) => {
      const exchange = spawnSync(process.execPath, ['packages/memex-mcp/bin/server.mjs', '--cwd', cwd, '--root', root, '--session', 'study', '--levels', 'l2,l3'], {
        encoding: 'utf8',
        input: [
          { jsonrpc: '2.0', id: 0, method: 'initialize', params: { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'locator-test', version: '1' } } },
          ...requests.map((request, index) => ({ jsonrpc: '2.0', id: index + 1, method: 'tools/call', params: request })),
        ].map(value => JSON.stringify(value) + '\n').join(''),
      })
      assert.equal(exchange.status, 0, exchange.stderr)
      return exchange.stdout.trim().split('\n').slice(1).map(line => JSON.parse(line).result)
    }
    const search = sourceEvents => ({ name: 'memory_search', arguments: { query: 'QUEUECAPSULE77', sourceEvents } })
    const [normal, located, invalid] = invoke(search(undefined), search(true), search('yes'))
    assert.doesNotMatch(normal.content[0].text, /Source event:/)
    assert.equal(invalid.isError, true)
    const text = located.content[0].text
    assert.doesNotMatch(text, /foreign|failed, exit 17/)
    const locator = JSON.parse(text.match(/Source event: (\{[^\n]+\})/)[1])
    assert.equal(locator.id, 'visible')
    assert.equal(locator.eventIndex, 2)
    assert.ok(locator.charOffset > 4_000)
    const [result, denial] = invoke({ name: 'memory_open', arguments: { ...locator, maxChars: 400 } },
      { name: 'memory_open', arguments: { ...locator, id: 'foreign', maxChars: 400 } })
    assert.match(JSON.parse(result.content[0].text).content, /QUEUECAPSULE77 evidence: failed, exit 17/)
    assert.equal(denial.isError, true)
  } finally {
    visible.close()
    foreign.close()
    rmSync(fixture, { recursive: true, force: true })
  }
})
