"""Distinguish a completed Codex turn from process shutdown status."""


def classify_turn(events, *, exit_code, timed_out):
    terminal = [(i, event.get('type')) for i, event in enumerate(events)
                if event.get('type') in ('turn.completed', 'turn.failed')]
    terminal_index, terminal_type = terminal[-1] if terminal else (len(events), None)
    messages = [event.get('item', {}).get('text', '') for event in events[:terminal_index]
                if event.get('type') == 'item.completed'
                and event.get('item', {}).get('type') == 'agent_message']
    answer = messages[-1] if messages else ''
    turn_completed = terminal_type == 'turn.completed'
    if timed_out:
        process_status = 'timeout_after_turn' if turn_completed else 'timeout_before_turn'
    elif exit_code == 0:
        process_status = 'exited_zero'
    else:
        process_status = 'exited_nonzero'
    return {'turnCompleted': turn_completed, 'answerPresent': turn_completed and bool(answer.strip()),
            'processStatus': process_status, 'answer': answer if turn_completed else ''}
