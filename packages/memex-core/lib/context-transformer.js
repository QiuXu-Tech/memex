/**
 * Transformer context-specialist (step 3 reference implementation).
 *
 * Loads the tiny transformer trained by `training/context_encoder.py` and
 * computes relevance logits in pure JS. The weights file is the contract;
 * a larger per-family encoder can replace it with the same architecture/config.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

export const CONTEXT_TRANSFORMER_VERSION = '0.13.0'
export const DEFAULT_CONTEXT_TRANSFORMER_WEIGHTS = fileURLToPath(new URL('../../../docs/assets/benchmarks/context-encoder-weights.json', import.meta.url))

const FNV_OFFSET = 0x811c9dc5
const FNV_PRIME = 0x01000193
function fnv1a(text) {
  let hash = FNV_OFFSET
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index)
    hash = Math.imul(hash, FNV_PRIME) >>> 0
  }
  return hash >>> 0
}
export function tokenizeContextText(text, vocab) {
  return [...String(text ?? '').toLowerCase().matchAll(/[a-z0-9]+/g)].map((match) => fnv1a(match[0]) % vocab)
}
const gelu = (value) => 0.5 * value * (1 + erf(value / Math.SQRT2))
function erf(value) {
  // Abramowitz-Stegun 7.1.26 approximation.
  const sign = value < 0 ? -1 : 1
  const x = Math.abs(value)
  const t = 1 / (1 + 0.3275911 * x)
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x)
  return sign * y
}
const linear = (vector, weights, bias) => weights.map((row, index) => row.reduce((sum, value, column) => sum + value * (vector[column] ?? 0), 0) + (bias?.[index] ?? 0))
const layerNorm = (vector, weight, bias, eps = 1e-5) => {
  const mean = vector.reduce((sum, value) => sum + value, 0) / Math.max(1, vector.length)
  const variance = vector.reduce((sum, value) => sum + (value - mean) ** 2, 0) / Math.max(1, vector.length)
  return vector.map((value, index) => ((value - mean) / Math.sqrt(variance + eps)) * (weight?.[index] ?? 1) + (bias?.[index] ?? 0))
}
const softmax = (values, mask) => {
  const max = Math.max(...values.map((value, index) => mask?.[index] === 0 ? -1e9 : value))
  const exps = values.map((value, index) => mask?.[index] === 0 ? 0 : Math.exp(value - max))
  const total = exps.reduce((sum, value) => sum + value, 0) || 1
  return exps.map((value) => value / total)
}

function applyEncoderLayer(h, mask, layer) {
  const dim = h[0].length
  const heads = layer.heads
  const headDim = dim / heads
  const qkv = h.map((vector) => linear(vector, layer.qkv_w, layer.qkv_b))
  const q = [], k = [], v = []
  for (let head = 0; head < heads; head += 1) {
    q.push(qkv.map((vector) => vector.slice(head * headDim, (head + 1) * headDim)))
    k.push(qkv.map((vector) => vector.slice(dim + head * headDim, dim + (head + 1) * headDim)))
    v.push(qkv.map((vector) => vector.slice(2 * dim + head * headDim, 2 * dim + (head + 1) * headDim)))
  }
  const context = Array.from({ length: h.length }, () => new Array(dim).fill(0))
  for (let head = 0; head < heads; head += 1) {
    for (let position = 0; position < h.length; position += 1) {
      const scores = k[head].map((keyVector, keyIndex) => q[head][position].reduce((sum, value, index) => sum + value * keyVector[index], 0) / Math.sqrt(headDim))
      const attention = softmax(scores, mask)
      for (let keyIndex = 0; keyIndex < attention.length; keyIndex += 1) {
        if (attention[keyIndex] === 0) continue
        for (let column = 0; column < headDim; column += 1) context[position][head * headDim + column] += attention[keyIndex] * v[head][keyIndex][column]
      }
    }
  }
  const h1 = h.map((vector, position) => layerNorm(vector.map((value, index) => value + linear(context[position], layer.out_w, layer.out_b)[index]), layer.ln1_w, layer.ln1_b))
  return h1.map((vector) => layerNorm(vector.map((value, index) => value + linear(geluVector(linear(vector, layer.ff1_w, layer.ff1_b)), layer.ff2_w, layer.ff2_b)[index]), layer.ln2_w, layer.ln2_b))
}

export class TransformerContextEncoder {
  constructor(weights) {
    this.weights = weights
    this.config = weights.config
    this.id = weights.model ?? 'memex-context-encoder-transformer-v0'
  }
  static load(path = DEFAULT_CONTEXT_TRANSFORMER_WEIGHTS) {
    return new TransformerContextEncoder(JSON.parse(readFileSync(path, 'utf8')))
  }
  /** Build fixed-length token/mask arrays for query + page. */
  encode(query, page) {
    const text = `${query} ${page.title ?? ''} ${page.summary ?? ''} ${page.body ?? ''}`
    const tokens = tokenizeContextText(text, this.config.vocab).slice(0, this.config.max_len)
    const mask = tokens.map(() => 1)
    while (tokens.length < this.config.max_len) { tokens.push(0); mask.push(0) }
    return { tokens, mask }
  }
  /** Forward pass; returns a relevance logit (higher = more relevant). */
  score(page, query) {
    const { tokens, mask } = this.encode(query, page)
    const weights = this.weights
    const dim = this.config.dim
    let h = tokens.map((token, position) => weights.token_emb[token].map((value, index) => value + weights.pos_emb[position][index]))
    if (Array.isArray(weights.layers) && weights.layers.length > 0) {
      for (const rawLayer of weights.layers) {
        const layer = {
          heads: this.config.heads,
          qkv_w: rawLayer['qkv.weight'], qkv_b: rawLayer['qkv.bias'],
          out_w: rawLayer['out.weight'], out_b: rawLayer['out.bias'],
          ff1_w: rawLayer['ff1.weight'], ff1_b: rawLayer['ff1.bias'],
          ff2_w: rawLayer['ff2.weight'], ff2_b: rawLayer['ff2.bias'],
          ln1_w: rawLayer['ln1.weight'], ln1_b: rawLayer['ln1.bias'],
          ln2_w: rawLayer['ln2.weight'], ln2_b: rawLayer['ln2.bias'],
        }
        h = applyEncoderLayer(h, mask, layer)
      }
    } else {
      h = applyEncoderLayer(h, mask, {
        heads: this.config.heads,
        qkv_w: weights.qkv_w, qkv_b: weights.qkv_b,
        out_w: weights.out_w, out_b: weights.out_b,
        ff1_w: weights.ff1_w, ff1_b: weights.ff1_b,
        ff2_w: weights.ff2_w, ff2_b: weights.ff2_b,
        ln1_w: weights.ln1_w, ln1_b: weights.ln1_b,
        ln2_w: weights.ln2_w, ln2_b: weights.ln2_b,
      })
    }
    const pooled = new Array(dim).fill(0)
    let count = 0
    for (let position = 0; position < this.config.max_len; position += 1) {
      if (mask[position] === 0) continue
      count += 1
      for (let column = 0; column < dim; column += 1) pooled[column] += h[position][column]
    }
    if (count > 0) for (let column = 0; column < dim; column += 1) pooled[column] /= count
    return linear(pooled, weights.head_w, weights.head_b)[0]
  }
  rank(pages, query) {
    return [...pages].map((page) => ({ page, score: this.score(page, query) })).sort((left, right) => right.score - left.score)
  }
}
const geluVector = (vector) => vector.map(gelu)

export function loadContextTransformer(path) {
  return TransformerContextEncoder.load(path)
}
