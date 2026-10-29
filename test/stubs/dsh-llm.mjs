/**
 * Offline stub for `@deepseek-ai/dsh-llm`.
 *
 * Two exports are used by the memory package:
 *
 * - `createUserMessage(input)`: builds the frozen user message that the
 *   checkpoint policy injects for receipts, catalogues and recall.
 * - `BlockAssembler`: folds a streamed response into text blocks. The
 *   checkpoint policy's card-refinement step only needs `.push(chunk)` and
 *   `.blocks()`, but the stub also tracks `.finish` and `.usage` so a future
 *   caller of the real API keeps working.
 */

/**
 * Whether a content-block list carries an image (the archive is text-only, so
 * the eviction row refuses to move image-bearing messages out of L1).
 * @param {Array<object>} content - Message content blocks.
 * @returns {boolean} True when any block is an image.
 */
export function contentHasImage(content) {
  return (content ?? []).some((block) => (
    typeof block?.type === 'string' && (block.type === 'image' || block.type.startsWith('image'))
  ))
}

/** Monotonic counter so every injected message gets a stable, unique id. */
let messageCounter = 0

/**
 * Build a frozen user-role message.
 * @param {object} input - Message input.
 * @param {Array<object>} [input.content] - Content blocks.
 * @param {object} [input.source] - Message source payload.
 * @returns {Readonly<object>} Frozen user message.
 */
export function createUserMessage(input = {}) {
  messageCounter += 1
  return Object.freeze({
    id: `msg_${messageCounter}`,
    role: 'user',
    content: Array.isArray(input.content) ? input.content : [],
    source: input.source ?? {},
  })
}

/**
 * Minimal streaming response assembler.
 *
 * Accepts the chunk shapes the harness emits:
 * - `{ type: 'text-delta', index, text }`
 * - `{ type: 'block-end', index, block: { type: 'text', text } }`
 * - `{ type: 'finish', usage }`
 */
export class BlockAssembler {
  constructor() {
    /** @type {Map<number, string>} */
    this.textByIndex = new Map()
    this.finished = false
    this.usage = undefined
  }

  /**
   * Feed one stream chunk.
   * @param {object} chunk - Stream chunk.
   * @returns {this} This assembler, for chaining.
   */
  push(chunk) {
    if (chunk === null || typeof chunk !== 'object') return this
    const index = Number.isInteger(chunk.index) ? chunk.index : 0
    switch (chunk.type) {
      case 'text-delta':
        this.textByIndex.set(index, `${this.textByIndex.get(index) ?? ''}${String(chunk.text ?? '')}`)
        break
      case 'block-end': {
        const block = chunk.block ?? {}
        const text = typeof block.text === 'string' ? block.text : (this.textByIndex.get(index) ?? '')
        this.textByIndex.set(index, text)
        break
      }
      case 'finish':
      case 'done':
      case 'stream-end':
        this.finished = true
        this.usage = chunk.usage
        break
      default:
        break
    }
    return this
  }

  /** Whether a finish/done chunk was observed. */
  get finish() {
    return this.finished
  }

  /** Assembled text blocks in stream-index order. */
  blocks() {
    return [...this.textByIndex.entries()]
      .sort(([left], [right]) => left - right)
      .filter(([, text]) => text.length > 0)
      .map(([, text]) => ({ type: 'text', text }))
  }
}

export default { createUserMessage, BlockAssembler, contentHasImage }
