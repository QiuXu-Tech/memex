#!/usr/bin/env python3
"""Bounded local source/environment qualifications, never agent experiments.

Only --run launches commands. Official patches, labels, complete logs, and raw
dataset rows stay in --private-root. Public receipts contain hashes and counts.
This reproduces selected changed test modules in a local pinned environment;
it does not claim equivalence to the official container or a formal P1 task.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import time
import xml.etree.ElementTree as ET


PREVIOUSLY_QUALIFIED = {'pallets__flask-5014', 'psf__requests-6028'}
DATASET_REVISION = '78f471bf655a3137b2e8a75af1501690ec009ec3'
DATASET_SHA256 = '030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25'
PARSER_SHA256 = 'cd56156414f8327221e525665ace9b184f7d73e83b272d9eb3f545fb17c2d9bc'
CONSTANTS_SHA256 = '8895ab5313d874349c4b07bd223bb9eb00acaee377b432e67cc7ad840341e79b'
MAX_SETUP_SECONDS, MAX_TEST_SECONDS = 360, 180


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':')).encode())


EXECUTED_DRIVER_SHA256 = digest(Path(__file__).read_bytes())


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def safe_paths(paths):
    return all(isinstance(p, str) and p and not PurePosixPath(p).is_absolute()
               and '..' not in PurePosixPath(p).parts and '\\' not in p for p in paths)


def validate_row(candidate, row):
    if canonical_digest(row) != candidate['source_dataset']['canonical_row_sha256']:
        raise ValueError('row_hash_mismatch')
    if (row['instance_id'] != candidate['candidate_id'] or
            row['repo'] != candidate['project_id'] or
            row['base_commit'] != candidate['upstream']['base_commit'] or
            not re.fullmatch('[0-9a-f]{40}', row['base_commit'])):
        raise ValueError('candidate_identity_mismatch')
    if candidate['repository_url'] != 'https://github.com/' + row['repo']:
        raise ValueError('nonofficial_origin')
    for key, list_key in [('patch', 'benchmark_source_patch'),
                          ('test_patch', 'benchmark_test_patch')]:
        if digest(row[key].encode()) != candidate['official_benchmark_labels_evaluator_only'][key + '_sha256']:
            raise ValueError('patch_hash_mismatch')
        paths = re.findall(r'^diff --git a/(\S+) b/(\S+)$', row[key], re.M)
        declared = set(candidate['changed_files'][list_key])
        actual = {p for pair in paths for p in pair}
        if not paths or not safe_paths(actual) or actual != declared:
            raise ValueError('patch_paths_mismatch')


def validate_profile(profile):
    requirements = profile.get('requirements', [])
    if not requirements or any(not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+', r)
                               for r in requirements):
        raise ValueError('all_dependencies_require_exact_pins')
    if profile.get('test_runner') not in {'pytest', 'sympy'}:
        raise ValueError('unsupported_test_runner')
    if any(not re.fullmatch(r'[A-Za-z0-9_.]+', p) for p in profile.get('plugins', [])):
        raise ValueError('invalid_pytest_plugin')


def install_environment():
    keys = ('PATH', 'LANG', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
            'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')
    env = {k: os.environ[k] for k in keys if k in os.environ}
    env.update(PIP_CONFIG_FILE='/dev/null', PYTHONNOUSERSITE='1',
               GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0')
    return env


def remaining_budget(start, limit):
    remaining = limit - (time.monotonic() - start)
    if remaining <= 0:
        raise TimeoutError('setup_budget_exhausted')
    return remaining


def retry_setup_budget(previous, limit):
    if previous.get('attempt_number', 1) != 1:
        raise ValueError('only_one_followup_allowed')
    if previous.get('status') != 'setup_or_acquisition_failure' or previous.get('base_result') is not None:
        raise ValueError('followup_is_setup_only')
    remaining = limit - previous['total_elapsed_seconds']
    if remaining <= 0:
        raise TimeoutError('setup_budget_exhausted')
    return remaining


def run_command(argv, cwd, env, timeout, logs, name):
    started = time.monotonic()
    record = {'phase': name, 'started_at': utcnow(), 'command': list(map(str, argv)),
              'timeout_seconds': timeout, 'environment_keys': sorted(env),
              'timed_out': False, 'returncode': None, 'launch_error': None}
    stdout, stderr = logs / (name + '.stdout.txt'), logs / (name + '.stderr.txt')
    with stdout.open('wb') as out, stderr.open('wb') as err:
        try:
            proc = subprocess.Popen(record['command'], cwd=cwd, env=env, stdout=out,
                                    stderr=err, start_new_session=True)
            try:
                record['returncode'] = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record['timed_out'] = True
                os.killpg(proc.pid, signal.SIGKILL)
                record['returncode'] = proc.wait()
        except OSError as exc:
            record['launch_error'] = type(exc).__name__
    record['elapsed_seconds'] = time.monotonic() - started
    for stream, path in [('stdout', stdout), ('stderr', stderr)]:
        record[stream] = {'private_file': str(path), 'bytes': path.stat().st_size,
                          'sha256': digest(path.read_bytes())}
    write_json(logs / (name + '.command.json'), record)
    return record


def junit_metrics(path):
    if not path.is_file():
        return None
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    cases = list(root.iter('testcase'))
    counts = {'tests': len(cases), 'passed': 0, 'failures': 0, 'errors': 0, 'skipped': 0}
    for case in cases:
        status = next((key for tag, key in [('error', 'errors'), ('failure', 'failures'),
                                           ('skipped', 'skipped')] if case.find(tag) is not None), 'passed')
        counts[status] += 1
    return counts


def initial_receipt(candidate, row):
    return {'schema_version': 1, 'kind': 'source_environment_qualification_only',
            'candidate_id': candidate['candidate_id'], 'project_id': candidate['project_id'],
            'recorded_at': utcnow(), 'formal_task': False, 'model_requests': 0,
            'official_container_used': False, 'docker_equivalence_claimed': False,
            'source_dataset': candidate['source_dataset'], 'upstream': candidate['upstream'],
            'license': candidate.get('license'), 'changed_files': candidate['changed_files'],
            'patch_hashes': {key: digest(row[key].encode()) for key in ['patch', 'test_patch']},
            'raw_patch_or_label_copy_published': False, 'status': 'attempt_started',
            'commands': [], 'base_result': None, 'fixed_result': None,
            'official_label_coverage': None}


def sandbox_command(python, venv, repo, logs, argv, writable_venv=False):
    runtime = python.resolve().parent.parent
    # A synthetic account entry lets historical setup tools resolve ~ without
    # reading a host account database or forwarding HOME / credential paths.
    account = logs / 'sandbox.passwd'
    account.write_text(f'qualification:x:{os.getuid()}:{os.getgid()}:qualification:/tmp:/bin/sh\n')
    cmd = ['bwrap', '--unshare-user', '--unshare-pid', '--unshare-ipc', '--unshare-uts',
           '--die-with-parent', '--ro-bind', '/usr', '/usr', '--ro-bind', '/lib', '/lib',
           '--ro-bind', '/lib64', '/lib64', '--symlink', 'usr/bin', '/bin', '--proc', '/proc',
           '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/etc',
           '--ro-bind', str(account), '/etc/passwd', '--ro-bind', str(runtime), str(runtime),
           '--bind' if writable_venv else '--ro-bind', str(venv), str(venv),
           '--bind', str(repo), str(repo), '--bind', str(logs), str(logs),
           '--chdir', str(repo), '--clearenv']
    variables = {'PATH': str(venv / 'bin') + ':/usr/bin:/bin', 'LANG': 'C.UTF-8',
                 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'MPLBACKEND': 'Agg',
                 'MPLCONFIGDIR': '/tmp/matplotlib', 'PYTHONHASHSEED': '0'}
    for k, v in variables.items():
        cmd.extend(['--setenv', k, v])
    return cmd + ['--'] + list(map(str, argv))


def file_hashes(repo, files):
    return {f: digest((repo / f).read_bytes()) if (repo / f).is_file() else None for f in files}


def load_official_parser(private_root, name):
    """Execute only pinned official parser function/enum AST, not the harness."""
    parser = private_root / 'official-log-parsers-python.py'
    constants = private_root / 'official-harness-constants.py'
    if digest(parser.read_bytes()) != PARSER_SHA256 or digest(constants.read_bytes()) != CONSTANTS_SHA256:
        raise ValueError('official_parser_hash_mismatch')
    from enum import Enum
    namespace = {'re': re, 'Enum': Enum, 'TestSpec': object}
    nodes = [n for n in ast.parse(constants.read_text()).body if isinstance(n, ast.ClassDef)
             and n.name == 'TestStatus']
    nodes.extend(n for n in ast.parse(parser.read_text()).body
                 if isinstance(n, (ast.FunctionDef, ast.Assign)))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(parser), 'exec'), namespace)
    return namespace[name]


def transition_checks(base, fixed, fail_to_pass, pass_to_pass):
    # Native SymPy reports uncaught regression exceptions as ERROR, which is a
    # failing execution. Missing/skipped tests never count as a reproduced bug.
    return {'base_failed_matches_official_f2p': all(base.get(t) in {'FAILED', 'ERROR'} for t in fail_to_pass),
            'all_official_f2p_pass_after_fix': all(fixed.get(t) == 'PASSED' for t in fail_to_pass),
            'all_official_p2p_pass_at_base': all(base.get(t) == 'PASSED' for t in pass_to_pass),
            'all_official_p2p_pass_after_fix': all(fixed.get(t) == 'PASSED' for t in pass_to_pass)}


def label_coverage(private_root, row, logs, base, fixed):
    parser = load_official_parser(private_root, row['log_parser'])
    results = {}
    for phase in ['base', 'fixed']:
        raw = (logs / (phase + '.stdout.txt')).read_text(errors='replace')
        raw += '\n' + (logs / (phase + '.stderr.txt')).read_text(errors='replace')
        results[phase] = parser(raw, None)
    labels = {k: json.loads(row[k]) if isinstance(row[k], str) else row[k]
              for k in ['FAIL_TO_PASS', 'PASS_TO_PASS']}
    f2p, p2p = labels['FAIL_TO_PASS'], labels['PASS_TO_PASS']
    checks = transition_checks(results['base'], results['fixed'], f2p, p2p)
    result = {'official_fail_to_pass_count': len(f2p), 'official_pass_to_pass_count': len(p2p),
              'parser': row['log_parser'], 'parser_sha256': PARSER_SHA256, **checks}
    result['all_expected_transitions_verified'] = bool(f2p) and all(checks.values())
    write_json(logs / 'private-label-comparison.json', {'parsed': results, 'expected': labels, 'checks': checks})
    return result


def qualify(candidate, profile, private_root, output, python, run=False, setup_seconds=360, test_seconds=180,
            retry_setup=False):
    candidate_id = candidate['candidate_id']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-[0-9]+', candidate_id):
        raise ValueError('invalid_candidate_id')
    if candidate_id in PREVIOUSLY_QUALIFIED:
        return {'candidate_id': candidate_id, 'status': 'previous_success_not_repeated'}
    if not run:
        return {'candidate_id': candidate_id, 'status': 'dry_run', 'model_requests': 0}
    private_root, output, python = private_root.resolve(), output.resolve(), python.absolute()
    work = private_root / candidate_id
    if (work / 'attempt.json').exists() and not retry_setup:
        return {'candidate_id': candidate_id, 'status': 'already_attempted'}
    if not 0 < setup_seconds <= MAX_SETUP_SECONDS or not 0 < test_seconds <= MAX_TEST_SECONDS:
        raise ValueError('budget_out_of_bounds')
    validate_profile(profile)
    previous = None
    if retry_setup:
        previous = json.loads((work / 'final-receipt.json').read_text())
        setup_seconds = retry_setup_budget(previous, setup_seconds)
    row = json.loads((private_root / (candidate_id + '.official-row.json')).read_text())
    validate_row(candidate, row)
    if output == private_root or output in private_root.parents or private_root in output.parents:
        raise ValueError('private_and_public_roots_must_be_disjoint')
    work.mkdir(parents=True, exist_ok=True)
    public = output / 'followup-2' / candidate_id if retry_setup else output / candidate_id
    public.mkdir(parents=True, exist_ok=False)
    logs, repo, venv = work / ('logs-followup-2' if retry_setup else 'logs'), work / 'repo', work / 'venv'
    logs.mkdir()
    with (work / ('attempt-followup-2.json' if retry_setup else 'attempt.json')).open('x') as f:
        json.dump({'candidate_id': candidate_id, 'started_at': utcnow(),
                   'profile_sha256': canonical_digest(profile)}, f)
    report = initial_receipt(candidate, row)
    report['attempt_number'] = 2 if retry_setup else 1
    report['executed_driver_sha256'] = EXECUTED_DRIVER_SHA256
    report['previous_attempt_receipt_sha256'] = canonical_digest(previous) if previous else None
    report['profile_sha256'] = canonical_digest(profile)
    report['python_executable_sha256'] = digest(python.resolve().read_bytes())
    report['bounds'] = {'setup_seconds': setup_seconds, 'test_seconds_per_phase': test_seconds}
    report['isolation'] = {'tool': 'bwrap', 'namespaces': ['user', 'pid', 'ipc', 'uts'],
                           'network_namespace': 'shared (existing network controls unchanged)',
                           'credentials_or_proxy_config_forwarded_to_tests': False,
                           'host_resolver_config_mounted': False,
                           'account_database': 'generated single sandbox account; host account database not mounted',
                           'other_project_mounts': [],
                           'scope': 'project installation and test commands; dependency download uses minimal transport environment'}
    (public / 'requirements-pinned.txt').write_text('\n'.join(profile['requirements']) + '\n')
    write_json(public / 'profile.json', profile)
    env = install_environment()
    start = time.monotonic()
    git = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'credential.helper=']

    def command(name, argv, *, timeout=None, cwd=work, check=True, isolated=False):
        limit = timeout if timeout is not None else remaining_budget(start, setup_seconds)
        record = run_command(argv, cwd, {} if isolated else env, limit, logs, name)
        report['commands'].append(record)
        write_json(public / 'reproduction.json', report)
        if check and (record['returncode'] != 0 or record['timed_out']):
            raise RuntimeError(name + '_failed')
        return record

    try:
        if not retry_setup or not (repo / '.git').is_dir():
            command('git-init', git + ['init', str(repo)])
            command('git-origin', git + ['-C', str(repo), 'remote', 'add', 'origin', candidate['repository_url'] + '.git'])
            command('git-fetch', git + ['-C', str(repo), 'fetch', '--depth=1', 'origin', row['base_commit']])
            command('git-checkout', git + ['-C', str(repo), 'checkout', '--detach', 'FETCH_HEAD'])
        else:
            command('git-source-clean', git + ['-C', str(repo), 'diff', '--exit-code'])
        command('git-head', git + ['-C', str(repo), 'rev-parse', 'HEAD'])
        if (logs / 'git-head.stdout.txt').read_text().strip() != row['base_commit']:
            raise RuntimeError('base_commit_mismatch')
        report['base_commit_verified'] = True
        if profile.get('requires_scm_history'):
            command('git-shallow', git + ['-C', repo, 'rev-parse', '--is-shallow-repository'])
            fetch = ['fetch', '--tags', 'origin', row['base_commit']]
            if (logs / 'git-shallow.stdout.txt').read_text().strip() == 'true':
                fetch.insert(1, '--unshallow')
            command('git-version-history', git + ['-C', repo, *fetch])
            command('git-describe', git + ['-C', repo, 'describe', '--tags', '--long'])
            command('git-tag-objects', git + ['-C', repo, 'show-ref', '--tags'])
            report['scm_version_description'] = (logs / 'git-describe.stdout.txt').read_text().strip()
            report['scm_tag_objects_sha256'] = digest((logs / 'git-tag-objects.stdout.txt').read_bytes())
        (work / 'patch.diff').write_text(row['patch'])
        (work / 'test_patch.diff').write_text(row['test_patch'])
        if not (venv / 'bin/python').exists():
            command('create-venv', [python, '-m', 'venv', venv])
        interpreter = venv / 'bin/python'
        command('install-dependencies', [interpreter, '-m', 'pip', '--isolated', 'install',
                 '--disable-pip-version-check', '--no-cache-dir', '--only-binary=:all:',
                 '--cert', '/etc/ssl/certs/ca-certificates.crt',
                 '--report', logs / 'dependency-install-report.json', *profile['requirements']])
        dependency_report = json.loads((logs / 'dependency-install-report.json').read_text())
        report['downloaded_dependency_archives'] = [
            {'name': x['metadata']['name'], 'version': x['metadata']['version'],
             'archive_sha256': x.get('download_info', {}).get('archive_info', {}).get('hashes', {}).get('sha256'),
             'url': x.get('download_info', {}).get('url')}
            for x in dependency_report.get('install', [])]
        install_argv = [interpreter, '-m', 'pip', '--isolated', 'install', '--disable-pip-version-check',
                        '--no-deps', '--no-build-isolation', '-e', repo]
        command('install-project', sandbox_command(python, venv, repo, logs, install_argv, True), isolated=True)
        command('dependencies-freeze', [interpreter, '-m', 'pip', '--isolated', 'freeze', '--all'])
        freeze = (logs / 'dependencies-freeze.stdout.txt').read_bytes()
        (public / 'dependencies-freeze.txt').write_bytes(freeze)
        report['dependency_freeze_sha256'] = digest(freeze)
        command('python-version', [interpreter, '-c', 'import sys,platform,json;print(json.dumps({"version":sys.version,"executable":sys.executable,"platform":platform.platform()}))'])
        report['python_environment'] = json.loads((logs / 'python-version.stdout.txt').read_text())
        for key in ['test_patch']:
            command(key + '-check', git + ['-C', repo, 'apply', '--check', work / (key + '.diff')])
            command(key + '-apply', git + ['-C', repo, 'apply', work / (key + '.diff')])
        test_files = candidate['changed_files']['benchmark_test_patch']
        before_test = file_hashes(repo, test_files)
        report['base_source_hashes'] = file_hashes(repo, candidate['changed_files']['benchmark_source_patch'])
        report['test_file_hashes'] = before_test
        for phase in ['base', 'fixed']:
            if phase == 'fixed':
                command('patch-check', git + ['-C', repo, 'apply', '--check', work / 'patch.diff'], timeout=20)
                command('patch-apply', git + ['-C', repo, 'apply', work / 'patch.diff'], timeout=20)
                report['fixed_source_hashes'] = file_hashes(repo, candidate['changed_files']['benchmark_source_patch'])
                if file_hashes(repo, test_files) != before_test:
                    raise RuntimeError('test_file_changed_between_phases')
            if profile['test_runner'] == 'sympy':
                argv = [interpreter, 'bin/test', '-C', '--verbose', *test_files]
            else:
                argv = [interpreter, '-m', 'pytest', '-rA']
                for plugin in profile.get('plugins', []):
                    argv.extend(['-p', plugin])
                argv.extend(test_files)
                argv.append('--junitxml=' + str(logs / (phase + '.junit.xml')))
            result = command(phase, sandbox_command(python, venv, repo, logs, argv),
                             timeout=test_seconds, isolated=True, check=False)
            report[phase + '_result'] = {k: result[k] for k in ['returncode', 'timed_out', 'elapsed_seconds']}
            report[phase + '_result']['actual_test_counts'] = junit_metrics(logs / (phase + '.junit.xml'))
            if (logs / (phase + '.junit.xml')).is_file():
                report[phase + '_result']['junit_sha256'] = digest((logs / (phase + '.junit.xml')).read_bytes())
        report['test_file_unchanged_between_phases'] = file_hashes(repo, test_files) == before_test
        try:
            report['official_label_coverage'] = label_coverage(private_root, row, logs,
                                                               report['base_result'], report['fixed_result'])
        except (KeyError, ValueError, OSError, TypeError) as exc:
            report['label_parser_error'] = type(exc).__name__
        coverage = report['official_label_coverage'] or {}
        timed_out = report['base_result']['timed_out'] or report['fixed_result']['timed_out']
        if report.get('test_file_unchanged_between_phases') is not True:
            report['status'] = 'evidence_integrity_failure'
        elif timed_out:
            report['status'] = 'test_timeout'
        elif (coverage.get('all_expected_transitions_verified') and report['fixed_result']['returncode'] == 0
              and report['base_result']['returncode'] == 1):
            report['status'] = 'qualified_expected_transitions'
        elif coverage.get('all_expected_transitions_verified'):
            report['status'] = 'expected_transitions_with_other_failures'
        else:
            report['status'] = 'test_or_environment_failure'
    except (RuntimeError, ValueError, TimeoutError, OSError) as exc:
        report['status'] = 'setup_or_acquisition_failure'
        report['failure'] = str(exc) if isinstance(exc, (RuntimeError, TimeoutError)) else type(exc).__name__
    report['finished_at'] = utcnow()
    report['total_elapsed_seconds'] = time.monotonic() - start
    write_json(public / 'reproduction.json', report)
    write_json(work / ('final-receipt-followup-2.json' if retry_setup else 'final-receipt.json'), report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--profiles', type=Path, required=True)
    parser.add_argument('--private-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--candidate', action='append')
    parser.add_argument('--setup-seconds', type=float, default=360)
    parser.add_argument('--test-seconds', type=float, default=180)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--retry-setup', action='store_true',
                        help='one explicit setup-only followup; first receipt remains untouched and total setup budget is shared')
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    profiles = json.loads(args.profiles.read_text())
    available = {c['candidate_id']: c for c in manifest['candidates']}
    selected = args.candidate or list(available)
    if len(set(selected)) != len(selected) or set(selected) - available.keys():
        parser.error('unknown or duplicate candidate')
    for candidate_id in selected:
        candidate = available[candidate_id]
        result = qualify(candidate, profiles.get(candidate_id, {}), args.private_root, args.output,
                         args.python, run=args.run, setup_seconds=args.setup_seconds, test_seconds=args.test_seconds,
                         retry_setup=args.retry_setup)
        print(json.dumps({k: result.get(k) for k in ['candidate_id', 'status', 'failure']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
