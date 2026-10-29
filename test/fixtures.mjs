/**
 * Fixtures shared by the memory test runner: session shims, raw session events,
 * a compaction summary event and user messages, all shaped exactly like the
 * harness types documented for the package.
 */
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { memoryWorkspaceKey } from '@qiuxu/memex-seam'

/** Fixed timestamp so archived record frontmatter is deterministic. */
export const BASE_TIME = 1_700_000_000_000

/**
 * Create a minimal session shim for the checkpoint policy.
 *
 * `header.cwd` drives the workspace key; `requestHeader()` supplies the
 * provider/model target used by optional card refinement.
 *
 * @param {object} [overrides] - Field overrides.
 * @param {string} [overrides.id] - Session id.
 * @param {string} [overrides.cwd] - Session working directory.
 * @returns {object} Session shim.
 */
export function createSession(overrides = {}) {
  const id = overrides.id ?? 'sess-1'
  const cwd = overrides.cwd ?? '/tmp/ws'
  return {
    id,
    header: { cwd },
    requestHeader() {
      return { config: { provider: 'p', model: 'm' } }
    },
  }
}

/**
 * Build the three "surface" session events the checkpoint policy buffers:
 * a user message, an assistant message with a tool call, and a tool result.
 *
 * @param {object} [options] - Fixture options.
 * @param {number} [options.startSeq] - First sequence number.
 * @returns {object[]} Raw session events.
 */
export function createSurfaceEvents(options = {}) {
  const start = Number.isInteger(options.startSeq) ? options.startSeq : 1
  return [
    {
      seq: start,
      time: BASE_TIME,
      type: 'user/message',
      data: {
        id: 'user-1',
        role: 'user',
        content: [{ type: 'text', text: 'Fix the ECONNREFUSED failure on port 8787' }],
        source: { kind: 'user' },
      },
    },
    {
      seq: start + 1,
      time: BASE_TIME + 1000,
      type: 'assistant/message',
      data: {
        message: {
          id: 'assistant-1',
          role: 'assistant',
          content: [
            { type: 'text', text: 'Reading the server log to find the listener.' },
            { type: 'tool-call', id: 'call-1', name: 'bash', arguments: JSON.stringify({ command: 'lsof -i :8787' }) },
          ],
          source: { kind: 'assistant' },
        },
      },
    },
    {
      seq: start + 2,
      time: BASE_TIME + 2000,
      type: 'tool/result',
      data: {
        message: {
          id: 'tool-1',
          role: 'tool',
          content: [{ type: 'text', text: 'ECONNREFUSED 127.0.0.1:8787 — no process is listening' }],
          source: { kind: 'tool' },
          isError: true,
        },
      },
    },
  ]
}

/**
 * Build one `compaction/summary` event covering the three surface events.
 *
 * @param {object} [overrides] - Field overrides.
 * @param {string} [overrides.compactionId] - Compaction id.
 * @param {number[]} [overrides.shadowedSeqs] - Shadowed sequence numbers.
 * @param {string} [overrides.summary] - Summary text.
 * @param {number} [overrides.shadowedTokenCount] - Estimated shadowed tokens.
 * @param {number} [overrides.seq] - Event sequence number.
 * @returns {object} Raw session event.
 */
export function createCompactionEvent(overrides = {}) {
  const seqs = overrides.shadowedSeqs ?? [1, 2, 3]
  return {
    seq: overrides.seq ?? seqs[seqs.length - 1] + 1,
    time: BASE_TIME + 3000,
    type: 'compaction/summary',
    data: {
      compactionId: overrides.compactionId ?? 'cmp-1',
      summary: [{ type: 'text', text: overrides.summary ?? 'Investigated ECONNREFUSED on port 8787 and found no listener.' }],
      shadowedRange: { start: seqs[0], end: seqs[seqs.length - 1] },
      shadowedSeqs: seqs,
      shadowedTokenCount: overrides.shadowedTokenCount ?? 1234,
      provider: 'p',
      model: 'm',
    },
  }
}

/**
 * Build a direct user message as it appears in a pre-step decision.
 *
 * @param {string} text - User text.
 * @returns {Readonly<object>} Frozen user message with `source.kind === 'user'`.
 */
export function directUserMessage(text) {
  return createUserMessage({
    source: { kind: 'user' },
    content: [{ type: 'text', text }],
  })
}

/**
 * The workspace key a session maps to.
 *
 * @param {object} session - Session shim.
 * @returns {string} 16-hex workspace key.
 */
export function workspaceKeyFor(session) {
  return memoryWorkspaceKey(session.header?.cwd, session.id)
}

/**
 * Build a pre-step decision whose message list carries one direct user message.
 *
 * @param {object} session - Session shim.
 * @param {string} text - Direct user text.
 * @returns {{kind: string, messages: object[]}} Decision.
 */
export function createPreStepDecision(session, text) {
  return { kind: 'enter', messages: [directUserMessage(text)] }
}

/**
 * The enqueue/terminal `next` used by every pre-step test.
 *
 * @param {{kind: string, messages: object[]}} decision - Decision to return.
 * @returns {() => Promise<object>} Terminal middleware.
 */
export function terminalNext(decision) {
  return async () => decision
}
