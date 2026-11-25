/** Consume a provider stream with a bounded wait, even if it ignores abort. */
export async function consumeModelStream(llm, options, onChunk, { timeoutMs = 30000, signal, onDispatch } = {}) {
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs <= 0) throw new RangeError('model stream deadline must be positive')
  if (signal?.aborted) throw signal.reason ?? new DOMException('cancelled', 'AbortError')
  const controller = new AbortController()
  let interrupt
  const interrupted = new Promise((_, reject) => { interrupt = reason => { controller.abort(reason); reject(reason) } })
  const cancel = () => interrupt(signal.reason ?? new DOMException('cancelled', 'AbortError'))
  signal?.addEventListener('abort', cancel, { once: true })
  const timer = setTimeout(() => interrupt(new DOMException('model stream deadline exceeded', 'TimeoutError')), timeoutMs)
  const operation = (async () => {
    if (controller.signal.aborted) throw controller.signal.reason
    onDispatch?.()
    for await (const chunk of llm.stream({ ...options, signal: controller.signal })) {
      if (controller.signal.aborted) throw controller.signal.reason
      onChunk(chunk)
    }
  })()
  try { await Promise.race([operation, interrupted]) } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', cancel)
  }
}
