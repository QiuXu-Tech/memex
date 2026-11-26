/** Build a session-private Memex archive from hash-checked original stdout lines. */
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { AgentMemory } from '../packages/memex-core/lib/engine.js'

const input = JSON.parse(readFileSync(0, 'utf8'))
const { root, cwd, session, workspaceScopes, threadId, itemId, stdoutSha256, sourceLines } = input
if (!Array.isArray(sourceLines) || !Array.isArray(workspaceScopes) || !itemId || !threadId) throw new Error('missing original source envelope')
const engine = new AgentMemory({ root, cwd, sessionId: session, levels: ['l2'] })
const captured = []
const seen = new Set()
try {
  for (const line of sourceLines) {
    if (typeof line !== 'string' || line.length > 80_000) throw new Error('invalid original source line')
    const receipt = JSON.parse(line)
    const { sourceRef, entity, type, scope, version, excerpt } = receipt
    if (![sourceRef, entity, type, scope, version, excerpt].every(field => typeof field === 'string' && field.trim())) {
      throw new Error('incomplete source identity')
    }
    if (!/^evt-[a-z0-9_.:-]+$/i.test(sourceRef) || seen.has(sourceRef)) throw new Error('duplicate or invalid source reference')
    seen.add(sourceRef)
    const sha256 = createHash('sha256').update(line).digest('hex')
    const visible = workspaceScopes.includes(scope)
    const sessionId = visible ? session : session + '-other'
    const rawEvent = { sourceRef, sourceLine: line, sha256, itemId, threadId, stdoutSha256 }
    engine.store.write({
      id: sourceRef, workspaceKey: engine.workspaceKey, scope: 'session', sessionId,
      kind: type === 'test_result' ? 'incident' : 'fact', trust: 'untrusted',
      title: entity + ' ' + type + ' ' + version,
      summary: excerpt, body: line,
      provenance: { shadowedSeqs: [1], evidence: { source: JSON.stringify([type, scope, entity]), version } },
    }, { archive: { sessionId, compactionId: sourceRef, events: [
      { sequence: 1, role: 'tool', type: 'tool_result', content: line, sessionId, attachments: [{ rawEvent }] },
    ] } })
    captured.push({ sourceRef, sha256, visible })
  }
  console.log(JSON.stringify({ threadId, itemId, captured }))
} finally {
  engine.close()
}
