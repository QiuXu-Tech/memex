#!/usr/bin/env python3
"""Logged, bounded 503 recovery for newly registered pilot calls."""
import datetime
import email.utils
import json
import os
import time
import urllib.error
import urllib.request

BACKOFF_SECONDS = (2, 8)
MAX_RETRY_AFTER_SECONDS = 30


def _append(path, event):
    with path.open('a') as stream:
        os.chmod(path, 0o600)
        stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def retry_delay(header, fallback, now=None):
    if not header:
        return fallback
    try:
        seconds = float(header)
    except (TypeError, ValueError):
        try:
            date = email.utils.parsedate_to_datetime(header)
            if date.tzinfo is None:
                date = date.replace(tzinfo=datetime.timezone.utc)
            now = now or datetime.datetime.now(datetime.timezone.utc)
            seconds = (date - now).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return fallback
    if not 0 <= seconds <= MAX_RETRY_AFTER_SECONDS:
        return None
    return seconds


def call(key, model, messages, max_tokens, trace, label, tools=None, *,
         opener=None, sleep=None, timeout=120):
    """Retry only explicit HTTP 503 responses; never replay an ambiguous timeout."""
    opener = opener or urllib.request.urlopen
    sleep = sleep or time.sleep
    body = {'model': model, 'messages': messages, 'temperature': 0, 'max_tokens': max_tokens}
    if tools is not None:
        body['tools'] = tools
    if model == 'deepseek-flash':
        body['thinking'] = {'type': 'disabled'}
    raw = json.dumps(body, ensure_ascii=False).encode()

    for attempt in range(1, len(BACKOFF_SECONDS) + 2):
        event = {'label': f'{label}#attempt-{attempt}', 'operationLabel': label,
                 'attempt': attempt, 'model': model,
                 'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 'status': 'started', 'requestBytes': len(raw)}
        _append(trace, event)
        event = dict(event)
        started = time.monotonic()
        request = urllib.request.Request('https://apimaster.ai/v1/chat/completions',
                                         data=raw, headers={'Authorization': 'Bearer ' + key,
                                                            'Content-Type': 'application/json'})
        try:
            with opener(request, timeout=timeout) as response:
                data = response.read()
                result = json.loads(data)
                choice = result['choices'][0]
                message, usage = choice['message'], result.get('usage', {})
                if not isinstance(message, dict):
                    raise ValueError('malformed message')
                event.update(status='ok', httpStatus=response.status, responseBytes=len(data),
                             responseModel=result.get('model'), responseId=result.get('id'),
                             finishReason=choice.get('finish_reason'), message=message, usage=usage)
                if not isinstance(usage.get('prompt_tokens'), int) or not isinstance(usage.get('completion_tokens'), int):
                    event['status'] = 'missing_usage'
        except urllib.error.HTTPError as exc:
            data = exc.read()
            event.update(status='http_error', httpStatus=exc.code, responseBytes=len(data),
                         retryAfter=exc.headers.get('Retry-After'))
            try:
                event['errorCode'] = json.loads(data).get('error', {}).get('code')
            except (ValueError, AttributeError):
                event['errorCode'] = 'UNKNOWN'
        except Exception as exc:
            event.update(status='error', errorType=type(exc).__name__)
        event['elapsedSeconds'] = round(time.monotonic() - started, 3)

        delay = None
        if event['status'] == 'http_error' and event['httpStatus'] == 503 and attempt <= len(BACKOFF_SECONDS):
            delay = retry_delay(event.get('retryAfter'), BACKOFF_SECONDS[attempt - 1])
            event['retryDelaySeconds'] = delay
        _append(trace, event)
        if delay is None:
            return event
        sleep(delay)
    return event
