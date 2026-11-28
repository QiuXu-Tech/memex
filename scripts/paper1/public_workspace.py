#!/usr/bin/env python3
"""Public-only workspace tools and explicitly probed OS-isolated pytest runs.

Reading/editing never executes project code. An edited snapshot may execute only
through SandboxRunner after that instance has run its own actual isolation
probe. No credentials, providers, installers or evaluator files are used.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import runpy
import shutil
import socket
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
WORKFLOW = runpy.run_path(str(HERE / 'python_workflow.py'))
EXPERIMENT = WORKFLOW['EXPERIMENT']
HEX = re.compile(r'[a-f0-9]{64}\Z')
FORBIDDEN = {'.git', '.codex', '.ssh', '.config', 'controller', 'evaluator', 'credentials'}
DEFAULT_LIMITS = {'max_source_open_bytes_per_call': 4000, 'max_source_open_bytes_total': 96000,
                  'max_source_open_calls': 32, 'max_tool_calls': 64,
                  'max_write_bytes_per_call': 65536, 'max_write_bytes_total': 262144,
                  'max_test_seconds': 120, 'max_wall_seconds': 300}


class WorkspaceError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def path(value, *, exists=True):
    target = Path(value).absolute()
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise WorkspaceError('symlink_path_component')
    if exists and not target.exists():
        raise WorkspaceError('path_missing')
    return target


def save(destination, value):
    with Path(destination).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        stream.flush(); os.fsync(stream.fileno())


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise WorkspaceError('invalid_tool_arguments')


def disjoint(*roots):
    for index, left in enumerate(roots):
        for right in roots[index + 1:]:
            if left == right or left.is_relative_to(right) or right.is_relative_to(left):
                raise WorkspaceError('workspace_controller_source_overlap')


def _schema(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


TOOL_DESCRIPTIONS = [
    {'name': 'read_file', 'description': 'Read a bounded UTF-8 byte page from the current public workspace. Returns the complete file hash and next byte offset.',
     'inputSchema': _schema({'path': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0},
                            'limit': {'type': 'integer', 'minimum': 1, 'maximum': 4000}}, ('path', 'offset', 'limit'))},
    {'name': 'write_file', 'description': 'Replace a public text file or an exact UTF-8 byte range. The expected hash must match; use null only for a new file. No code is executed.',
     'inputSchema': _schema({'path': {'type': 'string'}, 'content': {'type': 'string'},
        'expected_sha256': {'type': ['string', 'null']}, 'range': _schema({'start': {'type': 'integer', 'minimum': 0},
        'end': {'type': 'integer', 'minimum': 0}}, ('start', 'end'))}, ('path', 'content', 'expected_sha256'))},
    {'name': 'list_files', 'description': 'List at most 100 public workspace files, with paths and byte sizes. This is not a test result.',
     'inputSchema': _schema({'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}})},
    {'name': 'run_current_tests', 'description': 'Run the fixed public test module on an independent snapshot of the current edited source, only after actual OS sandbox verification. A passing selected suite does not establish hidden behavior or authorize publication.',
     'inputSchema': _schema({})},
    {'name': 'record_review', 'description': 'Record a local review tied to the current source and actual prior tool receipts. The review is not independently graded and is not published.',
     'inputSchema': _schema({'text': {'type': 'string', 'maxLength': 16000},
        'evidence_event_ids': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 64}}, ('text', 'evidence_event_ids'))},
]


class SandboxRunner:
    """Construct restrictive bwrap/Seatbelt launches and verify them in-process.

    command() is preparation only. probe() executes only the embedded own-code
    probe. No serialized receipt or boolean can activate a new runner instance.
    A successful instance may run the trusted observer until configuration,
    binary/interpreter/dependency identity changes or the probe expires.
    """
    def __init__(self, config):
        fields(config, ('kind', 'executable', 'python', 'dependencies', 'runtime_roots'))
        if config['kind'] not in ('bwrap', 'sandbox-exec') or not isinstance(config['runtime_roots'], list) or not 1 <= len(config['runtime_roots']) <= 12:
            raise WorkspaceError('invalid_sandbox_configuration')
        executable = path(config['executable'])
        python = Path(config['python']).resolve(strict=True)
        dependencies = path(config['dependencies'])
        if (not executable.is_file() or executable.name != config['kind'] or not os.access(executable, os.X_OK)
                or not python.is_file() or not os.access(python, os.X_OK) or not dependencies.is_dir()):
            raise WorkspaceError('invalid_sandbox_executable_or_dependencies')
        prohibited = {'/', '/home', '/Users', '/root', '/workspace', '/private', '/var', '/tmp', '/etc', '/opt'}
        roots = []
        for raw in config['runtime_roots']:
            if not isinstance(raw, str) or raw in prohibited or not Path(raw).is_absolute() or Path(raw) == Path.home():
                raise WorkspaceError('overbroad_sandbox_runtime_root')
            root = path(raw)
            # An explicitly installed interpreter may live in a precise
            # dependency subtree below .config. The exact subtree is mounted;
            # its .config ancestor and sibling controller files are not.
            if (not root.is_dir() or root.name in FORBIDDEN
                    or any(part in FORBIDDEN - {'.config'} or part.startswith('.env') for part in root.parts)):
                raise WorkspaceError('invalid_sandbox_runtime_root')
            roots.append(root)
        if not any(python.is_relative_to(root) for root in roots):
            raise WorkspaceError('python_runtime_mount_required')
        self.config = {'kind': config['kind'], 'executable': str(executable), 'python': str(python),
                       'dependencies': str(dependencies), 'runtime_roots': [str(root) for root in roots]}
        self._proof = None
        self._proof_binding = None
        self._probed_at = None

    def binding(self):
        dependency_snapshot = WORKFLOW['snapshot'](self.config['dependencies'], max_bytes=256 * 1024 * 1024, max_files=40000)
        return {'config_sha256': digest(self.config), 'executable_sha256': sha(path(self.config['executable'])),
                'python_sha256': sha(path(self.config['python'])), 'dependencies_sha256': dependency_snapshot['version'],
                'platform': sys.platform, 'kernel': os.uname().release}

    @property
    def verified(self):
        if self._proof is None or self._probed_at is None or time.monotonic() - self._probed_at > 3600:
            return False
        try:
            return self.binding() == self._proof_binding
        except (OSError, ValueError):
            return False

    def paths(self, workspace, output):
        if self.config['kind'] == 'bwrap':
            return {'workspace': '/p1/workspace', 'dependencies': '/p1/dependencies', 'bootstrap': '/p1/observer.py',
                    'config': '/p1/config.json', 'output': '/p1/output'}
        return {'workspace': str(Path(workspace).absolute()), 'dependencies': self.config['dependencies'],
                'output': str(Path(output).absolute())}

    def command(self, *, workspace, bootstrap, config, output):
        workspace, bootstrap, config, output = map(path, (workspace, bootstrap, config, output))
        dependencies = path(self.config['dependencies'])
        if not workspace.is_dir() or not output.is_dir() or not bootstrap.is_file() or not config.is_file():
            raise WorkspaceError('invalid_sandbox_inputs')
        disjoint(workspace, output, dependencies)
        roots = [path(root) for root in self.config['runtime_roots']]
        for root in roots:
            if any(p == root or p.is_relative_to(root) for p in (workspace, output, bootstrap, config)):
                raise WorkspaceError('sandbox_runtime_root_exposes_controller')
        environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'TZ': 'UTC', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}
        if self.config['kind'] == 'bwrap':
            argv = [self.config['executable'], '--unshare-all', '--unshare-net', '--disable-userns', '--assert-userns-disabled', '--die-with-parent', '--new-session',
                    '--cap-drop', 'ALL', '--clearenv', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/p1']
            system = [Path(p) for p in ('/usr/lib', '/usr/lib64', '/usr/share/zoneinfo') if Path(p).is_dir()]
            mounted = set()
            for root in system + roots:
                if str(root) not in mounted:
                    argv += ['--ro-bind', str(root), str(root)]; mounted.add(str(root))
            for alias in ('/lib', '/lib64'):
                link = Path(alias)
                if link.is_symlink():
                    argv += ['--symlink', os.readlink(link), alias]
                elif link.is_dir() and alias not in mounted:
                    argv += ['--ro-bind', alias, alias]
            argv += ['--ro-bind', str(dependencies), '/p1/dependencies', '--bind', str(workspace), '/p1/workspace',
                     '--bind', str(output), '/p1/output', '--ro-bind', str(bootstrap), '/p1/observer.py',
                     '--ro-bind', str(config), '/p1/config.json', '--chdir', '/p1/workspace']
            for key, value in environment.items():
                argv += ['--setenv', key, value]
            argv += ['--setenv', 'TMPDIR', '/p1/output/tmp', '--', self.config['python'], '-I', '-S', '-B', '/p1/observer.py', '/p1/config.json']
            paths = self.paths(workspace, output)
        else:
            read_roots = roots + [dependencies, workspace, output]
            read_roots += [Path(p) for p in ('/usr/lib', '/System/Library', '/Library/Apple/System/Library', '/private/var/db/dyld') if Path(p).exists()]
            lines = ['(version 1)', '(deny default)', '(deny network*)', '(allow process-exec)', '(deny process-fork)',
                     '(allow signal (target same-sandbox))', '(allow process-info* (target same-sandbox))',
                     '(allow sysctl-read)', '(allow file-write-data (literal "/dev/null"))',
                     # getcwd may inspect the root directory on macOS. A literal
                     # grant does not expose any child file or private subtree.
                     '(allow file-read* (literal "/"))',
                     '(allow file-read* (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))']
            lines += ['(allow file-read* (subpath ' + json.dumps(str(root)) + '))' for root in read_roots]
            lines += ['(allow file-read* (literal ' + json.dumps(str(file)) + '))' for file in (bootstrap, config)]
            ancestors = {str(parent) for node in read_roots + [bootstrap, config] for parent in node.parents}
            lines += ['(allow file-read-metadata (literal ' + json.dumps(parent) + '))' for parent in sorted(ancestors)]
            lines += ['(allow file-write* (subpath ' + json.dumps(str(root)) + '))' for root in (workspace, output)]
            policy = '\n'.join(lines) + '\n'
            profile = output.parent / ('sandbox-policy-' + uuid.uuid4().hex + '.sb')
            with profile.open('x') as stream:
                stream.write(policy); stream.flush(); os.fsync(stream.fileno())
            argv = [self.config['executable'], '-f', str(profile), self.config['python'], '-I', '-S', '-B', str(bootstrap), str(config)]
            paths = {**self.paths(workspace, output), 'bootstrap': str(bootstrap), 'config': str(config)}
            environment['TMPDIR'] = str(output / 'tmp')
        return {'argv': argv, 'environment': environment, 'paths': paths, 'config_sha256': digest(self.config)}

    def _launch(self, *, workspace, bootstrap, config, output, timeout):
        output = path(output, exists=False)
        if output.exists():
            raise WorkspaceError('sandbox_execution_output_must_be_new')
        output.mkdir(parents=True)
        writable = output / 'sandbox-output'; writable.mkdir()
        (writable / 'tmp').mkdir()
        capture = output / 'capture'; capture.mkdir()
        launch = self.command(workspace=workspace, bootstrap=bootstrap, config=config, output=writable)
        save(output / 'launch.json', launch)
        process = WORKFLOW['run_process'](launch['argv'], cwd=workspace, env=launch['environment'], timeout=timeout, directory=capture)
        save(output / 'process.json', process)
        return {'process': process, 'result_dir': str(writable), 'capture_dir': str(capture), 'launch_sha256': sha(output / 'launch.json')}

    def probe(self, output, *, timeout=15):
        """Run only own-code denial checks. Never run project code in a probe."""
        if (self.config['kind'] == 'bwrap' and not sys.platform.startswith('linux')) or (self.config['kind'] == 'sandbox-exec' and sys.platform != 'darwin'):
            raise WorkspaceError('sandbox_platform_mismatch')
        if type(timeout) not in (int, float) or not 0 < timeout <= 30:
            raise WorkspaceError('invalid_sandbox_probe_timeout')
        self._proof = self._proof_binding = self._probed_at = None
        binding = self.binding()
        output = path(output, exists=False)
        if output.exists():
            raise WorkspaceError('sandbox_probe_output_must_be_new')
        output.mkdir(parents=True)
        workspace = output / 'public'; workspace.mkdir()
        (workspace / 'allowed.txt').write_text('probe-allowed')
        private = output / 'private'; private.mkdir()
        private_file = private / 'sentinel.txt'; private_file.write_text('probe-private-' + uuid.uuid4().hex)
        private_hash = sha(private_file)
        bootstrap = output / 'probe.py'
        bootstrap.write_text(_PROBE_SOURCE)
        nonce = uuid.uuid4().hex
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', 0)); listener.listen(2); listener.settimeout(2)
            port = listener.getsockname()[1]
            with socket.create_connection(('127.0.0.1', port), timeout=2):
                connection, _ = listener.accept(); connection.close()
            mapped = self.paths(workspace, output / 'execution/sandbox-output')
            cfg = {'nonce': nonce, 'workspace': mapped['workspace'], 'output': mapped['output'],
                   'private_file': str(private_file), 'port': port}
            config = output / 'probe-config.json'; save(config, cfg)
            capture = self._launch(workspace=workspace, bootstrap=bootstrap, config=config, output=output / 'execution', timeout=timeout)
        raw = Path(capture['capture_dir']) / 'stdout.raw'
        checks = None
        try:
            report = EXPERIMENT['strict_json'](raw.read_text())
            if isinstance(report, dict) and report.get('nonce') == nonce:
                checks = report.get('checks')
        except (OSError, ValueError):
            pass
        wanted = {'allowed_read', 'allowed_write', 'private_read_denied', 'private_write_denied', 'loopback_connection_denied'}
        process = capture['process']
        try:
            private_unchanged = sha(private_file) == private_hash
        except (OSError, ValueError):
            private_unchanged = False
        try:
            observed_write = (Path(capture['result_dir']) / 'allowed-write.txt').read_text() == nonce
        except (OSError, ValueError):
            observed_write = False
        try:
            unchanged_binding = self.binding() == binding
        except (OSError, ValueError):
            unchanged_binding = False
        valid = (process.get('spawned') is True and process.get('returncode') == 0 and not process.get('error')
                 and not process.get('timed_out') and not process.get('output_limit_exceeded')
                 and isinstance(checks, dict) and set(checks) == wanted and all(value is True for value in checks.values())
                 and private_unchanged and observed_write and unchanged_binding)
        receipt = {'schema_version': 1, 'kind': 'actual_os_sandbox_probe', 'status': 'passed' if valid else 'failed',
                   'binding': binding, 'checks': checks, 'process': process, 'probe_source_sha256': sha(bootstrap),
                   'launch_sha256': capture['launch_sha256'], 'private_sentinel_unchanged': private_unchanged,
                   'real_source_executions': 0, 'model_requests': 0, 'provider_requests': 0}
        save(output / 'probe-receipt.json', receipt)
        if valid:
            self._proof, self._proof_binding, self._probed_at = receipt, binding, time.monotonic()
        return receipt

    def run_observer(self, *, workspace, bootstrap, config, output, timeout):
        if not self.verified:
            raise WorkspaceError('verified_os_sandbox_required')
        return self._launch(workspace=workspace, bootstrap=bootstrap, config=config, output=output, timeout=timeout)


_PROBE_SOURCE = '''import json, pathlib, socket, sys
cfg = json.loads(pathlib.Path(sys.argv[1]).read_text())
checks = {}
checks["allowed_read"] = (pathlib.Path(cfg["workspace"]) / "allowed.txt").read_text() == "probe-allowed"
target = pathlib.Path(cfg["output"]) / "allowed-write.txt"
target.write_text(cfg["nonce"])
checks["allowed_write"] = target.read_text() == cfg["nonce"]
try:
    pathlib.Path(cfg["private_file"]).read_bytes()
    checks["private_read_denied"] = False
except (PermissionError, FileNotFoundError):
    checks["private_read_denied"] = True
try:
    pathlib.Path(cfg["private_file"]).write_text("forbidden-probe-write")
    checks["private_write_denied"] = False
except (PermissionError, FileNotFoundError):
    checks["private_write_denied"] = True
try:
    with socket.create_connection(("127.0.0.1", cfg["port"]), timeout=0.5):
        checks["loopback_connection_denied"] = False
except OSError:
    checks["loopback_connection_denied"] = True
print(json.dumps({"nonce": cfg["nonce"], "checks": checks}))
raise SystemExit(0 if all(checks.values()) else 3)
'''


class PublicWorkspace:
    def __init__(self, public_path, workdir, controller_root, *, authorize_operation, limits=None,
                 sandbox=None, python=None, source_snapshot=None, expected_snapshot_sha256=None):
        if not callable(authorize_operation):
            raise WorkspaceError('tool_admission_callback_required')
        self.public = path(public_path)
        self.recipe = WORKFLOW['profile'](self.public)
        self.workdir, self.controller_root = path(workdir, exists=False), path(controller_root, exists=False)
        disjoint(self.public, self.workdir, self.controller_root)
        if self.workdir.exists() or self.controller_root.exists():
            raise WorkspaceError('fresh_public_workspace_session_required')
        self.limits = dict(DEFAULT_LIMITS)
        if limits is not None:
            if not isinstance(limits, dict) or set(limits) - set(DEFAULT_LIMITS) or any(
                    type(v) is not int or not 0 < v <= DEFAULT_LIMITS[k] for k, v in limits.items()):
                raise WorkspaceError('workspace_limits_exceed_public_budget')
            self.limits.update(limits)
        if self.limits['max_source_open_bytes_per_call'] > self.limits['max_source_open_bytes_total']:
            raise WorkspaceError('page_limit_exceeds_total_budget')
        source = self.public / 'workspace' if source_snapshot is None else path(source_snapshot)
        if source_snapshot is not None and (not HEX.fullmatch(str(expected_snapshot_sha256))
                or EXPERIMENT['public_digest'](source) != expected_snapshot_sha256):
            raise WorkspaceError('fork_workspace_snapshot_mismatch')
        original_digest = EXPERIMENT['public_digest'](source)
        self.controller_root.mkdir(parents=True, mode=0o700)
        self.workdir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, self.workdir, copy_function=shutil.copy2)
        if EXPERIMENT['public_digest'](self.workdir) != original_digest:
            raise WorkspaceError('detached_workspace_copy_mismatch')
        self.authorize_operation, self.sandbox, self.python = authorize_operation, sandbox, python
        self._counters = {'tool_calls': 0, 'source_open_calls': 0, 'source_open_bytes': 0,
            'write_calls': 0, 'write_bytes': 0, 'test_execution_attempts': 0, 'test_executions': 0,
            'reviews': 0, 'rejected_calls': 0}
        self._known = {}
        self._deadline = time.monotonic() + self.limits['max_wall_seconds']
        self.session_id = 'public-' + uuid.uuid4().hex
        self.journal = EXPERIMENT['Journal'](self.controller_root / 'tool-events.jsonl')
        save(self.controller_root / 'session.json', {'schema_version': 1, 'session_id': self.session_id,
             'task_id': self.recipe['task_id'], 'public_sha256': self.recipe['public_sha256'],
             'initial_workspace_sha256': original_digest, 'limits': self.limits,
             'model_requests': 0, 'scientific_ready': False})

    @property
    def tool_descriptions(self):
        return copy.deepcopy(TOOL_DESCRIPTIONS)

    @property
    def counters(self):
        return dict(self._counters)

    def constrain_deadline(self, deadline):
        """Bind to a controller's monotonic deadline without extending this session.

        An already elapsed finite deadline is retained so every subsequent tool
        fails before its side effect. This is not a model-visible tool.
        """
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise WorkspaceError('invalid_controller_deadline')
        self._deadline = min(self._deadline, deadline)
        return self._deadline

    def snapshot(self):
        observed = WORKFLOW['snapshot'](self.workdir)
        return {**observed, 'observer_version': observed['version'], 'version': EXPERIMENT['public_digest'](self.workdir),
                'digest_algorithm': 'experiment_public_digest'}

    def _relative(self, name, *, exists=True):
        if (not isinstance(name, str) or not name or Path(name).is_absolute() or '..' in Path(name).parts
                or Path(name).as_posix() != name or name == '.'
                or any(part in FORBIDDEN or part == '.env' or part.startswith('.env.') for part in Path(name).parts)):
            raise WorkspaceError('nonpublic_workspace_path')
        return path(self.workdir / name, exists=exists)

    def call(self, name, arguments):
        # One broker process owns a session; a filesystem lock also serializes
        # ordinary callers. Reopening the same session to reset counters fails.
        with (self.controller_root / 'tool.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            event_id = 'tool-' + uuid.uuid4().hex
            ok, before, after, result = False, None, None, None
            try:
                if self._counters['tool_calls'] >= self.limits['max_tool_calls']:
                    self._counters['rejected_calls'] += 1
                    raise WorkspaceError('public_tool_call_budget_exhausted')
                self._counters['tool_calls'] += 1
                if time.monotonic() >= self._deadline:
                    raise WorkspaceError('public_workspace_deadline_exhausted')
                if name not in {t['name'] for t in TOOL_DESCRIPTIONS} or not isinstance(arguments, dict):
                    raise WorkspaceError('unknown_or_invalid_public_tool')
                kinds = ['public_tool_call']
                if name == 'read_file':
                    if self._counters['source_open_calls'] >= self.limits['max_source_open_calls']:
                        raise WorkspaceError('source_open_call_budget_exhausted')
                    self._counters['source_open_calls'] += 1
                    kinds.append('source_open')
                before = self.snapshot()['version']
                intent = {'schema_version': 1, 'operation_id': event_id, 'tool': name,
                    'arguments_sha256': digest(arguments), 'workspace_sha256': before, 'kinds': kinds,
                    'observable_kind': 'test_execution' if name == 'run_current_tests' else name}
                self.journal.append({'event': 'tool_started', 'intent': intent})
                admission = self.authorize_operation(copy.deepcopy(intent))
                if admission != {'operation_id': event_id, 'admitted_kinds': kinds}:
                    raise WorkspaceError('public_tool_admission_mismatch')
                self.journal.append({'event': 'tool_admitted', 'operation_id': event_id, 'admission': admission})
                if time.monotonic() >= self._deadline:
                    raise WorkspaceError('public_workspace_deadline_exhausted')
                result = getattr(self, '_' + name)(arguments, event_id)
                after = self.snapshot()['version']
                ok = True
            except Exception as error:
                code = str(error) if isinstance(error, WorkspaceError) else 'public_tool_capture_error'
                result = {'error': code}
            receipt = {'schema_version': 1, 'kind': 'public_workspace_operation', 'event_id': event_id,
                'tool': name if isinstance(name, str) else 'invalid', 'ok': ok, 'workspace_before_sha256': before,
                'workspace_after_sha256': after, 'result_sha256': digest(result), 'authorizesExecution': False}
            self.journal.append({'event': 'tool_finished', 'receipt': receipt, 'result': result, 'counters': self.counters})
            self._known[event_id] = receipt
            return {'ok': ok, 'result': result, 'receipt': receipt}

    def _read_file(self, args, event_id):
        fields(args, ('path', 'offset', 'limit'))
        offset, limit = args['offset'], args['limit']
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 0 < limit <= self.limits['max_source_open_bytes_per_call']:
            raise WorkspaceError('invalid_source_page')
        if self._counters['source_open_bytes'] + limit > self.limits['max_source_open_bytes_total']:
            raise WorkspaceError('source_open_byte_budget_exhausted')
        target = self._relative(args['path'])
        if not target.is_file() or target.stat().st_size > 4 * 1024 * 1024:
            raise WorkspaceError('bounded_text_file_required')
        raw = target.read_bytes()
        if offset > len(raw):
            raise WorkspaceError('source_offset_out_of_range')
        try:
            raw[:offset].decode('utf-8')
            selected = raw[offset:offset + limit]
            for trim in range(4):
                try:
                    actual = selected if trim == 0 else selected[:-trim]
                    text = actual.decode('utf-8'); break
                except UnicodeDecodeError:
                    if trim == 3:
                        raise
        except UnicodeDecodeError:
            raise WorkspaceError('source_not_utf8_or_invalid_boundary') from None
        self._counters['source_open_bytes'] += len(actual)
        return {'path': args['path'], 'text': text, 'offset': offset, 'bytes': len(actual), 'file_bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'next_offset': offset + len(actual) if offset + len(actual) < len(raw) else None}

    def _write_file(self, args, event_id):
        fields(args, ('path', 'content', 'expected_sha256'), ('range',))
        if not isinstance(args['content'], str):
            raise WorkspaceError('write_content_must_be_text')
        content = args['content'].encode('utf-8')
        if len(content) > self.limits['max_write_bytes_per_call'] or self._counters['write_bytes'] + len(content) > self.limits['max_write_bytes_total']:
            raise WorkspaceError('write_byte_budget_exhausted')
        target = self._relative(args['path'], exists=False)
        if target.exists() and (not target.is_file() or target.stat().st_nlink != 1):
            raise WorkspaceError('write_target_must_be_independent_file')
        previous = target.read_bytes() if target.exists() else None
        expected = args['expected_sha256']
        if (previous is None and expected is not None) or (previous is not None and expected != hashlib.sha256(previous).hexdigest()):
            raise WorkspaceError('write_expected_hash_mismatch')
        if 'range' in args:
            fields(args['range'], ('start', 'end'))
            start, end = args['range']['start'], args['range']['end']
            if previous is None or any(type(v) is not int for v in (start, end)) or not 0 <= start <= end <= len(previous):
                raise WorkspaceError('invalid_write_range')
            try:
                previous[:start].decode('utf-8'); previous[end:].decode('utf-8')
            except UnicodeDecodeError:
                raise WorkspaceError('write_range_not_utf8_boundary') from None
            content = previous[:start] + content + previous[end:]
        if len(content) > 4 * 1024 * 1024:
            raise WorkspaceError('edited_file_size_exceeded')
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / ('.p1-edit-' + uuid.uuid4().hex)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             target.stat().st_mode & 0o777 if target.exists() else 0o644)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        self._counters['write_calls'] += 1
        self._counters['write_bytes'] += len(args['content'].encode('utf-8'))
        return {'path': args['path'], 'sha256': sha(target), 'bytes': len(content), 'executed': False}

    def _list_files(self, args, event_id):
        fields(args, (), ('offset', 'limit'))
        offset, limit = args.get('offset', 0), args.get('limit', 100)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 0 < limit <= 100:
            raise WorkspaceError('invalid_file_listing_page')
        entries = [item for item in self.snapshot()['files'] if item['kind'] == 'file'
                   and not any(part in FORBIDDEN or part.startswith('.env') for part in Path(item['path']).parts)]
        selected = entries[offset:offset + limit]
        return {'files': [{'path': row['path'], 'bytes': row['bytes']} for row in selected],
                'next_offset': offset + len(selected) if offset + len(selected) < len(entries) else None}

    def _record_review(self, args, event_id):
        fields(args, ('text', 'evidence_event_ids'))
        references = args['evidence_event_ids']
        if (not isinstance(args['text'], str) or not args['text'].strip() or len(args['text'].encode()) > 16000
                or not isinstance(references, list) or len(references) > 64 or any(not isinstance(r, str) or r not in self._known for r in references)):
            raise WorkspaceError('review_must_reference_observed_tool_events')
        review = {'review_id': event_id, 'text': args['text'], 'evidence_event_ids': references,
                  'workspace_sha256': self.snapshot()['version'], 'correctness_judged': False, 'published': False}
        folder = self.controller_root / 'reviews'; folder.mkdir(exist_ok=True)
        save(folder / (event_id + '.json'), review)
        self._counters['reviews'] += 1
        return review

    def _run_current_tests(self, args, event_id):
        fields(args, ())
        if not isinstance(self.sandbox, SandboxRunner) or not self.sandbox.verified:
            raise WorkspaceError('verified_os_sandbox_required')
        if self.python is None:
            raise WorkspaceError('explicit_pinned_python_required')
        runtime = WORKFLOW['runtime'](self.python, self.recipe)
        if (not runtime['report']['requirements_match'] or str(runtime['target']) != self.sandbox.config['python']
                or str(runtime['site']) != self.sandbox.config['dependencies']):
            raise WorkspaceError('sandbox_pinned_python_binding_mismatch')
        folder = self.controller_root / 'tests' / event_id; folder.mkdir(parents=True)
        before = WORKFLOW['snapshot'](self.workdir)
        before_public = EXPERIMENT['public_digest'](self.workdir)
        copied = folder / 'workspace'; shutil.copytree(self.workdir, copied, copy_function=shutil.copy2)
        if WORKFLOW['snapshot'](copied) != before:
            raise WorkspaceError('current_test_snapshot_copy_mismatch')
        nonce = uuid.uuid4().hex
        bootstrap = folder / 'observer.py'; bootstrap.write_bytes((HERE / 'python_workflow_child.py').read_bytes())
        mapped = self.sandbox.paths(copied, folder / 'execution/sandbox-output')
        configuration = {'nonce': nonce, 'workspace': mapped['workspace'], 'dependencies': mapped['dependencies'],
            'module': self.recipe['module'], 'import_root': self.recipe['import_root'], 'tests': self.recipe['tests'],
            'plugins': self.recipe['plugins'], 'requirements': self.recipe['requirements'], 'python_version': self.recipe['python_version'],
            'temporary': mapped['output'] + '/pytest-tmp', 'junit': mapped['output'] + '/pytest.junit.xml',
            'result': mapped['output'] + '/pytest-observation.json'}
        cfg = folder / 'observer-config.json'; save(cfg, configuration)
        save(folder / 'workspace-before.json', before)
        save(folder / 'dependency-snapshot.json', runtime['dependency_snapshot'])
        self._counters['test_execution_attempts'] += 1
        remaining = min(self.limits['max_test_seconds'], self._deadline - time.monotonic())
        if remaining <= 0:
            raise WorkspaceError('public_workspace_deadline_exhausted')
        capture = self.sandbox.run_observer(workspace=copied, bootstrap=bootstrap, config=cfg,
                                            output=folder / 'execution', timeout=remaining)
        process = capture['process']
        self._counters['test_executions'] += int(process.get('spawned') is True)
        observation_path = Path(capture['result_dir']) / 'pytest-observation.json'
        observation = None
        if observation_path.is_file() and observation_path.stat().st_size <= 4 * 1024 * 1024:
            try:
                observation = EXPERIMENT['read_json'](observation_path)
            except (OSError, ValueError):
                pass
        after = WORKFLOW['snapshot'](self.workdir)
        executed_after = WORKFLOW['snapshot'](copied)
        summary = WORKFLOW['summarize'](process, observation, before, after, nonce=nonce,
            tests=self.recipe['tests'], module=self.recipe['module'], dependencies=runtime['dependency_snapshot']['files'])
        after_runtime = WORKFLOW['runtime'](self.python, self.recipe)
        if before != executed_after or runtime['report'] != after_runtime['report'] or not self.sandbox.verified:
            summary.update(status='capture_incomplete', reason='executed_snapshot_or_runtime_changed')
        save(folder / 'workspace-after.json', after)
        save(folder / 'executed-after.json', executed_after)
        save(folder / 'summary.json', summary)
        streams = {}
        aliases = {str(copied): '<workspace>', str(self.controller_root): '<controller>',
                   str(runtime['venv']): '<dependencies>', str(runtime['target'].parent.parent): '<python-runtime>',
                   str(HERE.parents[1]): '<research-repository>'}
        for name in ('stdout', 'stderr'):
            raw = (Path(capture['capture_dir']) / (name + '.raw')).read_bytes()
            published = WORKFLOW['redact'](raw, aliases)
            preview = published[:4000].decode('utf-8', errors='replace')
            streams[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'preview': preview,
                             'preview_truncated': len(published) > 4000, 'preview_redaction': 'known_controller_runtime_paths'}
        counts = summary.get('test_counts')
        completed = summary['status'] in ('tests_passed', 'tests_failed')
        result = {'status': {'tests_passed': 'passed', 'tests_failed': 'failed'}.get(summary['status'], 'unknown'),
            'summary_status': summary['status'], 'reason': summary['reason'], 'completed': completed, 'complete': completed,
            'executed': process.get('spawned') is True, 'testCount': counts['collected'] if counts else None,
            'test_counts': counts, 'exitCode': process.get('returncode'), 'signal': process.get('signal'),
            'workspace_before_sha256': before_public, 'workspace_after_sha256': EXPERIMENT['public_digest'](self.workdir),
            'executed_snapshot_after_sha256': EXPERIMENT['public_digest'](copied),
            'observer_workspace_before_sha256': before['version'], 'observer_workspace_after_sha256': after['version'],
            'command': 'pytest ' + ' '.join(self.recipe['tests']), 'selected_tests': self.recipe['tests'],
            'streams': streams, 'observation_sha256': sha(observation_path) if observation_path.is_file() else None,
            'observer_sha256': sha(bootstrap), 'dependency_tree_sha256': runtime['report']['dependency_tree_sha256'],
            'nonce': nonce, 'os_isolation': True, 'sandbox_probe_sha256': digest(self.sandbox._proof),
            'native_execution_claimed': False, 'source_scope': 'selected_public_tests_only',
            'authorizesExecution': False}
        save(folder / 'public-result.json', result)
        return result
