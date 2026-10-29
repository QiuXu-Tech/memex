/**
 * Mock Cordis context and service mocks for the offline memory tests.
 *
 * `createFakeContext()` implements exactly the surface the memory package
 * touches:
 *
 *   ctx.effect(fn)                  register a disposer callback
 *   ctx.systemPrompt.section(sec)  collect system-prompt sections
 *   ctx.tools.register(def)        collect model-facing tool definitions
 *   ctx.logger.warn/info           record log lines instead of printing them
 *   ctx.on(event, listener)        record listeners; `emit()` invokes them
 *   ctx.get(serviceName)           return a registered service mock
 *   ctx.memory                     service property, like a real cordis ctx
 *   ctx.provideService(name, val)  register a mock service (used by wiring tests)
 *
 * It additionally exposes the collected `defs` (tool definitions), `sections`,
 * `logs`, `listeners`, a `tool(name)` lookup and an async `emit()` helper so a
 * test can drive `session/event` and `agent/pre-step` exactly like the runtime
 * would.
 */
/**
 * Build an async-iterable LLM mock.
 *
 * `stream(options)` records the call and yields the standard chunk sequence:
 * text deltas, a block-end carrying the full text block, and a finish chunk.
 *
 * @param {object} [options] - Mock options.
 * @param {string} [options.text] - Response text the mock streams back.
 * @param {Array<object>} [options.extraChunks] - Extra chunks appended after the text block.
 * @returns {{ calls: object[], stream: (streamOptions: object) => AsyncIterable<object> }} Mock LLM service.
 */
export function createLlmMock(options = {}) {
  const text = typeof options.text === 'string' ? options.text : ''
  const extraChunks = Array.isArray(options.extraChunks) ? options.extraChunks : []
  const calls = []
  return {
    calls,
    stream(streamOptions) {
      calls.push(streamOptions)
      async function* generate() {
        const third = Math.ceil(text.length / 3)
        yield { type: 'text-delta', index: 0, text: text.slice(0, third) }
        yield { type: 'text-delta', index: 0, text: text.slice(third) }
        yield { type: 'block-end', index: 0, block: { type: 'text', text } }
        for (const chunk of extraChunks) yield chunk
        yield { type: 'finish', usage: { inputTokens: 10, outputTokens: 20 } }
      }
      return generate()
    },
  }
}

/**
 * Build a session-query service mock with the three methods the checkpoint
 * reconcile path uses.
 *
 * @param {Record<string, object[]>} [eventsBySession] - Raw events keyed by session id.
 * @returns {object} Mock `ctx.sessionQuery` service.
 */
export function createSessionQueryMock(eventsBySession = {}) {
  return {
    async readSession(id) {
      return { events: eventsBySession[id] ?? [] }
    },
    async listEvents(id) {
      return (eventsBySession[id] ?? []).map((event) => ({ seq: event.seq, type: event.type }))
    },
    async readEvent({ sessionId, seq }) {
      const target = (eventsBySession[sessionId] ?? []).find((event) => event.seq === seq)
      return { target }
    },
  }
}

/**
 * Create a mock cordis context.
 *
 * @param {object} [options] - Context options.
 * @param {object} [options.services] - Extra services; pass `{ llm: undefined }` to disable the default LLM mock.
 * @param {object} [options.llm] - Convenience for `options.services.llm`.
 * @param {object} [options.sessionQuery] - Convenience for `options.services.sessionQuery`.
 * @returns {object} Fake context.
 */
