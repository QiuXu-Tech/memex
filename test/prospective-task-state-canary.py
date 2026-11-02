#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('task_state_canary', ROOT / 'scripts/prospective-task-state-canary-20261102.py')
canary = importlib.util.module_from_spec(spec); spec.loader.exec_module(canary)

class CanaryRegistrationTest(unittest.TestCase):
    def test_four_new_owners_are_registered_before_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            private = pathlib.Path(directory); source = private / 'source'; source.mkdir()
            (private / 'task-state-source').mkdir(); (private / 'task-state-source/manifest.json').write_text('[]\n')
            (private / 'task-state-screen').mkdir(); (private / 'task-state-screen/prior-owners.json').write_text('[]\n')
            (private / 'task-state-triage').mkdir(); (private / 'task-state-triage/registration.json').write_text('{}\n')
            tasks = []
            for i in range(4):
                tid = f'canary-{i}'; issue = source / f'{tid}.issue.json'; archive = source / f'{tid}.tar.gz'
                issue.write_text('{}\n'); archive.write_bytes(b'fixture')
                sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
                tasks.append({'id': tid, 'repo': f'owner{i}/repo', 'discussionSpanDays': 10, 'frozenAcceptance': 'criterion',
                              'issueSha256': sha(issue), 'archiveSha256': sha(archive)})
            (source / 'manifest.json').write_text(json.dumps(tasks) + '\n')
            study = canary.study; study.PRIVATE, study.BASE, study.SOURCE = private, private / 'trial', source
            study.agent.BASE, study.agent.SRC = study.BASE, source
            study.reviewer.BASE, study.reviewer.SRC = study.BASE, source
            study.verify_vm_worker = lambda: None
            canary.freeze(); registration = json.loads((study.BASE / 'registration.json').read_text())
            self.assertEqual(len(registration['tasks']), 4)
            self.assertEqual(registration['aggregateClientListReservationUsd'], 4.0)
            self.assertTrue((study.BASE / 'reviews/plan.json').exists())
            self.assertFalse((study.BASE / 'started-first.json').exists())

if __name__ == '__main__': unittest.main()
