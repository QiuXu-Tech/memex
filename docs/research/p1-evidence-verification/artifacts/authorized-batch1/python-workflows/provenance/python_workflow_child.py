#!/usr/bin/env python3
"""Trusted pytest observer launched with -I -S by python_workflow.py.

This is controller instrumentation, not a model tool or an adversarial sandbox.
It does not process .pth/egg-link files or load installed pytest entry points.
Its JSON is corroborated with the controller's actual process exit and snapshots.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time


def sha(data):
    return hashlib.sha256(data).hexdigest()


def origins(target, workspace, dependencies):
    observed = {}
    for name, module in list(sys.modules.items()):
        if name != target and not name.startswith(target + '.'):
            continue
        # This exact Requests base exposes real dependency objects through
        # requests.packages.* for compatibility. They are not project code.
        prefix = 'requests.packages.'
        suffix = name[len(prefix):] if target == 'requests' and name.startswith(prefix) else ''
        original = getattr(module, '__name__', '')
        ordinary = (suffix == 'urllib3' or suffix.startswith('urllib3.')
                    or suffix == 'idna' or suffix.startswith('idna.')) and sys.modules.get(suffix) is module
        charset = suffix == 'chardet' and (original == 'chardet' or original.startswith('chardet.')
                    or original == 'charset_normalizer' or original.startswith('charset_normalizer.'))
        value = getattr(module, '__file__', None)
        file = Path(value).resolve(strict=True) if value else None
        if file is not None and not file.is_file():
            raise ValueError('project_module_not_regular')
        if file is not None and file.is_relative_to(workspace):
            observed[name] = {'path': file.relative_to(workspace).as_posix(),
                              'scope': 'workspace', 'sha256': sha(file.read_bytes())}
            continue
        six_moves = 'urllib3.packages.six.moves'
        if ordinary and (suffix == six_moves or suffix.startswith(six_moves + '.')):
            # six installs synthetic namespaces and aliases standard-library
            # modules. Bind the known alias producer rather than inventing a
            # project source file for those objects.
            standard_library = Path(os.__file__).resolve().parent
            if file is not None and not (file.is_relative_to(standard_library) or file.is_relative_to(dependencies)):
                raise ValueError('dependency_alias_outside_bound_runtime')
            owner = Path(sys.modules['urllib3.packages.six'].__file__).resolve(strict=True)
            if not owner.is_relative_to(dependencies):
                raise ValueError('dependency_alias_owner_outside_bound_dependencies')
            observed[name] = {'scope': 'bound_dependency_runtime_alias', 'canonical_module': original,
                'bound_owner_module': 'urllib3.packages.six',
                'bound_owner_path': owner.relative_to(dependencies).as_posix(),
                'bound_owner_sha256': sha(owner.read_bytes())}
            continue
        if (not (ordinary or charset) or sys.modules.get(original) is not module
                or file is None or not file.is_relative_to(dependencies)):
            raise ValueError('project_import_outside_current_workspace')
        observed[name] = {'scope': 'pinned_dependency_alias', 'canonical_module': original,
                          'path': file.relative_to(dependencies).as_posix(),
                          'sha256': sha(file.read_bytes())}
    if target not in observed:
        raise ValueError('project_main_module_not_imported')
    return observed


class Observation:
    def __init__(self):
        self.started = False
        self.finished = False
        self.exitstatus = None
        self.collected = []
        self.collection_errors = []
        self.collection_skips = []
        self.reports = []

    def pytest_sessionstart(self, session):
        self.started = True

    def pytest_collection_finish(self, session):
        self.collected = [item.nodeid for item in session.items]
        if len(self.collected) > 4000:
            raise ValueError('collection_observation_limit')

    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors.append({'nodeid': report.nodeid, 'outcome': report.outcome})
        elif report.skipped:
            self.collection_skips.append({'nodeid': report.nodeid, 'outcome': report.outcome})

    def pytest_runtest_logreport(self, report):
        if len(self.reports) >= 16000:
            raise ValueError('test_observation_limit')
        self.reports.append({'nodeid': report.nodeid, 'when': report.when,
                             'outcome': report.outcome, 'duration_seconds': report.duration,
                             'was_xfail': hasattr(report, 'wasxfail')})

    def pytest_sessionfinish(self, session, exitstatus):
        self.finished = True
        self.exitstatus = int(exitstatus)


def run(config):
    result = {'schema_version': 'p1-python-child-1', 'nonce': config['nonce'],
              'kind': 'actual_pytest_observation', 'python_version': list(sys.version_info[:3]),
              'pth_processing_disabled': bool(sys.flags.no_site),
              'isolated_python_mode': bool(sys.flags.isolated),
              'pytest_started': False, 'pytest_finished': False,
              'network_attempts_blocked': 0, 'local_loopback_bind_probes': 0, 'error': None}
    observer = Observation()
    exit_code = 78
    try:
        if not sys.flags.no_site or not sys.flags.isolated:
            raise ValueError('isolated_no_site_python_required')
        if list(sys.version_info[:3]) != config['python_version']:
            raise ValueError('python_version_mismatch')
        workspace = Path(config['workspace']).resolve(strict=True)
        dependencies = Path(config['dependencies']).resolve(strict=True)
        source_root = (workspace / config['import_root']).resolve(strict=True)
        if not source_root.is_relative_to(workspace):
            raise ValueError('project_import_root_escape')
        # -S leaves only the interpreter's standard-library paths. Add these
        # directories explicitly; never execute site.py, .pth or egg-link files.
        sys.path[:0] = [str(source_root), str(workspace), str(dependencies)]
        os.chdir(workspace)
        installed = {}
        for distribution in importlib.metadata.distributions(path=[str(dependencies)]):
            name = distribution.metadata['Name']
            if not name:
                continue
            key = name.lower().replace('_', '-').replace('.', '-')
            if key in installed:
                raise ValueError('ambiguous_dependency_metadata')
            installed[key] = distribution.version
        for name, expected in config['requirements'].items():
            if installed.get(name) != expected:
                raise ValueError('dependency_version_mismatch')
        result['dependency_versions'] = {k: installed[k] for k in config['requirements']}

        def deny_connections(event, args):
            # A Python audit hook is a guard for these reviewed local tests,
            # not OS isolation and not a defense against arbitrary native code.
            # urllib3's import-time IPv6 capability probe binds ::1 port 0;
            # it does not listen, connect, send, or contact an external host.
            if event == 'socket.bind' and len(args) > 1:
                address = args[1]
                if isinstance(address, tuple) and len(address) >= 2 and address[0] in ('127.0.0.1', '::1') and address[1] == 0:
                    result['local_loopback_bind_probes'] += 1
                    return
            if event in ('socket.connect', 'socket.connect_ex', 'socket.bind',
                         'socket.sendto', 'socket.sendmsg', 'socket.getaddrinfo',
                         'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.getnameinfo'):
                result['network_attempts_blocked'] += 1
                raise PermissionError('network_operation_forbidden_in_source_capture')

        sys.addaudithook(deny_connections)
        pytest = importlib.import_module('pytest')
        if not Path(pytest.__file__).resolve().is_relative_to(dependencies):
            raise ValueError('pytest_import_outside_bound_dependencies')
        importlib.import_module(config['module'])
        result['project_origins_before'] = origins(config['module'], workspace, dependencies)
        expected_main = (source_root / config['module'] / '__init__.py').relative_to(workspace).as_posix()
        if result['project_origins_before'][config['module']]['path'] != expected_main:
            raise ValueError('project_main_origin_mismatch')
        # Preserve the public project's pytest configuration. Only output,
        # cache and temporary-file locations change; test selectors stay fixed.
        arguments = ['-q', '-p', 'no:cacheprovider', '--confcutdir=' + str(workspace),
                     '--rootdir=' + str(workspace), '--basetemp=' + config['temporary'],
                     '--junitxml=' + config['junit']]
        for plugin in config['plugins']:
            arguments.extend(['-p', plugin])
        arguments.extend(config['tests'])
        result['selected_tests'] = config['tests']
        exit_code = int(pytest.main(arguments, plugins=[observer]))
        result['project_origins_after'] = origins(config['module'], workspace, dependencies)
    except BaseException as exc:
        # Keep process/pytest failure separate from a successful test result.
        result['error'] = {'type': type(exc).__name__, 'code': str(exc)[:1000]}
        exit_code = 78
    finally:
        result.update({'pytest_started': observer.started, 'pytest_finished': observer.finished,
                       'pytest_exit_code': observer.exitstatus, 'process_exit_requested': exit_code,
                       'collected': observer.collected, 'collection_errors': observer.collection_errors,
                       'collection_skips': observer.collection_skips,
                       'reports': observer.reports, 'finished_at_unix_ns': time.time_ns()})
        path = Path(config['result'])
        with path.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, sort_keys=True, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
    return exit_code


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('one controller config required')
    with open(sys.argv[1], encoding='utf-8') as stream:
        configuration = json.load(stream)
    raise SystemExit(run(configuration))
