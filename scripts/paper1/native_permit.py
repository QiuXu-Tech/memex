#!/usr/bin/env python3
"""Admit one immutable controller-issued P1 native development permit.

The expected permit digest comes from the trusted controller CLI, never model
input. A hash is not a human signature: the root's single authoritative journal
and truthful prior conversation authorization remain trusted inputs. This module
neither starts a host nor grants device verification, API access, persistent MCP
approval or permissions outside the two named development tools.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time

HEX = re.compile(r'[a-f0-9]{64}\Z')
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_RUNTIME_BYTES = 64 * 1024 * 1024
MAX_RUNTIME_FILES = 4096
BATCH_ID = 'p1-20261128-approved-batch1'
KIND = 'p1_native_prior_chat_permit'
SCOPE = {'mode': 'prior_chat_authorization', 'host_auth': 'chatgpt',
         'mcp_server': 'memex', 'tools': ['run_current_tests', 'record_decision'],
         'api_access': False, 'persistent_grant': False}
MANDATORY = frozenset({
    'package.json', 'scripts/codex-retention-host.py',
    'scripts/paper1/native_live.py', 'scripts/paper1/native_smoke.py',
    'scripts/paper1/approvals.py', 'scripts/paper1/native_permit.py',
    'scripts/paper1/batch_limits.py', 'scripts/paper1/live_mcp.py',
    'scripts/paper1/live-broker.mjs', 'scripts/paper1/live-state.mjs',
    'scripts/paper1/normalize-node.mjs', 'scripts/paper1/archive.mjs',
    'scripts/paper1/claims.mjs', 'scripts/paper1/verification.mjs',
    'packages/memex-core/package.json', 'packages/memex-core/index.js',
})


class PermitError(ValueError):
    """Stable errors without source contents or credential values."""


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def fields(value, required):
    if not isinstance(value, dict) or set(value) != set(required):
        raise PermitError('permit_schema_fields')


def strict_json(data):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise PermitError('duplicate_json_key')
            result[key] = value
        return result
    def constant(_):
        raise PermitError('nonfinite_json')
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, PermitError):
            raise
        raise PermitError('invalid_permit_json') from exc


def _regular_bytes(path):
    path = Path(path)
    if path.is_symlink():
        raise PermitError('symlink_forbidden')
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except OSError as exc:
        raise PermitError('permit_file_unavailable') from exc
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            raise PermitError('unsafe_or_oversized_file')
        content = source.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise PermitError('oversized_file')
    return content


def _relative(value):
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+', value)
            or PurePosixPath(value).is_absolute()
            or any(p in ('', '.', '..') for p in value.split('/'))
            or PurePosixPath(value).as_posix() != value):
        raise PermitError('unsafe_runtime_path')
    return value


def _under(root, relative):
    relative = _relative(relative)
    cursor = root
    for part in relative.split('/'):
        cursor = cursor / part
        if cursor.is_symlink():
            raise PermitError('symlink_forbidden')
    return cursor


def _canonical_root(value):
    path = Path(value)
    if not path.is_absolute() or path.is_symlink():
        raise PermitError('absolute_regular_source_root_required')
    try:
        root = path.resolve(strict=True)
    except OSError as exc:
        raise PermitError('source_root_unavailable') from exc
    if not root.is_dir():
        raise PermitError('source_root_must_be_directory')
    # /var and /tmp are system aliases on macOS. Resolve trusted ancestors once;
    # subsequently reject symlinks inside the canonical runtime root.
    return root


def _runtime_paths(root):
    package = _under(root, 'packages/memex-core')
    if not package.is_dir():
        raise PermitError('memex_runtime_missing')
    paths = set(MANDATORY)
    for entry in package.rglob('*'):
        if entry.is_symlink():
            raise PermitError('symlink_forbidden')
        if entry.is_dir():
            continue
        if not entry.is_file():
            raise PermitError('nonregular_runtime_member')
        paths.add(entry.relative_to(root).as_posix())
        if len(paths) > MAX_RUNTIME_FILES:
            raise PermitError('too_many_runtime_files')
    return paths


def runtime_manifest(source_root):
    """Read-only helper for the trusted issuer; no permit or state is created."""
    root = _canonical_root(source_root)
    result, total = {}, 0
    for relative in sorted(_runtime_paths(root)):
        content = _regular_bytes(_under(root, relative))
        total += len(content)
        if total > MAX_RUNTIME_BYTES:
            raise PermitError('runtime_byte_limit')
        result[relative] = hashlib.sha256(content).hexdigest()
    return result


def _canonical_bound(value, *, must_exist=False):
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise PermitError('absolute_bound_path_required')
    p = Path(value)
    if p.is_symlink():
        raise PermitError('symlink_forbidden')
    try:
        canonical_path = p.resolve(strict=must_exist)
    except OSError as exc:
        raise PermitError('bound_path_unavailable') from exc
    # Permit text must already be canonical. Caller arguments may use an OS alias.
    if str(canonical_path) != value:
        raise PermitError('permit_bound_path_not_canonical')
    return canonical_path


def _reservation(value, authorization_sha256):
    fields(value, {'seq', 'previous_sha256', 'authorization_sha256', 'at_unix_ns', 'event', 'data', 'sha256'})
    if (type(value['seq']) is not int or value['seq'] < 1
            or not HEX.fullmatch(str(value['previous_sha256']))
            or value['authorization_sha256'] != authorization_sha256
            or type(value['at_unix_ns']) is not int or value['at_unix_ns'] <= 0
            or value['event'] != 'reserved'
            or not HEX.fullmatch(str(value['sha256']))
            or value['sha256'] != digest({k: v for k, v in value.items() if k != 'sha256'})):
        raise PermitError('invalid_reservation_event')
    data = value['data']
    fields(data, {'attempt_id', 'kind', 'unit_key', 'public_sha256', 'upper_bound_fen', 'billing_basis', 'wall_seconds'})
    if (not isinstance(data['attempt_id'], str) or not LABEL.fullmatch(data['attempt_id'])
            or data['kind'] != 'native' or data['unit_key'] is not None or data['public_sha256'] is not None
            or type(data['wall_seconds']) is not int or data['wall_seconds'] != 600
            or type(data['upper_bound_fen']) is not int or data['upper_bound_fen'] != 0):
        raise PermitError('reservation_outside_native_subscription_scope')
    basis = data['billing_basis']
    fields(basis, {'kind', 'evidence'})
    fields(basis['evidence'], {'ref', 'sha256'})
    if (basis['kind'] != 'included_subscription'
            or not HEX.fullmatch(str(basis['evidence']['sha256']))):
        raise PermitError('subscription_basis_required')
    _relative(basis['evidence']['ref'])
    return data['attempt_id']


def _deadline(permit, wall_seconds, now):
    issued, expires = permit['issued_at_unix_ns'], permit['expires_at_unix_ns']
    reserved = permit['reservation']['at_unix_ns']
    if (type(issued) is not int or type(expires) is not int
            or not reserved <= issued <= now < expires <= reserved + 600 * 10**9
            or now + wall_seconds * 10**9 > expires):
        raise PermitError('permit_expired_or_duration_not_covered')


def admit_permit(path, expected_sha256, *, output, model, wall_seconds, source_root, consume=False):
    """Return exactly three grant references after complete admission.

    consume=True atomically creates a one-use marker before host start. On any
    earlier rejection no file is created. No call attests a human interaction.
    A consumed permit cannot be retried or moved to another root/output.
    """
    if (not isinstance(expected_sha256, str) or not HEX.fullmatch(expected_sha256)
            or type(consume) is not bool or type(wall_seconds) is not int
            or not 1 <= wall_seconds <= 600
            or not isinstance(model, str) or not LABEL.fullmatch(model)):
        raise PermitError('invalid_trusted_controller_arguments')
    supplied_path = Path(path)
    if not supplied_path.is_absolute() or supplied_path.is_symlink():
        raise PermitError('absolute_regular_permit_path_required')
    try:
        permit_path = supplied_path.resolve(strict=True)
    except OSError as exc:
        raise PermitError('permit_file_unavailable') from exc
    raw = _regular_bytes(permit_path)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise PermitError('permit_hash_mismatch')
    permit = strict_json(raw)
    fields(permit, {'schema_version', 'kind', 'batch_id', 'permit_path', 'source_root',
                   'authorization_file', 'authorization_sha256', 'reservation', 'output', 'model',
                   'wall_seconds', 'issued_at_unix_ns', 'expires_at_unix_ns', 'runtime_sha256', 'scope'})
    if (type(permit['schema_version']) is not int or permit['schema_version'] != 1
            or permit['kind'] != KIND or permit['batch_id'] != BATCH_ID
            or permit['scope'] != SCOPE
            or permit['scope'].get('api_access') is not False
            or permit['scope'].get('persistent_grant') is not False):
        raise PermitError('unsupported_permit_scope')
    root = _canonical_root(source_root)
    if (_canonical_bound(permit['permit_path'], must_exist=True) != permit_path
            or _canonical_bound(permit['source_root'], must_exist=True) != root):
        raise PermitError('permit_location_mismatch')
    output_path = Path(output)
    if not output_path.is_absolute() or output_path.is_symlink():
        raise PermitError('absolute_new_output_required')
    if (_canonical_bound(permit['output']) != output_path.resolve()
            or output_path.exists()):
        raise PermitError('output_mismatch_or_already_exists')
    if (permit['model'] != model or type(permit['wall_seconds']) is not int
            or permit['wall_seconds'] != wall_seconds):
        raise PermitError('model_or_duration_mismatch')
    if (permit['authorization_file'] != 'authorization.json'
            or not HEX.fullmatch(str(permit['authorization_sha256']))):
        raise PermitError('adjacent_authorization_required')
    authorization_path = permit_path.parent / 'authorization.json'
    auth_raw = _regular_bytes(authorization_path)
    if hashlib.sha256(auth_raw).hexdigest() != permit['authorization_sha256']:
        raise PermitError('authorization_hash_mismatch')
    attempt_id = _reservation(permit['reservation'], permit['authorization_sha256'])
    _deadline(permit, wall_seconds, time.time_ns())
    manifest = permit['runtime_sha256']
    if not isinstance(manifest, dict) or set(manifest) != _runtime_paths(root):
        raise PermitError('runtime_manifest_coverage_mismatch')
    verified = {}
    total = 0
    for relative, expected in manifest.items():
        if not isinstance(expected, str) or not HEX.fullmatch(expected):
            raise PermitError('invalid_runtime_digest')
        content = _regular_bytes(_under(root, relative))
        total += len(content)
        if total > MAX_RUNTIME_BYTES:
            raise PermitError('runtime_byte_limit')
        if hashlib.sha256(content).hexdigest() != expected:
            raise PermitError('runtime_hash_mismatch')
        if relative == 'scripts/paper1/batch_limits.py':
            verified[relative] = content
    # Execute only the already hash-verified local validator. Its __main__ does
    # not run; no journal, provider or credential operation occurs here.
    name = 'scripts/paper1/batch_limits.py'
    namespace = {'__file__': str(root / name), '__name__': '_p1_permit_authorization_validator'}
    try:
        exec(compile(verified[name], str(root / name), 'exec'), namespace)
        namespace['validate_authorization'](strict_json(auth_raw))
    except Exception as exc:
        raise PermitError('invalid_batch_authorization') from exc
    reference = {'authorization_sha256': permit['authorization_sha256'], 'attempt_id': attempt_id,
                 'reservation_sha256': permit['reservation']['sha256']}
    marker = permit_path.with_name(permit_path.name + '.consumed.json')
    if marker.exists() or marker.is_symlink():
        raise PermitError('permit_already_consumed')
    _deadline(permit, wall_seconds, time.time_ns())
    if consume:
        receipt = {'schema_version': 1, 'kind': 'p1_native_permit_consumption',
                   'permit_sha256': expected_sha256, 'grant_reference': reference,
                   'consumed_at_unix_ns': time.time_ns(), 'output': permit['output'], 'model': model,
                   'source': 'trusted_controller_prior_chat_authorization',
                   'human_presence_attested': False, 'device_verification_attested': False}
        try:
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        except FileExistsError as exc:
            raise PermitError('permit_already_consumed') from exc
        except OSError as exc:
            raise PermitError('permit_consumption_unavailable') from exc
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as destination:
                destination.write(canonical(receipt) + '\n')
                destination.flush()
                os.fsync(destination.fileno())
            directory = os.open(marker.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError as exc:
            # Keep any marker after uncertain persistence. A retry may not start
            # the host simply because the first controller lost its response.
            raise PermitError('permit_consumption_persistence_uncertain') from exc
    return reference
