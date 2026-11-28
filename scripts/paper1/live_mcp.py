#!/usr/bin/env python3
"""Public MCP facade for the development broker; controller RPCs stay private.

This process exposes a fixed tool vocabulary. It is not a sandbox for arbitrary
code, and grants no access to the broker's extraction/verification controls.
"""
import argparse
import json
import socket
import sys

PUBLIC_NAMES = frozenset(('workspace_inspect', 'run_current_tests', 'record_decision'))
MAX_LINE = 131072
MAX_RESPONSE = 1048576


def broker_rpc(socket_path, message, *, timeout=30):
    payload = (json.dumps(message, ensure_ascii=False) + '\n').encode()
    if len(payload) > 100000:
        raise ValueError('broker_request_too_large')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(socket_path))
        client.sendall(payload)
        chunks = bytearray()
        while b'\n' not in chunks:
            part = client.recv(65536)
            if not part:
                raise RuntimeError('broker_closed_without_response')
            chunks.extend(part)
            if len(chunks) > MAX_RESPONSE:
                raise RuntimeError('broker_response_too_large')
        return json.loads(bytes(chunks).split(b'\n', 1)[0])


def dispatch(message, rpc):
    if not isinstance(message, dict):
        return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid Request'}}
    if 'id' not in message:
        return None
    reply = {'jsonrpc': '2.0', 'id': message['id']}
    method = message.get('method')
    params = message.get('params') or {}
    if method == 'initialize':
        reply['result'] = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}},
                           'serverInfo': {'name': 'p1-public-workspace', 'version': '0.1'}}
    elif method == 'ping':
        reply['result'] = {}
    elif method == 'tools/list':
        result = rpc({'op': 'tools'})
        if not result.get('ok'):
            reply['error'] = {'code': -32603, 'message': 'Tool catalog unavailable'}
        else:
            reply['result'] = {'tools': [t for t in result['result'] if t['name'] in PUBLIC_NAMES]}
    elif method == 'tools/call':
        name = params.get('name') if isinstance(params, dict) else None
        arguments = params.get('arguments', {}) if isinstance(params, dict) else {}
        if name not in PUBLIC_NAMES or not isinstance(arguments, dict):
            result = {'ok': False, 'error': 'unknown_public_tool_or_invalid_arguments'}
        else:
            try:
                result = rpc({'op': 'public', 'name': name, 'input': arguments})
            except (OSError, ValueError, RuntimeError) as error:
                result = {'ok': False, 'error': str(error)}
        reply['result'] = {'isError': not bool(result.get('ok')), 'content': [
            {'type': 'text', 'text': json.dumps(result.get('result') if result.get('ok') else
                                               {'error': result.get('error')}, ensure_ascii=False)}]}
    else:
        reply['error'] = {'code': -32601, 'message': 'Method not found'}
    return reply


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', required=True)
    args = parser.parse_args()
    while True:
        line = sys.stdin.buffer.readline(MAX_LINE + 1)
        if not line:
            break
        if len(line) > MAX_LINE or not line.endswith(b'\n'):
            raise SystemExit('MCP request line exceeds limit or lacks delimiter')
        try:
            response = dispatch(json.loads(line), lambda value: broker_rpc(args.socket, value))
        except (ValueError, OSError, RuntimeError, KeyError, TypeError):
            response = {'jsonrpc': '2.0', 'id': None,
                        'error': {'code': -32603, 'message': 'Public MCP request failed'}}
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + '\n')
            sys.stdout.flush()


if __name__ == '__main__':
    main()
