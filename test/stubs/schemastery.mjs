/**
 * Offline stub for `@deepseek-ai/schemastery`.
 *
 * Static plugin configs (`static Config = z.object({...})`) are evaluated at
 * module-import time. The tests never validate or apply a config schema, so the
 * stub only has to be chainable and must never throw at import time:
 * `z.object(spec)`, `z.string()`, `z.number()`, `z.boolean()`, and the chain
 * methods `.default(v)`, `.step(n)`, `.min(n)`, `.max(n)` (each returns `this`).
 */

/** Attach the chainable schema DSL to a plain schema descriptor. */
function chainable(descriptor) {
  return {
    ...descriptor,
    /** Record the declared default and keep chaining. */
    default(value) {
      this.defaultValue = value
      return this
    },
    /** Record a numeric step and keep chaining. */
    step(value) {
      this.stepValue = value
      return this
    },
    /** Record a minimum and keep chaining. */
    min(value) {
      this.minValue = value
      return this
    },
    /** Record a maximum and keep chaining. */
    max(value) {
      this.maxValue = value
      return this
    },
    /** Cosmetic in the real library; keep chaining here too. */
    description(value) {
      this.descriptionValue = value
      return this
    },
    /** Cosmetic in the real library; keep chaining here too. */
    required() {
      this.isRequired = true
      return this
    },
    /** Cosmetic in the real library; keep chaining here too. */
    optional() {
      return this
    },
  }
}

const z = {
  object(spec) {
    return chainable({ type: 'object', properties: spec })
  },
  string() {
    return chainable({ type: 'string' })
  },
  number() {
    return chainable({ type: 'number' })
  },
  boolean() {
    return chainable({ type: 'boolean' })
  },
}

export default z
