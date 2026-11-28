#!/usr/bin/env python3
"""Capture fixed tests on the two clean public Python source seeds.

prepare/inspect are zero-execution operations. execute --run records one real
controller-only development execution, not one of the 16 paired method units.
No official patch, evaluator repository, model, provider or installer is used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import runpy
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPERIMENT = runpy.run_path(str(HERE / 'experiment.py'))
SCHEMA = 'p1-python-workflow-capture-1'
RECIPES = {
    'w-101': {'module': 'flask', 'import_root': 'src', 'tests': ['tests/test_blueprints.py'],
              'plugins': [], 'python_version': [3, 10, 16],
              'public_sha256': '5d6c40acd8895373970af9a306fa88bb1c234603b6923d97d4732cda6dce7313',
              'requirements_file': 'docs/research/p1-evidence-verification/tasks/reproduction/pallets__flask-5014/requirements-pinned.txt',
              'requirements_sha256': '5817943cece5ddfb25e91eb00ca3c608502f9c029b970fd570a92b7aef96801a'},
    'w-102': {'module': 'requests', 'import_root': '.', 'tests': ['tests/test_utils.py'],
              'plugins': ['pytest_mock'], 'python_version': [3, 10, 16],
              'public_sha256': '3ad1f3e28265f6da8b060d087db8ea0b8a0a11b4c44534f1ffc3f601c2403adb',
              'requirements_file': 'docs/research/p1-evidence-verification/tasks/reproduction/psf__requests-6028/requirements-pinned.txt',
              'requirements_sha256': '652d5312533e0ef8ab830f85811c20391d520b55624ae516de28d325d4578313'},
}


class CaptureError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return sha(canonical(value).encode())


def now():
    return datetime.now(timezone.utc).isoformat()


def path(value, *, exists=True):
    result = Path(value).absolute()
    if any(p.is_symlink() for p in (result, *result.parents)):
        raise CaptureError('symlink_path_component')
    if exists and not result.exists():
        raise CaptureError('path_missing')
    return result


def read_json(value):
    return EXPERIMENT['read_json'](path(value))


def write_json(destination, value):
    with Path(destination).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def snapshot(root, *, max_bytes=64 * 1024 * 1024, max_files=4096):
    """Hash current regular-file bytes and modes, with no ignored source files."""
    root = path(root)
    if not root.is_dir():
        raise CaptureError('snapshot_root_not_directory')
    entries, total = [], 0
    for member in [root, *sorted(root.rglob('*'))]:
        info = member.lstat()
        relative = '.' if member == root else member.relative_to(root).as_posix()
        row = {'path': relative, 'mode': stat.S_IMODE(info.st_mode)}
        if stat.S_ISDIR(info.st_mode):
            row['kind'] = 'directory'
        elif stat.S_ISREG(info.st_mode):
            if info.st_size > max_bytes or total + info.st_size > max_bytes:
                raise CaptureError('snapshot_byte_limit')
            fd = os.open(member, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
            with os.fdopen(fd, 'rb') as source:
                before = os.fstat(source.fileno())
                content = source.read(max_bytes - total + 1)
                after = os.fstat(source.fileno())
            current = member.lstat()
            identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if (len(content) != info.st_size or identity(info) != identity(before)
                    or identity(before) != identity(after) or identity(after) != identity(current)):
                raise CaptureError('file_changed_during_snapshot')
            row.update(kind='file', bytes=len(content), sha256=sha(content))
            total += len(content)
        else:
            raise CaptureError('nonregular_or_symlink_snapshot_member')
        entries.append(row)
        if len(entries) > max_files:
            raise CaptureError('snapshot_file_limit')
    return {'version': digest(entries), 'files': entries, 'total_bytes': total}


def profile(public):
    public = path(public)
    descriptor = read_json(public / 'task.json')
    task = descriptor.get('task_handle')
    if task not in RECIPES or descriptor.get('material_kind') != 'real_source_seed':
        raise CaptureError('unsupported_source_seed')
    recipe = dict(RECIPES[task])
    if EXPERIMENT['public_digest'](public) != recipe['public_sha256']:
        raise CaptureError('clean_public_seed_hash_mismatch')
    requirements = (ROOT / recipe['requirements_file']).read_bytes()
    if sha(requirements) != recipe['requirements_sha256']:
        raise CaptureError('pinned_requirements_hash_mismatch')
    pins = {}
    for line in requirements.decode('ascii').splitlines():
        if not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+', line):
            raise CaptureError('invalid_exact_requirement')
        name, version = line.split('==')
        key = name.lower().replace('_', '-').replace('.', '-')
        if key in pins:
            raise CaptureError('duplicate_requirement')
        pins[key] = version
    recipe.update(task_id=task, requirements=pins)
    return recipe


def runtime(python, recipe):
    """Read-only pin and interpreter-file checks, without invoking Python/site."""
    executable = Path(python).absolute()
    # A normal venv/bin/python is a symlink to the pinned base interpreter.
    if executable.name not in ('python', 'python3', 'python3.10'):
        raise CaptureError('explicit_venv_python_required')
    venv = path(executable.parent.parent)
    if executable.parent.name != 'bin' or not (venv / 'pyvenv.cfg').is_file():
        raise CaptureError('explicit_venv_python_required')
    target = executable.resolve(strict=True)
    if not target.is_file() or not os.access(target, os.X_OK):
        raise CaptureError('interpreter_unavailable')
    site = path(venv / 'lib/python3.10/site-packages')
    versions = {}
    for dist in importlib.metadata.distributions(path=[str(site)]):
        name = dist.metadata['Name']
        if name:
            key = name.lower().replace('_', '-').replace('.', '-')
            if key in versions:
                raise CaptureError('ambiguous_dependency_metadata')
            versions[key] = dist.version
    mismatch = [name for name, value in recipe['requirements'].items() if versions.get(name) != value]
    dependencies = snapshot(site, max_bytes=256 * 1024 * 1024, max_files=40000)
    report = {'interpreter_sha256': sha(target.read_bytes()),
              'dependency_tree_sha256': dependencies['version'],
              'required_versions': recipe['requirements'],
              'observed_versions': {name: versions.get(name) for name in recipe['requirements']},
              'mismatched_dependencies': mismatch, 'requirements_match': not mismatch,
              'python_version_not_yet_executed': True,
              'pth_processing': 'disabled_by_python_-I_-S',
              'os_isolation': False, 'runtime_ready_for_formal_method': False}
    return {'python': executable, 'target': target, 'venv': venv, 'site': site,
            'report': report, 'dependency_snapshot': dependencies}


def inspect(public, python=None):
    recipe = profile(public)
    result = {'schema_version': SCHEMA, 'kind': 'zero_execution_python_capture_preflight',
              'task_id': recipe['task_id'], 'public_sha256': recipe['public_sha256'],
              'fixed_tests': recipe['tests'], 'explicit_plugins': recipe['plugins'],
              'required_python_version': recipe['python_version'],
              'required_dependencies': recipe['requirements'],
              'observer_implemented': True, 'source_executions': 0,
              'model_requests': 0, 'provider_requests': 0, 'method_attempts_reserved': 0,
              'scientific_ready': False, 'method_runtime_ready': False,
              'source_tests_do_not_establish_requested_behavior': True}
    if python:
        result['environment'] = runtime(python, recipe)['report']
    return result


def prepare(public, session):
    recipe = profile(public)
    public, session = path(public), path(session, exists=False)
    if session.exists():
        raise CaptureError('session_already_exists')
    if session.is_relative_to(public) or public.is_relative_to(session):
        raise CaptureError('source_session_overlap')
    session.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.p1-python-', dir=session.parent))
    try:
        shutil.copytree(public, temporary / 'public', copy_function=shutil.copy2)
        if EXPERIMENT['public_digest'](temporary / 'public') != recipe['public_sha256']:
            raise CaptureError('detached_public_hash_mismatch')
        (temporary / 'controller').mkdir(mode=0o700)
        (temporary / 'controller/attempts').mkdir(mode=0o700)
        value = {'schema_version': SCHEMA, 'kind': 'controller_source_session', 'recipe': recipe,
                 'initial_workspace': snapshot(temporary / 'public/workspace'),
                 'session_id': 'python-' + uuid.uuid4().hex, 'created_at': now(),
                 'model_requests': 0, 'scientific_ready': False}
        value['sha256'] = digest(value)
        write_json(temporary / 'controller/session.json', value)
        # Confirm source identity again after copying, before publishing session.
        profile(public)
        temporary.rename(session)
        return {'task_id': recipe['task_id'], 'session_id': value['session_id'],
                'public_sha256': recipe['public_sha256'],
                'workspace_sha256': value['initial_workspace']['version'],
                'source_executions': 0, 'method_runtime_ready': False}
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def run_process(argv, *, cwd, env, timeout, directory, output_limit=2 * 1024 * 1024):
    """Capture bounded original bytes and a real process-group outcome."""
    if (type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300
            or type(output_limit) is not int or not 1 <= output_limit <= 16 * 1024 * 1024):
        raise CaptureError('invalid_process_limits')
    directory = Path(directory)
    result = {'started_at': now(), 'spawned': False, 'returncode': None, 'signal': None,
              'timed_out': False, 'output_limit_exceeded': False, 'error': None,
              'stdout': 'stdout.raw', 'stderr': 'stderr.raw'}
    started = time.monotonic()
    streams = {name: (directory / (name + '.raw')).open('xb') for name in ('stdout', 'stderr')}
    process = None
    poller = selectors.DefaultSelector()
    sizes = {name: 0 for name in streams}
    termination_at = None
    try:
        process = subprocess.Popen(list(map(str, argv)), cwd=cwd, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True)
        result['spawned'] = True
        for name in streams:
            pipe = getattr(process, name)
            os.set_blocking(pipe.fileno(), False)
            poller.register(pipe, selectors.EVENT_READ, name)
        while poller.get_map() or process.poll() is None:
            elapsed = time.monotonic() - started
            if elapsed >= timeout and not result['timed_out']:
                result['timed_out'] = True
            if (result['timed_out'] or result['output_limit_exceeded']) and termination_at is None:
                termination_at = time.monotonic()
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if termination_at is not None and time.monotonic() - termination_at >= 0.25:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                # Do not wait indefinitely on a pipe inherited by escaped code.
                if time.monotonic() - termination_at >= 1.0:
                    for key in list(poller.get_map().values()):
                        poller.unregister(key.fileobj)
                        key.fileobj.close()
            for key, _ in poller.select(0.03):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    poller.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                name = key.data
                room = max(0, output_limit - sizes[name])
                streams[name].write(data[:room])
                sizes[name] += len(data[:room])
                if len(data) > room:
                    result['output_limit_exceeded'] = True
        result['returncode'] = process.wait(timeout=1)
        if process.returncode < 0:
            result['signal'] = -process.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        result['error'] = {'type': type(exc).__name__, 'errno': getattr(exc, 'errno', None)}
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
        for key in list(poller.get_map().values()):
            key.fileobj.close()
        poller.close()
        if process is not None:
            result['returncode'] = process.returncode
            if process.returncode is not None and process.returncode < 0:
                result['signal'] = -process.returncode
        for stream in streams.values():
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
        result.update(finished_at=now(), elapsed_seconds=time.monotonic() - started,
                      output_complete=not result['output_limit_exceeded'])
        result['streams'] = {name: {'bytes': sizes[name], 'sha256': sha((directory / (name + '.raw')).read_bytes())}
                             for name in streams}
    return result


def summarize(process, observation, before, after, *, nonce, tests, module, dependencies=()):
    """No stdout keyword matching and no exit-zero-only success inference."""
    result = {'status': 'capture_incomplete', 'test_counts': None, 'reason': None,
              'current_workspace_bound': before['version'] == after['version']}
    if process.get('error') or not process.get('spawned'):
        result['reason'] = 'process_start_or_capture_error'; return result
    if process.get('timed_out'):
        result.update(status='timeout', reason='process_timeout'); return result
    if process.get('output_limit_exceeded'):
        result['reason'] = 'output_capture_limit'; return result
    if not isinstance(observation, dict) or observation.get('schema_version') != 'p1-python-child-1' or observation.get('nonce') != nonce:
        result['reason'] = 'missing_or_unbound_pytest_observation'; return result
    if (observation.get('error') or observation.get('pytest_started') is not True
            or observation.get('pytest_finished') is not True
            or observation.get('pth_processing_disabled') is not True
            or observation.get('isolated_python_mode') is not True):
        result['reason'] = 'python_environment_import_or_observer_error'; return result
    if observation.get('network_attempts_blocked') != 0:
        result['reason'] = 'network_operation_blocked'; return result
    if observation.get('pytest_exit_code') != process['returncode'] or observation.get('process_exit_requested') != process['returncode']:
        result['reason'] = 'process_pytest_exit_mismatch'; return result
    if observation.get('collection_errors') or process['returncode'] not in (0, 1):
        result['reason'] = 'pytest_collection_usage_or_internal_error'; return result
    nodes = observation.get('collected')
    if (not isinstance(nodes, list) or not nodes
            or any(not isinstance(n, str) or n.split('::')[0] not in tests for n in nodes)
            or len(nodes) != len(set(nodes))):
        result['reason'] = 'empty_duplicate_or_unexpected_collection'; return result
    reports = observation.get('reports')
    if not isinstance(reports, list):
        result['reason'] = 'missing_test_reports'; return result
    phases = {n: {} for n in nodes}
    for report in reports:
        if (not isinstance(report, dict) or report.get('nodeid') not in phases
                or report.get('when') not in ('setup', 'call', 'teardown')
                or report.get('outcome') not in ('passed', 'failed', 'skipped')
                or report['when'] in phases[report['nodeid']]):
            result['reason'] = 'invalid_or_duplicate_test_phase'; return result
        phases[report['nodeid']][report['when']] = report['outcome']
    counts = {'collected': len(nodes), 'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 0}
    for phase in phases.values():
        if 'setup' not in phase or 'teardown' not in phase:
            result['reason'] = 'incomplete_test_phases'; return result
        if phase['setup'] == 'passed' and 'call' not in phase:
            result['reason'] = 'missing_test_call'; return result
        if phase['setup'] != 'passed' and 'call' in phase:
            result['reason'] = 'unexpected_test_call'; return result
        if phase['setup'] == 'failed' or phase['teardown'] == 'failed':
            counts['errors'] += 1
        elif phase.get('call') == 'failed':
            counts['failed'] += 1
        elif phase['setup'] == 'skipped' or phase.get('call') == 'skipped':
            counts['skipped'] += 1
        elif phase.get('call') == 'passed' and phase['teardown'] == 'passed':
            counts['passed'] += 1
        else:
            result['reason'] = 'inconsistent_test_outcome'; return result
    result['test_counts'] = counts
    failures = counts['failed'] + counts['errors']
    if (process['returncode'] == 0 and failures) or (process['returncode'] == 1 and not failures):
        result['reason'] = 'exit_test_outcome_disagreement'; return result
    files = {r['path']: r for r in before['files'] if r['kind'] == 'file'}
    dependency_files = {r['path']: r for r in dependencies if r['kind'] == 'file'}
    for stage in ('project_origins_before', 'project_origins_after'):
        origins = observation.get(stage)
        if (not isinstance(origins, dict) or module not in origins
                or origins[module].get('scope') != 'workspace'):
            result['reason'] = 'missing_project_import_binding'; return result
        for name, origin in origins.items():
            if not isinstance(origin, dict):
                result['reason'] = 'invalid_project_import_binding'; return result
            bound_files = files
            if origin.get('scope') == 'bound_dependency_runtime_alias':
                prefix = 'requests.packages.urllib3.packages.six.moves'
                owner = origin.get('bound_owner_path')
                if (module != 'requests' or not (name == prefix or name.startswith(prefix + '.'))
                        or origin.get('bound_owner_module') != 'urllib3.packages.six'
                        or owner not in dependency_files
                        or origin.get('bound_owner_sha256') != dependency_files[owner]['sha256']):
                    result['reason'] = 'invalid_dependency_runtime_alias'; return result
                continue
            if origin.get('scope') == 'pinned_dependency_alias':
                if module != 'requests' or not name.startswith('requests.packages.'):
                    result['reason'] = 'unexpected_dependency_alias'; return result
                bound_files = dependency_files
            elif origin.get('scope') != 'workspace':
                result['reason'] = 'unknown_import_scope'; return result
            if (origin.get('path') not in bound_files
                    or origin.get('sha256') != bound_files[origin['path']]['sha256']):
                result['reason'] = 'project_import_bytes_mismatch'; return result
    if not result['current_workspace_bound']:
        result['reason'] = 'workspace_changed_during_execution'; return result
    if failures:
        result.update(status='tests_failed', reason='observed_test_failure')
    elif not counts['passed']:
        result['reason'] = 'no_non_skipped_passing_tests'
    else:
        result.update(status='tests_passed', reason=None)
    return result


def redact(data, substitutions):
    published = data
    for original, alias in sorted(substitutions.items(), key=lambda x: len(x[0]), reverse=True):
        published = published.replace(original.encode(), alias.encode())
    return published


def _execute(session, python, output, *, timeout=300, mode='controller-only', run=False, state):
    """One explicitly requested development capture; no method quota is consumed."""
    if mode != 'controller-only':
        raise CaptureError('unsupported_execution_mode')
    if type(timeout) is not int or not 1 <= timeout <= 300:
        raise CaptureError('capture_wall_limit_must_be_1_to_300')
    session, output = path(session), path(output, exists=False)
    if output.exists() or output.is_relative_to(session) or session.is_relative_to(output):
        raise CaptureError('new_nonoverlapping_export_required')
    stored = read_json(session / 'controller/session.json')
    if stored['sha256'] != digest({k: v for k, v in stored.items() if k != 'sha256'}):
        raise CaptureError('session_receipt_hash_mismatch')
    # This less-restrictive mode admits only the exact reviewed clean public
    # seeds. Future model-edited workspaces need separately designed isolation.
    recipe = profile(session / 'public')
    if stored['recipe'] != recipe:
        raise CaptureError('session_recipe_drift')
    env_runtime = runtime(python, recipe)
    if not env_runtime['report']['requirements_match']:
        raise CaptureError('pinned_dependency_mismatch')
    if not run:
        return {'kind': 'zero_execution_capture_preflight', 'environment': env_runtime['report'],
                'source_executions': 0, 'method_attempts_reserved': 0,
                'model_requests': 0, 'provider_requests': 0, 'os_isolation': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    state.update(output=output, task_id=recipe['task_id'], public_sha256=recipe['public_sha256'])
    with (session / 'controller/attempt.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        attempts = session / 'controller/attempts'
        index = len(list(attempts.iterdir())) + 1
        attempt_id = f'{recipe["task_id"]}-capture-{index:03d}'
        attempt = attempts / f'{index:03d}'
        attempt.mkdir()
        state.update(attempt=attempt, attempt_id=attempt_id, dispatch_started=False)
        write_json(attempt / 'preparing.json', {'attempt_id': attempt_id, 'started_at': now()})
        nonce = uuid.uuid4().hex
        started = time.monotonic()
        workspace = session / 'public/workspace'
        before = snapshot(workspace)
        write_json(attempt / 'before.json', before)
        # A fresh detached snapshot is the actual import/test target. This
        # avoids accidentally importing the old editable evaluator checkout.
        copied = attempt / 'workspace'
        shutil.copytree(workspace, copied, copy_function=shutil.copy2)
        if snapshot(copied) != before:
            raise CaptureError('execution_snapshot_copy_mismatch')
        bootstrap = attempt / 'observer.py'
        bootstrap.write_bytes((HERE / 'python_workflow_child.py').read_bytes())
        config = {'nonce': nonce, 'workspace': str(copied), 'dependencies': str(env_runtime['site']),
                  'module': recipe['module'], 'import_root': recipe['import_root'],
                  'tests': recipe['tests'], 'plugins': recipe['plugins'],
                  'requirements': recipe['requirements'], 'python_version': recipe['python_version'],
                  'temporary': str(attempt / 'tmp'), 'junit': str(attempt / 'pytest.junit.xml'),
                  'result': str(attempt / 'pytest-observation.json')}
        write_json(attempt / 'child-config.json', config)
        write_json(attempt / 'dependency-snapshot.json', env_runtime['dependency_snapshot'])
        argv = [env_runtime['python'], '-I', '-S', '-B', bootstrap, attempt / 'child-config.json']
        environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'TZ': 'UTC',
                       'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'TMPDIR': str(attempt / 'tmp-environment')}
        Path(environment['TMPDIR']).mkdir()
        begin = {'attempt_id': attempt_id, 'started_at': now(), 'nonce': nonce,
                 'argv': list(map(str, argv)), 'environment_keys': sorted(environment),
                 'workspace_sha256': before['version'], 'runtime': env_runtime['report'],
                 'observer_sha256': sha(bootstrap.read_bytes()), 'run_requested': True}
        write_json(attempt / 'started.json', begin)
        state['dispatch_started'] = True
        process = run_process(argv, cwd=copied, env=environment,
            timeout=max(0.01, timeout - 5 - (time.monotonic() - started)), directory=attempt)
        state['process'] = process
        write_json(attempt / 'process.json', process)
        observation = None
        try:
            observation = read_json(attempt / 'pytest-observation.json')
        except (OSError, ValueError):
            pass
        after, snapshot_after = snapshot(workspace), snapshot(copied)
        write_json(attempt / 'after.json', after)
        write_json(attempt / 'executed-after.json', snapshot_after)
        evaluation = summarize(process, observation, before, after, nonce=nonce, tests=recipe['tests'],
            module=recipe['module'], dependencies=env_runtime['dependency_snapshot']['files'])
        after_runtime = runtime(python, recipe)['report']
        evaluation.update(executed_snapshot_bound=before == snapshot_after,
                          runtime_bound=after_runtime == env_runtime['report'])
        if not evaluation['executed_snapshot_bound'] or not evaluation['runtime_bound']:
            evaluation.update(status='capture_incomplete', reason='execution_snapshot_or_runtime_changed')
        aliases = {str(copied): '<workspace>', str(session): '<controller-session>',
                   str(env_runtime['venv']): '<dependencies>', str(env_runtime['target'].parent.parent): '<python-runtime>',
                   str(ROOT): '<research-repository>', os.uname().nodename: 'controller-host'}
        stream_records = {}
        for name in ('stdout', 'stderr'):
            raw = (attempt / (name + '.raw')).read_bytes()
            published = redact(raw, aliases)
            (output / (name + '.txt')).write_bytes(published)
            stream_records[name] = {'path': name + '.txt', 'raw_sha256': sha(raw),
                'published_sha256': sha(published), 'raw_bytes': len(raw),
                'published_bytes': len(published), 'verbatim': raw == published,
                'redaction': 'known_controller_runtime_paths_and_host_name'}
        if observation is not None:
            safe_observation = json.loads(redact(canonical(observation).encode(), aliases))
            write_json(output / 'pytest-observation.json', safe_observation)
        junit = attempt / 'pytest.junit.xml'
        if junit.is_file():
            raw = junit.read_bytes()
            published = redact(raw, aliases)
            (output / 'pytest.junit.xml').write_bytes(published)
            stream_records['junit'] = {'path': 'pytest.junit.xml', 'raw_sha256': sha(raw),
                'published_sha256': sha(published), 'verbatim': raw == published}
        write_json(output / 'workspace-before.json', before)
        write_json(output / 'workspace-after.json', after)
        captured_environment = dict(env_runtime['report'])
        if observation is not None:
            captured_environment.update(python_version_not_yet_executed=False,
                                        observed_python_version=observation.get('python_version'))
        event = {'schema_version': SCHEMA, 'kind': 'controller_python_test_execution',
                 'event_id': attempt_id + '-' + nonce, 'attempt_id': attempt_id, 'task_id': recipe['task_id'],
                 'public_sha256': recipe['public_sha256'], 'fixed_tests': recipe['tests'],
                 'plugins': recipe['plugins'], 'execution_mode': mode, 'os_isolation': False,
                 'isolation_note': 'Reviewed clean public source, empty inherited environment, explicit imports; not an OS security boundary.',
                 'model_visible_controller_files': False, 'external_network_permitted': False,
                 'network_guard': 'Python audit hook denies connections/DNS/sends; permits loopback port-zero bind probes; not an OS sandbox',
                 'source_executions': int(process['spawned']), 'model_requests': 0,
                 'provider_requests': 0, 'native_compactions': 0, 'method_attempts_reserved': 0,
                 'accepted_p1_task_count': 0, 'scientific_ready': False, 'method_runtime_ready': False,
                 'archive_created': False, 'native_event_claimed': False,
                 'observer_sha256': begin['observer_sha256'], 'environment': captured_environment,
                 'process': {k: v for k, v in process.items() if k not in ('stdout', 'stderr')},
                 'raw_streams_retained_in_controller_attempt': True,
                 'streams': stream_records, 'evaluation': evaluation,
                 'workspace_before_sha256': before['version'], 'workspace_after_sha256': after['version'],
                 'executed_snapshot_after_sha256': snapshot_after['version'],
                 'scope_note': 'Only the selected public tests are observed; a pass does not establish the requested fix or accepted P1 workflow.',
                 'elapsed_seconds': time.monotonic() - started}
        event['sha256'] = digest(event)
        write_json(attempt / 'capture.json', event)
        write_json(output / 'capture.json', event)
        return event


def execute(session, python, output, *, timeout=300, mode='controller-only', run=False):
    state = {}
    try:
        return _execute(session, python, output, timeout=timeout, mode=mode, run=run, state=state)
    except Exception as exc:
        if 'output' not in state:
            raise  # Read-only admission failures create no attempt or output.
        event = {'schema_version': SCHEMA, 'kind': 'controller_capture_failure',
                 'attempt_id': state.get('attempt_id'), 'task_id': state['task_id'],
                 'public_sha256': state['public_sha256'], 'os_isolation': False,
                 'evaluation': {'status': 'capture_incomplete', 'reason': 'controller_capture_error'},
                 'error': {'type': type(exc).__name__,
                           'code': str(exc) if isinstance(exc, CaptureError) else 'controller_exception'},
                 'process': state.get('process'), 'source_executions':
                     int(state['process']['spawned']) if 'process' in state else
                     (None if state.get('dispatch_started') else 0),
                 'model_requests': 0, 'provider_requests': 0, 'method_attempts_reserved': 0,
                 'scientific_ready': False, 'method_runtime_ready': False,
                 'raw_attempt_preserved': 'attempt' in state, 'finished_at': now()}
        event['sha256'] = digest(event)
        if 'attempt' in state:
            write_json(state['attempt'] / 'controller-failure.json', event)
        destination = state['output'] / 'capture.json'
        if not destination.exists():
            write_json(destination, event)
        return event


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('inspect'); p.add_argument('--public', required=True, type=Path); p.add_argument('--python', type=Path)
    p = sub.add_parser('prepare'); p.add_argument('--public', required=True, type=Path); p.add_argument('--session', required=True, type=Path)
    p = sub.add_parser('execute')
    for key in ('session', 'python', 'output'):
        p.add_argument('--' + key, required=True, type=Path)
    p.add_argument('--run', action='store_true')
    p.add_argument('--execution-mode', choices=['controller-only'], default='controller-only')
    p.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args(argv)
    if args.command == 'inspect':
        result = inspect(args.public, args.python)
    elif args.command == 'prepare':
        result = prepare(args.public, args.session)
    else:
        result = execute(args.session, args.python, args.output, timeout=args.timeout, mode=args.execution_mode, run=args.run)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get('evaluation', {}).get('status', 'tests_passed') == 'tests_passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
