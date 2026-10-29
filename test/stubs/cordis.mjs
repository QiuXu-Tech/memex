/**
 * Offline stub for `@deepseek-ai/cordis`.
 *
 * The memory package only needs the base `Service` class: `MemoryStore` extends
 * it and calls `super(ctx, 'memory')` to expose itself as a cordis service.
 * Nothing from the real cordis runtime (fiber, plugin lifecycle, inject) is
 * exercised by these tests, so the stub is intentionally tiny.
 */
export class Service {
  constructor(ctx, name) {
    this.ctx = ctx
    this.name = name
  }
}

export default { Service }
