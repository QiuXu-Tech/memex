/** Narrow, auditable native Node/TAP adapter; no learned semantic inference.
 * Capture metadata must be supplied by the host observer, never model output.
 * Unparsed relevant events must keep the caller's source view incomplete.
 */
export function normalizeNodeTestEvent(event, capture) {
  const reject = issue => ({ source: null, issue, invalidatesView: true })
  if (event?.type !== 'commandExecution' || typeof event.command !== 'string') return reject('not_native_command')
  const transportCommand = event.command.trim()
  const envelope = transportCommand.match(/^\/(?:[^\s/]+\/)*(?:zsh|bash|sh) -lc (['"])([^\r\n]*)\1$/)
  const command = (envelope ? envelope[2] : transportCommand).replace(/[\t ]+/g, ' ')
  const argv = command.split(' ')
  const executable = argv.shift()
  if (executable !== 'node' && executable !== capture?.nodeExecutable) return reject('unsupported_command')
  // --test must be a Node option, never a script argument or --eval payload.
  // This adapter intentionally supports only the two frozen smoke commands.
  if (argv.shift() !== '--test') return reject('unsupported_command')
  if (argv[0] === '--test-reporter=tap') argv.shift()
  if (argv.some(arg => !/^[a-zA-Z0-9_./-]+\.(?:mjs|cjs|js)$/.test(arg) || arg.startsWith('-'))
      || /[;&|<>$`\\\r\n]/.test(command)) return reject('unsupported_command')
  if (!capture || !['artifactBefore', 'artifactAfter'].every(k => /^[a-f0-9]{64}$/.test(capture[k] ?? ''))) return reject('missing_artifact_binding')
  if (capture.artifactBefore !== capture.artifactAfter) return reject('artifact_changed_during_execution')
  if (!['threadId', 'scope', 'observedAt'].every(k => typeof capture[k] === 'string' && capture[k].trim())
      || !Number.isFinite(Date.parse(capture.observedAt)) || !Number.isSafeInteger(capture.sourceSequence)
      || capture.sourceSequence < 1 || typeof event.id !== 'string' || !event.id.trim()) return reject('invalid_transport_metadata')
  if (!['completed', 'failed'].includes(event.status) || !Number.isSafeInteger(event.exitCode) || typeof event.aggregatedOutput !== 'string') return reject('incomplete_native_event')
  const output = event.aggregatedOutput.replace(/\u001b\[[0-9;]*m/g, '')
  const tap = /^TAP version 13\s*$/m.test(output)
    || (/^1\.\.\d+\s*$/m.test(output) && /^(?:not )?ok \d+(?:\s|$)/m.test(output))
  if (!tap || /(?:output truncated|truncated output)/i.test(output)) return reject('incomplete_test_output')
  const counts = {}
  for (const field of ['tests', 'pass', 'fail', 'cancelled', 'skipped']) {
    const matches = [...output.matchAll(new RegExp('^# ' + field + ' (\\d+)\\s*$', 'gm'))]
    if (matches.length !== 1) return reject('ambiguous_or_missing_test_footer')
    counts[field] = Number(matches[0][1])
  }
  const todo = Number(output.match(/^# todo (\d+)\s*$/m)?.[1] ?? 0)
  if (counts.tests < 1 || counts.pass + counts.fail < 1) return reject('no_tests_executed')
  if (counts.cancelled !== 0 || counts.pass + counts.fail + counts.skipped + todo !== counts.tests) return reject('incomplete_test_execution')
  const passed = event.exitCode === 0 && counts.fail === 0 && counts.pass > 0
  const failed = event.exitCode !== 0 && counts.fail > 0
  if (!passed && !failed) return reject('exit_result_mismatch')
  return { issue: null, invalidatesView: false, source: {
    eventId: event.id, sourceId: `${capture.threadId}:node-tests`, sourceSequence: capture.sourceSequence,
    observedAt: capture.observedAt, type: 'test_result', scope: capture.scope, entity: command,
    version: capture.artifactBefore, role: 'tool', kind: 'command_execution', command,
    status: passed ? 'passed' : 'failed', complete: true, completed: true, executed: true,
    exitCode: event.exitCode, testCount: counts.pass + counts.fail, skippedCount: counts.skipped,
    todoCount: todo, text: event.aggregatedOutput, parserVersion: 'native-node-tap-v1',
  } }
}
