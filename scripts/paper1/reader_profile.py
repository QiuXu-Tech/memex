#!/usr/bin/env python3
"""Pinned common-reader configuration and actual offline reference tokenizer.

Reference JSON token counts are deliberately separate from provider billable
input. No byte/token conversion, alternate tokenizer, remote code, or network
fallback is provided. This module never starts Codex or reads API credentials.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy

HERE = Path(__file__).resolve().parent
BATCH = runpy.run_path(str(HERE / 'batch_limits.py'))
PROFILE = HERE / 'deepseek-reader-profile.json'
PROVIDER_ID = 'memex_deepseek_p1'


class ProfileError(ValueError):
    pass


def load_profile(path=PROFILE):
    value = BATCH['read_json'](path)
    fixed = {'schema_version': 1, 'kind': 'p1-deepseek-native-reader-profile',
             'provider': 'deepseek', 'model': 'deepseek-flash',
             'endpoint': 'https://api.deepseek.com/responses', 'reasoning_effort': 'none',
             'temperature': 0, 'retries': 0, 'formal_study_frozen': False}
    if any(value.get(k) != v for k, v in fixed.items()):
        raise ProfileError('unsupported_reader_profile')
    maxima = {'max_request_bytes': 262144, 'max_response_bytes': 4194304,
              'timeout_seconds': 30, 'max_output_tokens': 8192,
              'max_model_input_tokens': 65536, 'max_model_output_tokens': 8192,
              'max_http_dispatches': 8, 'reference_input_token_limit': 65536}
    if any(type(value.get(k)) is not int or not 0 < value[k] <= maximum for k, maximum in maxima.items()):
        raise ProfileError('reader_limit_outside_development_budget')
    if (value.get('tokenizer', {}).get('runtime') != 'tokenizers==0.22.2'
            or value['tokenizer'].get('provider_billable_input_exact') is not False
            or value.get('host', {}).get('provider_id') != PROVIDER_ID
            or value['host'].get('version') != '0.153.0'):
        raise ProfileError('reader_runtime_identity_mismatch')
    budget_path = HERE.parents[1] / 'docs/research/p1-evidence-verification/tasks/workflows/shared-budget.json'
    if hashlib.sha256(BATCH['regular_bytes'](budget_path)).hexdigest() != value.get('shared_budget_sha256'):
        raise ProfileError('original_shared_budget_drift')
    return value


class ReferenceTokenizer:
    def __init__(self, path, profile=None):
        self.profile = load_profile() if profile is None else profile
        raw = BATCH['regular_bytes'](path)
        expected = self.profile['tokenizer']['tokenizer_json_sha256']
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ProfileError('tokenizer_digest_mismatch')
        try:
            import tokenizers
        except ImportError:
            raise ProfileError('pinned_tokenizer_runtime_missing') from None
        if tokenizers.__version__ != '0.22.2':
            raise ProfileError('tokenizer_runtime_version_mismatch')
        # Data-only Rust tokenizer load: no pickle, Python module or remote code.
        self.engine = tokenizers.Tokenizer.from_str(raw.decode('utf-8'))
        self.identity = {'tokenizer_json_sha256': expected, 'runtime_version': tokenizers.__version__,
                         'add_special_tokens': False, 'vocab_size': self.engine.get_vocab_size(),
                         'provider_billable_input_exact': False}

    def __call__(self, text):
        if not isinstance(text, str):
            raise ProfileError('tokenizer_text_required')
        return len(self.engine.encode(text, add_special_tokens=False).ids)


def codex_flags(base_url, *, profile=None):
    """Per-process overrides; user files, approval policies and credentials stay owned by the user."""
    profile = load_profile() if profile is None else profile
    if not isinstance(base_url, str) or not re.fullmatch(r'http://127\.0\.0\.1:[1-9][0-9]{0,4}', base_url):
        raise ProfileError('loopback_relay_required')
    port = int(base_url.rsplit(':', 1)[1])
    if port > 65535:
        raise ProfileError('invalid_relay_port')
    host = runpy.run_path(str(HERE.parent / 'codex-retention-host.py'))
    flags = host['codex_overrides'](None, True)
    overrides = {
        'forced_login_method': 'api', 'model': profile['model'], 'model_provider': PROVIDER_ID,
        'model_reasoning_effort': 'none', 'model_reasoning_summary': 'none',
        'model_context_window': 1048576,
        'model_auto_compact_token_limit': 200000,
        'tools.experimental_request_user_input.enabled': False,
        'tools.update_plan.enabled': False,
        # Pinned 0.153 has separate default-on orchestrator capability gates;
        # skipping host skill discovery does not close these extension tools.
        'orchestrator.skills.enabled': False, 'orchestrator.mcp.enabled': False,
        'features.remote_models': False, 'features.responses_websockets': False,
        'features.responses_websockets_v2': False, 'features.unbounded_connection_retries': False,
        'model_providers.' + PROVIDER_ID + '.name': 'P1 scoped DeepSeek relay',
        'model_providers.' + PROVIDER_ID + '.base_url': base_url,
        'model_providers.' + PROVIDER_ID + '.env_key': 'MEMEX_P1_RELAY_TOKEN',
        'model_providers.' + PROVIDER_ID + '.wire_api': 'responses',
        'model_providers.' + PROVIDER_ID + '.requires_openai_auth': False,
        'model_providers.' + PROVIDER_ID + '.request_max_retries': 0,
        'model_providers.' + PROVIDER_ID + '.stream_max_retries': 0,
        'model_providers.' + PROVIDER_ID + '.stream_idle_timeout_ms': 35000,
        'model_providers.' + PROVIDER_ID + '.supports_websockets': False,
        'model_providers.' + PROVIDER_ID + '.supports_standalone_web_search': False,
    }
    # Dynamic public tools are the only executable surface in this protocol.
    # The relay independently rejects every other declared tool before dispatch.
    # Goals independently adds get/create/update to persistent threads. The
    # remaining gates below register utility tools or the code-mode executor;
    # explicit overrides also prevent inherited user feature settings doing so.
    for feature in ('apply_patch_freeform', 'unified_exec', 'experimental_use_unified_exec_tool',
                    'js_repl', 'js_repl_tools_only', 'code_mode', 'code_mode_host', 'code_mode_only',
                    'goals', 'sleep_tool', 'deferred_executor', 'request_permissions_tool',
                    'token_budget', 'current_time_reminder',
                    'browser_use', 'computer_use', 'image_generation', 'view_image',
                    'connectors', 'collab', 'collaboration_modes', 'enable_fanout',
                    'memory_tool', 'search_tool', 'tool_search', 'tool_suggest',
                    'skill_search', 'send_async_message', 'workspace_dependencies',
                    'default_mode_request_user_input', 'codex_hooks'):
        overrides['features.' + feature] = False
    # Keep one value per key rather than relying on duplicate -c precedence.
    existing = {flags[i + 1].split('=', 1)[0]: flags[i + 1].split('=', 1)[1]
                for i in range(0, len(flags), 2)}
    existing.update({key: json.dumps(value) for key, value in overrides.items()})
    return [part for key, value in existing.items() for part in ('-c', key + '=' + value)]


def host_environment(local_token, environ=None):
    if not isinstance(local_token, str) or not 16 <= len(local_token) <= 256 or '\n' in local_token:
        raise ProfileError('invalid_local_relay_capability')
    source = os.environ if environ is None else environ
    # Preserve the user's existing HOME only; never reassign it or CODEX_HOME.
    allowed = ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TZ', 'TMPDIR', 'SYSTEMROOT')
    result = {key: source[key] for key in allowed if key in source}
    result['MEMEX_P1_RELAY_TOKEN'] = local_token
    # The pinned reqwest path reads macOS proxy endpoints but not the system
    # exception list. Keep the local relay local without importing proxy URLs,
    # user bypass lists, or changing Codex/system proxy policy.
    result['NO_PROXY'] = '127.0.0.1,localhost'
    result['no_proxy'] = '127.0.0.1,localhost'
    return result
