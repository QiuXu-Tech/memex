import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/paper1'))
import reader_profile as reader


class ReaderProfileTest(unittest.TestCase):
    def test_checked_profile_is_development_not_original_budget_freeze(self):
        profile = reader.load_profile()
        self.assertFalse(profile['formal_study_frozen'])
        self.assertFalse(profile['tokenizer']['provider_billable_input_exact'])
        self.assertEqual(profile['model'], 'deepseek-flash')

    def test_environment_does_not_forward_provider_secrets_or_controller_state(self):
        env = {'HOME': '/existing-user-home', 'PATH': '/bin', 'DEEPSEEK_API_KEY': 'not-a-real-key',
               'OPENAI_API_KEY': 'not-a-real-key', 'VECTORIZE_API_KEY': 'not-a-real-key',
               'CODEX_HOME': '/other', 'P1_CONTROLLER': '/private'}
        result = reader.host_environment('local-capability-12345678', env)
        self.assertEqual(result, {'HOME': env['HOME'], 'PATH': '/bin',
                                 'MEMEX_P1_RELAY_TOKEN': 'local-capability-12345678',
                                 'NO_PROXY': '127.0.0.1,localhost', 'no_proxy': '127.0.0.1,localhost'})

    def test_loopback_proxy_exceptions_are_exact_and_do_not_change_parent_environment(self):
        env = {'HOME': '/existing-user-home', 'PATH': '/bin',
               'HTTP_PROXY': 'http://fixture-private-proxy.invalid',
               'http_proxy': 'http://fixture-private-proxy.invalid',
               'HTTPS_PROXY': 'http://fixture-private-proxy.invalid',
               'https_proxy': 'http://fixture-private-proxy.invalid',
               'ALL_PROXY': 'socks5://fixture-private-proxy.invalid',
               'all_proxy': 'socks5://fixture-private-proxy.invalid',
               'NO_PROXY': '*,api.deepseek.com,.fixture-internal.invalid',
               'no_proxy': '*,api.deepseek.com,.fixture-internal.invalid',
               'DEEPSEEK_API_KEY': 'fixture-private-provider-value'}
        before = copy.deepcopy(env)
        result = reader.host_environment('local-capability-12345678', env)
        self.assertEqual(result.get('NO_PROXY'), '127.0.0.1,localhost')
        self.assertEqual(result.get('no_proxy'), '127.0.0.1,localhost')
        self.assertEqual(env, before)
        for name in ('HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy', 'ALL_PROXY', 'all_proxy'):
            self.assertNotIn(name, result)
        serialized = json.dumps(result)
        for private in ('fixture-private-proxy', 'fixture-private-provider-value', 'api.deepseek.com',
                        'fixture-internal', '*'):
            self.assertNotIn(private, serialized)

    def test_environment_never_reads_proxy_or_provider_credential_values(self):
        class ProtectedValues(dict):
            def __getitem__(self, key):
                if 'proxy' in key.lower() or key.endswith('_API_KEY'):
                    raise AssertionError('private proxy/provider values must not be read')
                return super().__getitem__(key)
        env = ProtectedValues({'HOME': '/existing-user-home', 'PATH': '/bin',
            'NO_PROXY': 'private-value', 'HTTP_PROXY': 'private-value', 'DEEPSEEK_API_KEY': 'private-value'})
        result = reader.host_environment('local-capability-12345678', env)
        self.assertEqual(result.get('NO_PROXY'), '127.0.0.1,localhost')
        self.assertEqual(result.get('no_proxy'), '127.0.0.1,localhost')

    def test_custom_provider_has_no_retries_or_builtin_exec(self):
        flags = reader.codex_flags('http://127.0.0.1:4321')
        entries = [flags[i + 1] for i in range(0, len(flags), 2)]
        values = dict(entry.split('=', 1) for entry in entries)
        self.assertEqual(len(values), len(entries))
        for name in ('features.shell_tool', 'features.unified_exec', 'features.apply_patch_freeform',
                     'features.apps', 'features.plugins', 'features.js_repl'):
            self.assertEqual(json.loads(values[name]), False)
        for name in ('request_max_retries', 'stream_max_retries'):
            self.assertEqual(json.loads(values['model_providers.memex_deepseek_p1.' + name]), 0)
        self.assertEqual(json.loads(values['model_provider']), 'memex_deepseek_p1')
        self.assertNotIn('features.respect_system_proxy', values)

    def test_nonlocal_relay_and_invalid_capability_rejected(self):
        for endpoint in ('https://api.deepseek.com', 'http://localhost:4321', 'http://127.0.0.1:99999',
                         'http://127.0.0.1:12/private', 'http://evil.test:80'):
            with self.assertRaises(reader.ProfileError):
                reader.codex_flags(endpoint)
        with self.assertRaises(reader.ProfileError):
            reader.host_environment('short')

    def test_custom_provider_disables_default_reasoning_summary(self):
        flags = reader.codex_flags('http://127.0.0.1:4321')
        values = dict(flags[i + 1].split('=', 1) for i in range(0, len(flags), 2))
        self.assertEqual(json.loads(values.get('model_reasoning_summary', 'null')), 'none')
        self.assertEqual(json.loads(values['model_reasoning_effort']), 'none')

    def test_builtin_plan_and_interactive_tools_are_explicitly_disabled(self):
        flags = reader.codex_flags('http://127.0.0.1:4321')
        values = dict(flags[i + 1].split('=', 1) for i in range(0, len(flags), 2))
        # The default-mode feature flag only restricts allowed modes in the
        # pinned host; these separate settings suppress tool registration.
        for name in ('tools.experimental_request_user_input.enabled', 'tools.update_plan.enabled'):
            with self.subTest(setting=name):
                self.assertIs(json.loads(values.get(name, 'null')), False)

    def test_tokenizer_digest_precedes_any_runtime_import_or_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'wrong-tokenizer.json'; path.write_text('{}')
            with self.assertRaisesRegex(reader.ProfileError, 'tokenizer_digest_mismatch'):
                reader.ReferenceTokenizer(path)

    def test_profile_increase_and_changed_shared_budget_rejected(self):
        profile = reader.load_profile()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'profile.json'
            for edit in ({'max_output_tokens': 1000000}, {'formal_study_frozen': True},
                         {'shared_budget_sha256': '0' * 64}, {'reasoning_effort': 'high'}):
                value = copy.deepcopy(profile); value.update(edit); path.write_text(json.dumps(value))
                with self.assertRaises(reader.ProfileError):
                    reader.load_profile(path)


if __name__ == '__main__':
    unittest.main()
