/**
 * Offline stub for `@deepseek-ai/dsh-compaction`.
 *
 * The memory-evict row uses `toolPairingBalancedBefore(session, seq)` to avoid
 * cutting a split tool-call/tool-result pair. The real helper inspects the
 * session's events; this stub lets the fake session decide:
 *
 * - if the session exposes `__balancedBefore(seq)`, delegate to it;
 * - otherwise the cut is always balanced.
 */
export function toolPairingBalancedBefore(session, seq) {
  if (typeof session?.__balancedBefore === 'function') return session.__balancedBefore(seq) === true
  return true
}

export default { toolPairingBalancedBefore }
