/**
 * Context encoder seam (context-materialization step 3).
 *
 * The transformer specialist slot is intentionally an interface first: this
 * module ships a deterministic heuristic and a tiny trainable linear baseline
 * so callers can exercise salience scoring and train/evaluate a surrogate
 * offline. A transformer/cross-encoder can implement the same `score()` shape
 * without changing the materializer or pager.
 */
import { memoryQueryTerms } from '../index.js'

export const CONTEXT_ENCODER_INTERFACE_VERSION = '0.12.0'
export const CONTEXT_ENCODER_FEATURES = Object.freeze([
  'titleOverlap', 'summaryOverlap', 'useWhenOverlap', 'bodyOverlap',
  'recency', 'pinned', 'coldPenalty', 'lengthPenalty',
])

const lowerText = (text) => String(text ?? '').toLowerCase()
const countMatches = (text, terms) => terms.reduce((count, term) => count + (term.length >= 3 && lowerText(text).includes(term) ? 1 : 0), 0)

/** Deterministic feature vector in [0,1]-ish ranges. */
export function encoderFeatures(page = {}, query = '', { now = Date.now() } = {}) {
  const terms = [...new Set(memoryQueryTerms(query, 24).map((term) => term.toLowerCase()).filter((term) => term.length >= 3))]
  const denom = Math.max(1, terms.length)
  const ageDays = Math.max(0, (now - Number(page.createdAt ?? now)) / 86_400_000)
  return {
    titleOverlap: countMatches(page.title, terms) / denom,
    summaryOverlap: countMatches(page.summary, terms) / denom,
    useWhenOverlap: countMatches(page.useWhen, terms) / denom,
    bodyOverlap: countMatches(page.body, terms) / denom,
    recency: Math.max(0, 1 - ageDays / 30),
    pinned: page.status === 'pinned' ? 1 : 0,
    coldPenalty: page.cold === true ? 1 : 0,
    lengthPenalty: Math.min(1, String(page.body ?? '').length / 20_000),
  }
}

export class HeuristicContextEncoder {
  constructor({ weights } = {}) {
    this.id = 'heuristic-v1'
    this.weights = { titleOverlap: 4, summaryOverlap: 2, useWhenOverlap: 1, bodyOverlap: 1, recency: 1, pinned: 2, coldPenalty: -1, lengthPenalty: -0.5, ...(weights ?? {}) }
  }
  score(page, query, options) {
    const features = encoderFeatures(page, query, options)
    return CONTEXT_ENCODER_FEATURES.reduce((sum, name) => sum + (features[name] ?? 0) * (this.weights[name] ?? 0), 0)
  }
  rank(pages, query, options) { return [...pages].map((page) => ({ page, score: this.score(page, query, options) })).sort((a, b) => b.score - a.score) }
}

/** Tiny logistic-regression baseline; the transformer specialist can replace this class. */
export class LinearContextEncoder {
  constructor({ weights } = {}) {
    this.id = 'linear-v1'
    this.weights = { bias: 0, ...Object.fromEntries(CONTEXT_ENCODER_FEATURES.map((name) => [name, 0])), ...(weights ?? {}) }
  }
  score(page, query, options) {
    const features = encoderFeatures(page, query, options)
    return this.weights.bias + CONTEXT_ENCODER_FEATURES.reduce((sum, name) => sum + (features[name] ?? 0) * this.weights[name], 0)
  }
  probability(page, query, options) { return 1 / (1 + Math.exp(-this.score(page, query, options))) }
  rank(pages, query, options) { return [...pages].map((page) => ({ page, score: this.score(page, query, options) })).sort((a, b) => b.score - a.score) }
  /** Offline gradient descent; samples: `{page, query, label: 0|1}`. */
  static train(samples, { epochs = 200, learningRate = 0.1 } = {}) {
    const encoder = new LinearContextEncoder()
    const rows = (Array.isArray(samples) ? samples : []).filter((sample) => sample?.page !== undefined)
    for (let epoch = 0; epoch < epochs; epoch += 1) {
      const gradients = { bias: 0, ...Object.fromEntries(CONTEXT_ENCODER_FEATURES.map((name) => [name, 0])) }
      for (const sample of rows) {
        const features = encoderFeatures(sample.page, sample.query)
        const error = encoder.probability(sample.page, sample.query) - (sample.label === 1 ? 1 : 0)
        gradients.bias += error
        for (const name of CONTEXT_ENCODER_FEATURES) gradients[name] += error * (features[name] ?? 0)
      }
      const scale = learningRate / Math.max(1, rows.length)
      for (const name of Object.keys(gradients)) encoder.weights[name] -= scale * gradients[name]
    }
    return encoder
  }
}

export function createContextEncoder(type = 'heuristic', options) {
  return type === 'linear' ? new LinearContextEncoder(options) : new HeuristicContextEncoder(options)
}
