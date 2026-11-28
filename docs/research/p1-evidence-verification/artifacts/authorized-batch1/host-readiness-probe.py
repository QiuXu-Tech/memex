#!/usr/bin/env python3
"""Zero-generation native account-mode probe; never export account identifiers."""
import argparse
import json
from pathlib import Path
import runpy
import shutil

parser = argparse.ArgumentParser()
parser.add_argument('--runtime', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
runtime = args.runtime.resolve()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
smoke = runpy.run_path(str(runtime / 'scripts/paper1/native_smoke.py'))
helper = smoke['HOST']
logs = output / 'host'
logs.mkdir()
report = {'schema_version': 1, 'kind': 'zero_generation_account_mode_probe',
          'model_generation_starts': 0, 'compactions': 0, 'provider_api_requests': 0,
          'keys_read_or_created': False, 'personal_identifiers_exported': False}
host = None
try:
    host = smoke['TrialHost'](shutil.which('codex') or 'codex',
        helper['codex_overrides'](None, True), runtime, logs, __import__('os').environ.copy(), 45)
    host.rpc('initialize', {'clientInfo': {'name': 'p1_batch1_readiness', 'version': '0.1'},
                           'capabilities': {'experimentalApi': True}})
    host.send({'method': 'initialized', 'params': {}})
    value = host.rpc('account/read', {'refreshToken': False})
    account = value.get('account') or {}
    report['account_type'] = account.get('type')
    report['plan_type'] = account.get('planType')
    report['requires_openai_auth'] = value.get('requiresOpenaiAuth')
    value = host.rpc('account/rateLimits/read', None)
    rates = value.get('rateLimits') or {}
    report['rate_limits'] = {k: rates.get(k) for k in ('primary', 'secondary')}
    credits = rates.get('credits') or {}
    report['credits'] = {k: credits.get(k) for k in ('hasCredits', 'unlimited')}
    report['credits']['balance_field_present'] = credits.get('balance') is not None
    report['status'] = 'completed'
except Exception as error:
    report['status'] = 'blocked'
    report['error_type'] = type(error).__name__
finally:
    if host is not None:
        host.close()
(output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
