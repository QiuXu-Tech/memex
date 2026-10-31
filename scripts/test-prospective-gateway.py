#!/usr/bin/env python3
import datetime
import io
import json
import pathlib
import tempfile
import unittest
import urllib.error

import prospective_gateway as gateway


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({'id': 'r1', 'model': 'm', 'choices': [{'message': {'content': 'ok'},
                          'finish_reason': 'stop'}],
                          'usage': {'prompt_tokens': 7, 'completion_tokens': 2}}).encode()


def error(status, retry_after=None):
    headers = {} if retry_after is None else {'Retry-After': retry_after}
    return urllib.error.HTTPError('https://example.invalid', status, 'error', headers,
                                  io.BytesIO(b'{"error":{"code":"system_cpu_overloaded"}}'))


class Tests(unittest.TestCase):
    def run_call(self, responses):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        trace = pathlib.Path(folder.name) / 'calls.jsonl'
        delays = []
        def opener(request, timeout):
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        result = gateway.call('test-key', 'm', [{'role': 'user', 'content': 'x'}], 10,
                              trace, 'task', opener=opener, sleep=delays.append)
        events = [json.loads(line) for line in trace.read_text().splitlines()]
        self.assertNotIn('test-key', trace.read_text())
        return result, events, delays

    def test_explicit_503_then_success_keeps_both_attempts(self):
        result, events, delays = self.run_call([error(503, '3'), Response()])
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(delays, [3])
        self.assertEqual([e['status'] for e in events], ['started', 'http_error', 'started', 'ok'])
        self.assertEqual(events[1]['retryDelaySeconds'], 3)
        self.assertEqual(result['usage']['prompt_tokens'], 7)

    def test_three_503s_stop_without_fourth_call(self):
        result, events, delays = self.run_call([error(503), error(503), error(503)])
        self.assertEqual(result['httpStatus'], 503)
        self.assertEqual(delays, [2, 8])
        self.assertEqual(len(events), 6)

    def test_timeout_and_other_http_errors_are_not_retried(self):
        for failure in [TimeoutError(), error(403)]:
            result, events, delays = self.run_call([failure])
            self.assertNotEqual(result['status'], 'ok')
            self.assertEqual(delays, [])
            self.assertEqual(len(events), 2)

    def test_retry_after_longer_than_budget_stops(self):
        result, events, delays = self.run_call([error(503, '31')])
        self.assertEqual(result['httpStatus'], 503)
        self.assertEqual(delays, [])
        self.assertIsNone(events[-1]['retryDelaySeconds'])

    def test_retry_after_http_date(self):
        now = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        self.assertEqual(gateway.retry_delay('Thu, 01 Jan 2026 00:00:05 GMT', 2, now), 5)


if __name__ == '__main__':
    unittest.main()
