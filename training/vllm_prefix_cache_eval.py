#!/usr/bin/env python3
"""A-route prefix-cache probe against a local vLLM OpenAI server.

Sends two requests with the same long stable prefix + different suffix and
prints usage/prompt-cache fields. Used to verify that a materialized stable
prefix is actually reused by vLLM's paged-KV prefix cache.
"""
import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000/v1'
MODEL = sys.argv[2] if len(sys.argv) > 2 else 'Qwen/Qwen2.5-0.5B-Instruct'

def post(payload):
    req = urllib.request.Request(f'{BASE}/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.loads(response.read())

prefix = ('[EXTRA-CONTEXT MATERIALIZED WINDOW]\n' + '\n'.join(
    f'- context page mem_{index:010d}: exact archived content about component {index}; keep this for later questions.' for index in range(1, 80)
) + '\n[END MATERIALIZED WINDOW]\n\n')
for suffix in ['Question one: what did we decide about component 7?', 'Question two: what did we decide about component 42?']:
    data = post({'model': MODEL, 'messages': [{'role': 'user', 'content': prefix + suffix}], 'max_tokens': 8, 'temperature': 0})
    usage = data.get('usage', {})
    print(json.dumps({'suffix': suffix, 'usage': usage, 'text': data['choices'][0]['message']['content'][:80]}, ensure_ascii=False))
