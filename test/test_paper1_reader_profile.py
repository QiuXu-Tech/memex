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
                                 'MEMEX_P1_RELAY_TOKEN': 'local-capability-12345678'})

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

    def test_nonlocal_relay_and_invalid_capability_rejected(self):
        for endpoint in ('https://api.deepseek.com', 'http://localhost:4321', 'http://127.0.0.1:99999',
                         'http://127.0.0.1:12/private', 'http://evil.test:80'):
            with self.assertRaises(reader.ProfileError):
                reader.codex_flags(endpoint)
        with self.assertRaises(reader.ProfileError):
            reader.host_environment('short')

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
