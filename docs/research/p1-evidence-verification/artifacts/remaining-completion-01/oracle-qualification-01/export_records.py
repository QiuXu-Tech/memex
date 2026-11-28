"""Export only this independent qualification directory, with path redaction.

No canonical execution directory, method output, credentials or ledger is read.
Raw private records remain in place. Every published file binds raw and public
SHA-256, and XML is parsed/redacted/reserialized rather than broken by brackets.
"""
from pathlib import Path
import base64
import hashlib
import json
import os
import runpy
import zipfile

ROOT = Path(__file__).resolve().parent


def sha(value):
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def main():
    if (ROOT / 'evidence.zip').exists():
        raise RuntimeError('new_export_archive_required')
    workflow = runpy.run_path(str(ROOT / 'tooling/scripts/paper1/python_workflow.py'))
    first = json.loads((ROOT / 'qualification.json').read_text())
    second = json.loads((ROOT / 'revision-02/qualification.json').read_text())
    audit = json.loads((ROOT / 'posthoc-integrity-audit.json').read_text())
    if audit['status'] != 'passed' or audit['checked_runs'] != 15:
        raise RuntimeError('complete_integrity_audit_required')
    selected = set()
    for name in ('source-preparation.json', 'source-preparation-failure.json', 'execution-plan.json',
                 'qualification.json', 'tooling-manifest.json', 'posthoc-integrity-audit.json'):
        selected.add(ROOT / name)
    for directory in ('source-exports', 'acquisition', 'runtimes', 'tooling'):
        selected.update(p for p in (ROOT / directory).rglob('*') if p.is_file())
    selected.update((ROOT / 'sources').glob('*/fixed-export.json'))
    selected.update((ROOT / 'fallback-environments').glob('*/control.json'))
    for directory in ('probes', 'revision-02/probes'):
        selected.update(p for p in (ROOT / directory).rglob('*') if p.is_file())
    for directory in ('runs', 'revision-02/runs'):
        for p in (ROOT / directory).rglob('*'):
            if p.is_file() and 'workspace' not in p.relative_to(ROOT / directory).parts:
                selected.add(p)
    selected.update(ROOT / name for name in ('revision-02/qualification.json', 'revision-02/revision-plan.json',
        'revision-02/runtime.json', 'revision-02/dependency-snapshot.json'))
    # The exact script/oracle bytes and their copied historical qualification
    # receipts are retained separately from all observed output records.
    for name in ('source_prepare.py', 'source_prepare_v2.py', 'run_qualification.py', 'run_requests_v2.py',
                 'audit_records.py', 'export_records.py', 'test_requests_request_contract_v2.py'):
        selected.add(ROOT / name)
    selected.update((ROOT / 'oracles').glob('*.py'))
    selected.update((ROOT / 'reference-qualification').glob('*.json'))
    selected.add(ROOT / 'revision-02/oracles/w-102.py')
    # Exact path prefixes only. No inferred credential filtering is needed;
    # those values were never read or inherited by any qualification process.
    p1_root = ROOT.parent
    substitutions = {str(ROOT): '<oracle-qualification>', str(p1_root / 'runtime'): '<canonical-runtime>',
        str(p1_root / 'dependencies/python-workflows-20261128-f521f249'): '<pinned-python-dependencies>',
        str(Path.home()): '<device-home>', os.uname().nodename: 'qualification-host',
        '/workspace/scratch/d5292d3ebcac/p1-real-repros': '<original-program-reproduction>'}
    records, files = [], {}
    for p in sorted(selected):
        relative = p.relative_to(ROOT).as_posix()
        if p.is_symlink() or not p.is_file():
            raise RuntimeError('nonregular_export_member')
        raw = p.read_bytes()
        if p.suffix == '.xml':
            published = workflow['redact_xml'](raw, substitutions)
            transformation = 'parse_XML_redact_known_paths_and_reserialize'
        else:
            raw.decode('utf-8')
            published = workflow['redact'](raw, substitutions)
            transformation = 'known_private_paths_and_host_only'
        files[relative] = published
        records.append({'path': relative, 'raw_sha256': sha(raw), 'published_sha256': sha(published),
            'raw_bytes': len(raw), 'published_bytes': len(published), 'verbatim': raw == published,
            'transformation': None if raw == published else transformation})
    result_rows = first['results'] + second['results']
    summary = {'kind': 'reference_oracle_qualification_summary', 'schema_version': 2,
        'status': 'two_partial_behavior_oracles_qualified_on_known_references',
        'flask_original_five_case_oracle': {'base': {'passed': 4, 'failed': 1},
            'official_fixed': {'passed': 5, 'failed': 0}, 'incorrect_behavior': {'passed': 2, 'failed': 3}},
        'requests_original_six_case_draft': {'base': {'passed': 2, 'failed': 4},
            'official_fixed': {'passed': 5, 'failed': 1}, 'incorrect_behavior': {'passed': 3, 'failed': 3},
            'fully_qualified': False, 'unresolved_input': 'reviewer:fixture-password@proxy.example.invalid:3128'},
        'requests_explicit_url_v2_five_case_oracle': {'base': {'passed': 2, 'failed': 3},
            'official_fixed': {'passed': 5, 'failed': 0}, 'incorrect_behavior': {'passed': 2, 'failed': 3}},
        'empty_test_controls': {'observed': 2, 'pytest_exit': 5, 'scored_passes': 0},
        'missing_source_controls': {'observed': 2, 'observer_exit': 78, 'scored_passes': 0},
        'wrong_origin_dependency_controls': {'observed': 2, 'observer_exit': 78,
            'error': 'project_import_outside_current_workspace', 'scored_passes': 0},
        'observer_processes': sum(row['observer_processes'] for row in result_rows),
        'sandbox_probe_processes': first['sandbox_probe_processes'] + second['sandbox_probe_processes'],
        'all_probes_passed': True, 'original_settings_and_dependencies_unchanged': True,
        'captured_input_reconstructions_passed': audit['checked_runs'],
        'input_binding_audit_timing': 'posthoc_for_round_1_and_pre_run_plus_posthoc_for_revision_2',
        'new_native_or_method_outputs_read': False, 'oracle_delivered_to_model': False,
        'source_qualification_not_method_evaluation': True, 'source_qualification_not_task_acceptance': True,
        'human_annotators': 0, 'accepted_research_tasks': 0, 'decision_success': None,
        'native_attempts': 0, 'method_units': 0, 'model_requests': 0, 'provider_requests': 0,
        'canonical_ledger_accessed': False, 'original_draft_failure_retained': True,
        'uncovered_behavior': ['Requests Python 3.8.12 equivalence', 'end-to-end HTTP 407 proxy scenario',
            'ambiguous scheme-less ordinary credentials', 'all P1 evidence-use and decision obligations']}
    # Verify summary counts against the actual revalidated reports, never just
    # trust the handwritten display labels above.
    for task, key, result_group in [('w-101', 'flask_original_five_case_oracle', first['results']),
            ('w-102', 'requests_original_six_case_draft', first['results']),
            ('w-102', 'requests_explicit_url_v2_five_case_oracle', second['results'])]:
        for variant, label in [('base', 'base'), ('fixed', 'official_fixed'), ('incorrect_behavior', 'incorrect_behavior')]:
            row = next(r for r in result_group if r['task_id'] == task and r['variant'] == variant)
            counts = row['summary']['test_counts']
            if summary[key][label] != {k: counts[k] for k in ('passed', 'failed')}:
                raise RuntimeError('summary_counts_do_not_match_observations')
    files['reference-summary.json'] = encoded(summary)
    manifest = {'kind': 'path_redacted_independent_oracle_evidence_export', 'schema_version': 1,
        'files': records, 'published_record_count': len(records),
        'summary_sha256': sha(files['reference-summary.json']),
        'raw_private_records_retained': True, 'new_method_output_included': False,
        'credentials_read': False, 'externally_attested_authenticity_claimed': False,
        'redaction_policy': 'Known home/controller/dependency paths and hostname only; XML values are escaped after replacement.',
        'raw_named_stream_files_in_export_may_be_redacted': True}
    files['export-manifest.json'] = encoded(manifest)
    with zipfile.ZipFile(ROOT / 'evidence.zip', 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, value in sorted(files.items()):
            archive.writestr('evidence/' + name, value)
    raw = (ROOT / 'evidence.zip').read_bytes()
    text = base64.b64encode(raw).decode('ascii')
    (ROOT / 'evidence-transfer.b64').write_text('\n'.join(text[i:i + 100] for i in range(0, len(text), 100)) + '\n')
    print(json.dumps({'status': 'qualification_evidence_exported', 'record_files': len(records),
        'archive_bytes': len(raw), 'archive_sha256': sha(raw), 'base64_lines': (len(text) + 99) // 100}))


if __name__ == '__main__':
    main()
