import copy
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('p1_native_permit_test', ROOT / 'scripts/paper1/native_permit.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
AUTH = ROOT / 'docs/research/p1-evidence-verification/artifacts/authorized-batch1/authorization.json'


def consumer(path, sha, output, model, root, queue):
    try:
        M.admit_permit(path, sha, output=output, model=model, wall_seconds=300, source_root=root, consume=True)
        queue.put('consumed')
    except M.PermitError as exc:
        queue.put(str(exc))


class NativePermitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / 'source'
        self.root.mkdir()
        for relative in M.MANDATORY:
            p = self.root / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('controlled fixture, never executed: ' + relative)
        for relative in ('scripts/paper1/batch_limits.py', 'scripts/paper1/native_permit.py'):
            (self.root / relative).write_bytes((ROOT / relative).read_bytes())
        extra = self.root / 'packages/memex-core/lib/engine.js'
        extra.parent.mkdir(parents=True)
        extra.write_text('// controlled package member fixture\n')
        self.control = self.root / 'control'
        self.control.mkdir()
        (self.control / 'authorization.json').write_bytes(AUTH.read_bytes())
        self.auth_sha = hashlib.sha256(AUTH.read_bytes()).hexdigest()
        self.path = self.control / 'permit.json'
        self.output = self.root / 'runs/attempt-01'
        self.now = time.time_ns()
        reservation = {'seq': 1, 'previous_sha256': '0' * 64,
                       'authorization_sha256': self.auth_sha, 'at_unix_ns': self.now - 2 * 10**9,
                       'event': 'reserved', 'data': {
                           'attempt_id': 'native-01', 'kind': 'native', 'unit_key': None, 'public_sha256': None,
                           'upper_bound_fen': 0, 'wall_seconds': 600,
                           'billing_basis': {'kind': 'included_subscription',
                                             'evidence': {'ref': 'evidence/subscription.json', 'sha256': 'a' * 64}}}}
        reservation['sha256'] = M.digest(reservation)
        self.permit = {'schema_version': 1, 'kind': M.KIND, 'batch_id': M.BATCH_ID,
                       'permit_path': str(self.path), 'source_root': str(self.root),
                       'authorization_file': 'authorization.json', 'authorization_sha256': self.auth_sha,
                       'reservation': reservation, 'output': str(self.output), 'model': 'gpt-5.6-sol',
                       'wall_seconds': 300, 'issued_at_unix_ns': self.now - 10**9,
                       'expires_at_unix_ns': self.now + 598 * 10**9,
                       'runtime_sha256': M.runtime_manifest(self.root), 'scope': copy.deepcopy(M.SCOPE)}
        self.write()

    def write(self):
        self.path.write_text(json.dumps(self.permit, ensure_ascii=False, indent=2) + '\n')
        self.expected = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def admit(self, **kwargs):
        arguments = dict(output=self.output, model='gpt-5.6-sol', wall_seconds=300, source_root=self.root)
        arguments.update(kwargs)
        return M.admit_permit(self.path, self.expected, **arguments)

    def files(self):
        return {p.relative_to(self.base).as_posix() for p in self.base.rglob('*')}

    def assert_rejected_without_write(self, code, **kwargs):
        before = self.files()
        output_existed = self.output.exists()
        with self.assertRaisesRegex(M.PermitError, code):
            self.admit(consume=True, **kwargs)
        self.assertEqual(before, self.files())
        self.assertEqual(self.output.exists(), output_existed)

    def resign_reservation(self):
        r = self.permit['reservation']
        r['sha256'] = M.digest({k: v for k, v in r.items() if k != 'sha256'})

    def test_valid_preflight_returns_only_references_and_writes_nothing(self):
        before = self.files()
        result = self.admit()
        self.assertEqual(result, {'authorization_sha256': self.auth_sha, 'attempt_id': 'native-01',
                                  'reservation_sha256': self.permit['reservation']['sha256']})
        self.assertEqual(before, self.files())
        self.assertFalse(self.output.exists())

    def test_consumption_is_one_use_and_does_not_attest_human_presence(self):
        self.admit(consume=True)
        marker = self.path.with_name(self.path.name + '.consumed.json')
        receipt = json.loads(marker.read_text())
        self.assertFalse(receipt['human_presence_attested'])
        self.assertFalse(receipt['device_verification_attested'])
        self.assertEqual(receipt['permit_sha256'], self.expected)
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.output.exists())
        with self.assertRaisesRegex(M.PermitError, 'already_consumed'):
            self.admit(consume=True)
        with self.assertRaisesRegex(M.PermitError, 'already_consumed'):
            self.admit()

    def test_permit_bytes_must_match_trusted_cli_hash(self):
        self.path.write_text(self.path.read_text() + ' ')
        self.assert_rejected_without_write('permit_hash_mismatch')

    def test_unknown_keys_and_duplicate_keys_are_rejected(self):
        self.permit['automatic_topup'] = True
        self.write()
        self.assert_rejected_without_write('permit_schema_fields')
        del self.permit['automatic_topup']
        self.write()
        self.path.write_text(self.path.read_text().replace('"schema_version": 1,', '"schema_version": 1, "schema_version": 1,'))
        self.expected = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assert_rejected_without_write('duplicate_json_key')

    def test_workspace_model_and_wall_duration_are_exactly_bound(self):
        for arguments in ({'output': self.root/'other'}, {'model': 'other-model'}, {'wall_seconds': 301}):
            self.assert_rejected_without_write('mismatch', **arguments)
        self.output.mkdir(parents=True)
        self.assert_rejected_without_write('output_mismatch_or_already_exists')

    def test_api_or_persistent_or_unrelated_tool_scope_is_rejected(self):
        original = copy.deepcopy(self.permit)
        for key, value in [('api_access', True), ('persistent_grant', True),
                           ('host_auth', 'api_key'), ('tools', ['run_current_tests', 'shell'])]:
            self.permit = copy.deepcopy(original)
            self.permit['scope'][key] = value
            self.write()
            self.assert_rejected_without_write('unsupported_permit_scope')

    def test_authorization_bytes_must_match_adjacent_file(self):
        p = self.control / 'authorization.json'
        p.write_text(p.read_text() + '\n')
        self.assert_rejected_without_write('authorization_hash_mismatch')

    def test_structurally_invalid_authorization_cannot_be_resigned_into_grant(self):
        p = self.control / 'authorization.json'
        auth = json.loads(p.read_text())
        auth['limits']['native_attempts'] = 3
        p.write_text(json.dumps(auth))
        self.permit['authorization_sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
        self.permit['reservation']['authorization_sha256'] = self.permit['authorization_sha256']
        self.resign_reservation(); self.write()
        self.assert_rejected_without_write('invalid_batch_authorization')

    def test_reservation_hash_authorization_kind_and_amount_are_checked(self):
        original = copy.deepcopy(self.permit)
        self.permit['reservation']['data']['attempt_id'] = 'changed'
        self.write()
        self.assert_rejected_without_write('invalid_reservation_event')
        for key, value in [('kind', 'method'), ('upper_bound_fen', 100), ('wall_seconds', 601), ('unit_key', 'w-101:A:1')]:
            self.permit = copy.deepcopy(original)
            self.permit['reservation']['data'][key] = value
            self.resign_reservation(); self.write()
            self.assert_rejected_without_write('reservation_outside_native')

    def test_reservation_cannot_claim_different_authorization(self):
        self.permit['reservation']['authorization_sha256'] = 'b' * 64
        self.resign_reservation(); self.write()
        self.assert_rejected_without_write('invalid_reservation_event')

    def test_expiry_future_issue_and_full_duration_are_enforced(self):
        original = copy.deepcopy(self.permit)
        for key, value in [('expires_at_unix_ns', self.now - 1),
                           ('issued_at_unix_ns', self.now + 1000 * 10**9),
                           ('expires_at_unix_ns', self.now + 700 * 10**9),
                           ('expires_at_unix_ns', self.now + 100 * 10**9)]:
            self.permit = copy.deepcopy(original)
            self.permit[key] = value
            self.write()
            self.assert_rejected_without_write('expired_or_duration_not_covered')

    def test_runtime_mutation_is_detected_before_consumption(self):
        (self.root/'scripts/paper1/live_mcp.py').write_text('mutated')
        self.assert_rejected_without_write('runtime_hash_mismatch')

    def test_manifest_requires_every_mandatory_and_present_core_file(self):
        del self.permit['runtime_sha256']['scripts/paper1/native_live.py']
        self.write()
        self.assert_rejected_without_write('runtime_manifest_coverage')
        self.permit['runtime_sha256'] = M.runtime_manifest(self.root)
        self.write()
        (self.root/'packages/memex-core/lib/extra.js').write_text('new package runtime')
        self.assert_rejected_without_write('runtime_manifest_coverage')

    def test_runtime_symlink_is_rejected(self):
        p = self.root/'packages/memex-core/lib/engine.js'
        target = self.base/'outside.js'
        target.write_bytes(p.read_bytes()); p.unlink(); p.symlink_to(target)
        self.assert_rejected_without_write('symlink_forbidden')

    def test_adjacent_authorization_and_permit_symlinks_are_rejected(self):
        p = self.control/'authorization.json'
        target = self.base/'auth-copy.json'; target.write_bytes(p.read_bytes())
        p.unlink(); p.symlink_to(target)
        self.assert_rejected_without_write('symlink_forbidden')
        p.unlink(); p.write_bytes(target.read_bytes())
        permit_copy = self.control/'permit-copy.json'; permit_copy.write_bytes(self.path.read_bytes())
        self.path.unlink(); self.path.symlink_to(permit_copy)
        self.assert_rejected_without_write('absolute_regular_permit_path')

    def test_copying_permit_to_new_location_does_not_reset_consumption(self):
        target = self.control/'copy.json'; target.write_bytes(self.path.read_bytes())
        before = self.files()
        with self.assertRaisesRegex(M.PermitError, 'permit_location_mismatch'):
            M.admit_permit(target, self.expected, output=self.output, model='gpt-5.6-sol',
                           wall_seconds=300, source_root=self.root, consume=True)
        self.assertEqual(before, self.files())

    def test_canonical_ancestor_alias_matches_mac_var_tmp_semantics(self):
        alias = self.base/'ancestor-alias'
        alias.symlink_to(self.base, target_is_directory=True)
        aliased_root = alias/'source'
        result = M.admit_permit(aliased_root/'control/permit.json', self.expected,
                               output=aliased_root/'runs/attempt-01', model='gpt-5.6-sol',
                               wall_seconds=300, source_root=aliased_root)
        self.assertEqual(result['attempt_id'], 'native-01')

    def test_concurrent_consumers_only_one_can_start(self):
        ctx = multiprocessing.get_context('fork'); queue = ctx.Queue()
        children = [ctx.Process(target=consumer, args=(str(self.path), self.expected, str(self.output),
                    'gpt-5.6-sol', str(self.root), queue)) for _ in range(3)]
        for p in children: p.start()
        for p in children:
            p.join(10); self.assertEqual(p.exitcode, 0)
        results = [queue.get(timeout=2) for _ in children]
        self.assertEqual(results.count('consumed'), 1, results)
        self.assertEqual(results.count('permit_already_consumed'), 2, results)

    def test_fsync_failure_leaves_marker_and_cannot_replay(self):
        with patch.object(M.os, 'fsync', side_effect=OSError('fixture fsync failure')):
            with self.assertRaisesRegex(M.PermitError, 'persistence_uncertain'):
                self.admit(consume=True)
        with self.assertRaisesRegex(M.PermitError, 'already_consumed'):
            self.admit(consume=True)

    def test_boolean_counters_and_nonboolean_consume_are_rejected(self):
        self.assert_rejected_without_write('invalid_trusted_controller_arguments', wall_seconds=True)
        before = self.files()
        with self.assertRaisesRegex(M.PermitError, 'invalid_trusted_controller_arguments'):
            self.admit(consume='yes')
        self.assertEqual(before, self.files())


if __name__ == '__main__':
    unittest.main()
