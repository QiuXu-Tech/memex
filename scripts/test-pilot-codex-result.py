#!/usr/bin/env python3
"""Exercise turn completion independently from process termination."""
from pilot_codex_result import classify_turn

message = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'answer'}}
done = {'type': 'turn.completed', 'usage': {'input_tokens': 123}}
ok = classify_turn([message, done], exit_code=0, timed_out=False)
assert ok == {'turnCompleted': True, 'answerPresent': True, 'processStatus': 'exited_zero', 'answer': 'answer'}
shutdown_timeout = classify_turn([message, done], exit_code=-15, timed_out=True)
assert shutdown_timeout['turnCompleted'] and shutdown_timeout['answer'] == 'answer'
assert shutdown_timeout['processStatus'] == 'timeout_after_turn'
turn_timeout = classify_turn([message], exit_code=-15, timed_out=True)
assert not turn_timeout['turnCompleted'] and not turn_timeout['answerPresent'] and turn_timeout['answer'] == ''
assert turn_timeout['processStatus'] == 'timeout_before_turn'
missing = classify_turn([done], exit_code=0, timed_out=False)
assert missing['turnCompleted'] and not missing['answerPresent']
failed = classify_turn([message, done, {'type': 'turn.failed'}], exit_code=1, timed_out=False)
assert not failed['turnCompleted'] and failed['answer'] == ''
print('pilot Codex turn and process status regression passed')
