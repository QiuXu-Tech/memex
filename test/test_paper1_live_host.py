import importlib.util
from pathlib import Path
import unittest
import runpy

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('p1_live_proxy', ROOT / 'scripts/paper1/live_mcp.py')
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)
native = runpy.run_path(str(ROOT / 'scripts/paper1/native_live.py'))


class PublicProxyTests(unittest.TestCase):
    def test_controller_operations_are_not_exposed_as_model_tools(self):
        calls = []
        response = proxy.dispatch({'id': 2, 'method': 'tools/call', 'params': {'name': 'install_extraction', 'arguments': {}}}, lambda x: calls.append(x))
        self.assertTrue(response['result']['isError'])
        self.assertEqual(calls, [])

    def test_public_calls_have_a_fixed_controller_operation(self):
        calls = []
        def rpc(value):
            calls.append(value)
            return {'ok': True, 'result': {'scope': 'demo'}}
        response = proxy.dispatch({'id': 3, 'method': 'tools/call', 'params': {'name': 'workspace_inspect', 'arguments': {}}}, rpc)
        self.assertFalse(response['result']['isError'])
        self.assertEqual(calls, [{'op': 'public', 'name': 'workspace_inspect', 'input': {}}])

    def test_unknown_protocol_method_does_not_reach_broker(self):
        calls = []
        response = proxy.dispatch({'id': 4, 'method': 'verify', 'params': {'mode': 'always'}}, lambda x: calls.append(x))
        self.assertEqual(response['error']['code'], -32601)
        self.assertEqual(calls, [])

    def test_initialization_requires_no_broker_or_model_call(self):
        response = proxy.dispatch({'id': 1, 'method': 'initialize', 'params': {}}, lambda _: self.fail('unexpected RPC'))
        self.assertEqual(response['result']['serverInfo']['name'], 'p1-public-workspace')


class NativeIntegrationBoundaryTests(unittest.TestCase):
    def test_earlier_wrong_attempt_is_not_erased_by_later_right_decision(self):
        source = {'source': {'eventId': 'real', 'version': 'current', 'status': 'passed'}}
        decision = {'decision': 'release', 'currentVersion': 'current', 'liveObservationOk': True,
                    'evidenceEventIds': ['real']}
        check = native['decision_check']
        self.assertTrue(check([decision], [source], expected='release', version='current'))
        self.assertFalse(check([{**decision, 'decision': 'hold'}, decision], [source], expected='release', version='current'))

    def test_current_decision_cannot_cite_a_passing_receipt_for_old_bytes(self):
        source = {'source': {'eventId': 'old-pass', 'version': 'old', 'status': 'passed'}}
        decision = {'decision': 'release', 'currentVersion': 'current', 'liveObservationOk': True,
                    'evidenceEventIds': ['old-pass']}
        self.assertFalse(native['decision_check']([decision], [source], expected='release', version='current'))

    def test_requested_model_must_be_explicit_and_offered(self):
        for requested in [None, '', 'invented-model']:
            with self.assertRaises(ValueError):
                native['offered_model']({'models': [{'id': 'offered', 'model': 'offered'}]}, requested)

    def test_expired_wall_deadline_stops_before_a_new_protocol_wait(self):
        host = native['DeadlineHost'].__new__(native['DeadlineHost'])
        host.deadline = -1
        host.timeout = 30
        with self.assertRaisesRegex(TimeoutError, 'wall budget'):
            host.wait(lambda: False)


if __name__ == '__main__':
    unittest.main()