export function createFakeContext(options = {}) {
  /** @type {object[]} Registered tool definitions. */
  const defs = []
  /** @type {object[]} Registered system-prompt sections. */
  const sections = []
  /** @type {{level: string, args: unknown[]}[]} Recorded log lines. */
  const logs = []
  /** @type {Record<string, Function[]>} Event listeners by event name. */
  const listeners = Object.create(null)
  /** @type {Function[]} Effect disposers registered by the package. */
  const disposers = []
  const evicted = []

  const services = { ...(options.services ?? {}) }
  if (options.sessionQuery !== undefined) services.sessionQuery = options.sessionQuery
  if (options.llm !== undefined) services.llm = options.llm
  if (!('llm' in services)) services.llm = createLlmMock({ text: '' })

  function log(level, args) {
    logs.push({ level, args })
  }

  const ctx = {
    defs,
    sections,
    logs,
    listeners,
    services,
    /** All registered disposers run at teardown by `dispose()`. */
    disposers,

    /** Cordis effect: run the factory now and remember its disposer. */
    effect(factory) {
      const dispose = factory()
      if (typeof dispose === 'function') disposers.push(dispose)
      return dispose
    },

    systemPrompt: {
      section(section) {
        sections.push(section)
        return section
      },
    },

    tools: {
      register(definition) {
        defs.push(definition)
        return definition
      },
    },

    logger: {
      warn(...args) {
        log('warn', args)
      },
      info(...args) {
        log('info', args)
      },
      error(...args) {
        log('error', args)
      },
    },

    /** Register an event listener; `{ prepend: true }` puts it first. */
    on(eventName, listener, listenerOptions = {}) {
      const list = (listeners[eventName] ||= [])
      if (listenerOptions.prepend === true) list.unshift(listener)
      else list.push(listener)
      return () => {
        const index = list.indexOf(listener)
        if (index >= 0) list.splice(index, 1)
      }
    },

    /** Look up a service mock. */
    get(serviceName) {
      return services[serviceName]
    },

    /** Tool definition by name, or undefined. */
    tool(name) {
      return defs.find((definition) => definition.name === name)
    },

    /**
     * Invoke the listeners registered for one event.
     *
     * For `agent/pre-step` / `agent/post-step` (middleware-style events with a
     * `next()` continuation) the listeners run as a chain and the final
     * decision is returned. For every other event the listeners are awaited in
     * order and their results returned as an array.
     *
     * @param {string} eventName - Event name, e.g. `session/event`.
     * @param {...unknown} args - Payload followed by an optional terminal `next`.
     * @returns {Promise<unknown>} The last result / chained result.
     */
    async emit(eventName, ...args) {
      const list = [...(listeners[eventName] ?? [])]
      if (eventName.endsWith('pre-step') || eventName.endsWith('post-step')) {
        const payload = args[0]
        const terminal = typeof args[1] === 'function' ? args[1] : async (input) => input
        let cursor = 0
        const run = async () => {
          if (cursor >= list.length) return terminal(payload)
          const listener = list[cursor]
          cursor += 1
          return listener(payload, run)
        }
        return run()
      }
      const results = []
      for (const listener of list) results.push(await listener(...args))
      return results
    },

    /** Run all registered effect disposers (closes the store, disposes policy). */
    async dispose() {
      while (disposers.length > 0) {
        const disposer = disposers.pop()
        try {
          await disposer()
        } catch (error) {
          log('error', [`disposer failed: ${String(error?.message ?? error)}`])
        }
      }
    },

    /**
     * Register a mock service both for `ctx.get(name)` and as a property
     * (`ctx.memory`), matching how a real cordis context exposes services.
     * Re-providing a name swaps the value behind the same getter.
     *
     * @param {string} serviceName - Service name, e.g. `'memory'`.
     * @param {unknown} value - Service instance or mock.
     * @returns {unknown} The provided value.
     */
    provideService(serviceName, value) {
      services[serviceName] = value
      defineServiceProperty(serviceName)
      return value
    },

    /** Escape hatch for teardown: forget recorded state. */
    resetListeners() {
      for (const key of Object.keys(listeners)) delete listeners[key]
    },
  }

  /** Expose one service as a read-only ctx property (like cordis does). */
  function defineServiceProperty(serviceName) {
    Object.defineProperty(ctx, serviceName, {
      configurable: true,
      enumerable: true,
      get: () => services[serviceName],
    })
  }

  // Existing service mocks are also reachable as properties, not only get().
  for (const serviceName of Object.keys(services)) defineServiceProperty(serviceName)

  return ctx
}

/** Format recorded logs for a failure message. */
export function formatLogs(logs) {
  return logs
    .map(({ level, args }) => `${level}: ${args.map((arg) => (typeof arg === 'string' ? arg : String(arg))).join(' ')}`)
    .join('\n')
}
