"""Recheck the exported records without executing target projects or pytest."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import runpy
import stat
import tempfile
import zipfile


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.archive.read_bytes()
    if args.output.exists():
        raise ValueError('new_verification_output_required')
    with tempfile.TemporaryDirectory(prefix='p1-oracle-export-check-') as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(args.archive) as archive:
            members = archive.infolist()
            if len(members) > 1000 or sum(p.file_size for p in members) > 32 * 1024 * 1024:
                raise ValueError('archive_size_limit')
            for member in members:
                name = PurePosixPath(member.filename)
                if (name.is_absolute() or '..' in name.parts or not name.parts or name.parts[0] != 'evidence'
                        or stat.S_ISLNK(member.external_attr >> 16)):
                    raise ValueError('unsafe_archive_member')
                destination = root / member.filename
                if destination.exists():
                    raise ValueError('duplicate_archive_member')
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(member))
        root /= 'evidence'
        manifest = read(root / 'export-manifest.json')
        entries = {}
        for row in manifest['files']:
            value = (root / row['path']).read_bytes()
            assert sha(value) == row['published_sha256'] and len(value) == row['published_bytes'], row['path']
            assert row['path'] not in entries
            entries[row['path']] = row
        assert sha((root / 'reference-summary.json').read_bytes()) == manifest['summary_sha256']
        helpers = read(root / 'tooling-manifest.json')['files']
        for name, expected in helpers.items():
            assert sha((root / 'tooling' / name).read_bytes()) == expected
        workflow = runpy.run_path(str(root / 'tooling/scripts/paper1/python_workflow.py'))
        results = []
        for prefix in ('', 'revision-02/'):
            qualification = read(root / prefix / 'qualification.json')
            for row in qualification['results']:
                run_name = prefix + row['run']
                run = root / run_name
                config = read(run / 'child-config.json')
                process = read(run / 'execution/process.json')
                observation = read(run / 'execution/sandbox-output/pytest-observation.json')
                before, after = read(run / 'workspace-before.json'), read(run / 'workspace-after.json')
                assert before['version'] == workflow['digest'](before['files'])
                assert before == after
                dependencies = read(root / 'runtimes' / (row['task_id'] + '-dependency-snapshot.json'))
                evaluation = workflow['summarize'](process, observation, before, after,
                    nonce=config['nonce'], tests=config['tests'], module=config['module'], dependencies=dependencies['files'])
                assert evaluation == row['summary'], run_name
                for stream, source in process['streams'].items():
                    entry = entries[run_name + '/execution/capture/' + stream + '.raw']
                    assert source['sha256'] == entry['raw_sha256'] and source['bytes'] == entry['raw_bytes']
                if evaluation['status'] in ('tests_passed', 'tests_failed'):
                    origin = observation['project_origins_after'][config['module']]
                    assert origin['scope'] == 'workspace'
                    assert evaluation['test_counts']['collected'] > 0
                assert row['decision_success'] is None and row['human_annotators'] == 0
                results.append({'run': run_name, 'summary': evaluation})
        probes = []
        for parent in (root / 'probes', root / 'revision-02/probes'):
            for path in sorted(parent.glob('*/probe-receipt.json')):
                receipt = read(path)
                assert receipt['status'] == 'passed' and receipt['private_sentinel_unchanged'] is True
                assert len(receipt['checks']) == 5 and all(v is True for v in receipt['checks'].values())
                process = receipt['process']
                assert process['spawned'] is True and process['returncode'] == 0 and not process['timed_out'] and not process['error']
                observed = read(path.parent / 'execution/capture/stdout.raw')
                assert observed['checks'] == receipt['checks']
                assert observed['nonce'] == read(path.parent / 'probe-config.json')['nonce']
                probes.append(str(path.relative_to(root)))
        summary = read(root / 'reference-summary.json')
        assert len(results) == summary['observer_processes'] == 15
        assert len(probes) == summary['sandbox_probe_processes'] == 5
        assert summary['requests_original_six_case_draft']['official_fixed']['failed'] == 1
        assert summary['decision_success'] is None and summary['accepted_research_tasks'] == 0
        output = {'kind': 'independent_oracle_export_verification', 'status': 'passed',
            'archive_sha256': sha(raw), 'archive_bytes': len(raw), 'published_record_hashes_rechecked': len(entries),
            'observer_summaries_recomputed': len(results), 'actual_probe_receipts_rechecked': len(probes),
            'original_unexpected_reference_failure_retained': True, 'results': results,
            'source_executions_in_this_verification': 0, 'model_requests': 0, 'native_attempts': 0,
            'canonical_ledger_accessed': False,
            'scope_note': 'Record integrity and deterministic summary recheck; no new source run or external attestation of provenance.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(output, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({key: value for key, value in output.items() if key != 'results'}))


if __name__ == '__main__':
    main()
