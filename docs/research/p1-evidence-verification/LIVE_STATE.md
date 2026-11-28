# Live workspace artifact binding

Updated: 2026-11-28. **Engineering component, not a paper result.**

`scripts/paper1/live-state.mjs` adds bounded observations of explicitly declared public files to the existing evidence verifier. It does not invoke a model, execute a command, select task answers, or replace the archive's source-completeness contract. The current supported decision is **the state of a test execution as applied to the current workspace**. Historical questions must use a different interface and must not be silently retargeted.

## Stable interface

```js
await captureWorkspace({ root, files, environment, limits })
bindObservedClaim(claim, snapshot, { target: 'current_workspace' })
bindExecutionSource(source, { before, after })
withLiveState(archive, configuration)
```

The wrapper additionally exposes `await adapter.bindClaim(claim, { target: 'current_workspace' })` and a read-only snapshot of cumulative counters at `adapter.metrics`. It delegates `search`, `open`, and an existing `countTokens` method. The caller owns and closes the original archive.

### 1. Capture a workspace

```js
const configuration = {
  root: canonicalAbsoluteWorkspace,
  files: ['sum.mjs', 'sum.test.mjs'],
  environment: {
    cwd: '.',
    lockfiles: [],
    values: { NODE_ENV: 'test' },
  },
}
const snapshot = await captureWorkspace(configuration)
```

`root` must already be an absolute, canonical directory path. Resolve a trusted workspace boundary when establishing the host session; do not normalize an untrusted request into a broader allowed root. Relative artifact and lockfile paths must already be canonical. Absolute paths, `.`/`..` file components, doubled separators, backslashes, and observed symlink components are rejected. A declared file must be a regular file; directories and other special files are not treated as file contents. The Node runtime must support `O_NOFOLLOW`.

`files` is a nonempty, explicit list of public artifact files. `environment.lockfiles` is an explicit list of required lockfiles; a missing declared lockfile produces a failed observation, not an assumed empty dependency set. A path appearing in both lists is read once per pass with both roles. Duplicate paths within one list are rejected. No file globbing or semantic dependency inference occurs.

`environment.cwd` is a canonical directory relative to `root`, with `.` denoting the root itself. The observer checks that it exists inside the boundary. This is a **declared execution directory identity**, not proof that a remote command used that directory. `nodeVersion`, `platform`, and `arch` come from the actual observing Node process and cannot be overridden through `environment`. The controller must execute the tested command under that same runtime and declared directory. `values` contains only explicitly supplied public scalar configuration; the module does not read arbitrary environment variables, credentials, or `.env` files.

A successful observation has this shape:

```js
{
  ok: true,
  schema: 1,
  policy: 'p1-live-workspace-v1',
  version: '<sha256 of the public content/environment manifest>',
  rootIdentity: '<local boundary identity digest>',
  manifest: {
    schema: 1,
    policy: 'p1-live-workspace-v1',
    environment: { cwd, nodeVersion, platform, arch, values },
    files: [{ path, roles, bytes, sha256, mode }],
    directories: [{ path, entryCount, membershipDigest }],
  },
  observation: { passes: 2, changeGuard, filesRead, bytesRead, directoryReads },
}
```

`version` is the digest of the entire manifest, **not the digest of one source file**. Files and directory members are sorted by JavaScript code-unit order, independent of the machine's collation locale. Mtime is not used as a substitute for content hashing. A content change with restored mtime still changes the version. Node version, working-directory identity, declared environment values, artifact contents, modes, and declared lockfile contents participate in that version.

The module also records directory membership digests for the root, artifact-path ancestors, and declared working-directory ancestors. Adding or deleting a direct member in those observed directories conservatively changes the version. It hashes the names and kinds of those members without reading unlisted file contents. This **does not observe edits inside unlisted files or recursively cover unlisted directories**. The host remains responsible for selecting the dependency scope. Directory membership is not a substitute for declaring every relevant input file.

Each capture performs two bounded file-content passes. Each file uses a no-follow file handle, regular-file checks, and comparisons of pathname/descriptor identity and metadata before and after reading. Directory membership and metadata are checked before and after each pass. The two passes must agree. `changeGuard` additionally summarizes observed device/inode identity, size, mode, and nanosecond mtime/ctime metadata. It can reject an observed change-and-restoration across an execution or view-read boundary even when the content version has returned to its previous value. Root identity is bound separately from the portable content manifest; it is intentionally local to the canonical workspace boundary.

A failure returns `{ ok: false, version: null, reason, observation }`, optionally with a relative `path`. Examples include `file_missing`, `symlink`, `noncanonical_path`, `unsupported_file`, `unsupported_environment`, `workspace_changed`, and budget errors. Failed observations never return a usable fallback version. Do not substitute an earlier snapshot, a model-proposed version, or a controller's expected answer.

### 2. Bind a current-workspace claim

```js
const bound = bindObservedClaim(proposal, snapshot, {
  target: 'current_workspace',
})
```

This supports only `test_result` claims. It replaces `version` with the observed composite version, retains the original value as `proposedVersion`, and records `versionBinding.source = 'live_workspace_snapshot'`, the explicit target, policy, version, and root identity. It does not modify the input object or fill an unknown entity, scope, principal, or action.

The explicit target is mandatory. An explicit `asOf`, `historicalAt`, historical flag, or incompatible target is rejected. The caller must also establish the user's temporal intent; the module cannot infer whether unrestricted natural-language text is a historical question. Passing `target: 'current_workspace'` to a historical request is a caller error, not an authorized reinterpretation.

Snapshots received across a process boundary must come through the trusted host-observer transport. A recomputable hash checks consistency, **not producer authenticity**. The wrapper therefore observes the actual workspace again at every verification view read. No evaluator labels or gold source locations are accepted or needed by these APIs.

### 3. Bind an execution source

The host's required sequence is:

```js
const before = await captureWorkspace(configuration)
// Abort or mark unresolved if before.ok is false.
const event = await trustedHostExecuteInDeclaredDirectory()
const after = await captureWorkspace(configuration)
// Abort or mark unresolved if after.ok is false.

const parsed = normalizeNodeTestEvent(event, {
  threadId,
  scope,
  sourceSequence,
  observedAt: actualTerminalEventUtc,
  nodeExecutable: process.execPath,
  artifactBefore: before.version,
  artifactAfter: after.version,
})
// Do not ingest a null/unparsed source as a complete execution receipt.
const source = bindExecutionSource(parsed.source, { before, after })
archive.ingest([source])
// Assert synchronization only when the host really has no known ingestion gap.
archive.setSynchronized(true)
```

The helper requires two successful observations with equal content versions, root identities, and change guards. It also requires the normalized `source.version` to equal that observed version. It cannot relabel a receipt for an unrelated version. It rejects a detected execution-boundary change with `execution_state_changed`, a wrong source version with `source_version_mismatch`, and an unavailable observation with `capture_unavailable`.

The helper adds its public record under `source.transport.liveState`, retaining existing transport metadata. This includes the manifest, policy, before/after versions, before/after change guards, and root identity. No private evaluator field is added. The existing Raw-RAG public archive schema permits this nested `transport` metadata, so the same source can be supplied to both arms. The command's actual success/failure semantics still belong to the normalizer and verifier; a live binding does not turn `failed` into `passed`.

### 4. Verify through a live wrapper

```js
const adapter = withLiveState(archive, configuration)
const claim = await adapter.bindClaim(proposal, {
  target: 'current_workspace',
})
const result = await verifyEvidence({ claim, now, cached }, adapter)
```

Before every underlying `readView`, the wrapper captures the live state. After the archive work it captures again. It adds the stable policy/version/root/change-guard summary to the returned view. A missing observation, unbound claim, current-version mismatch, detected race, or unbound execution source sets `complete: false` with a diagnostic `bindingIssue`. The existing verifier then abstains; its usual outer reason is `incomplete_view` or `view_changed`, with the specific issue in the trace. An archive error remains an error rather than an invented archive watermark.

Because the verifier compares whole views, a live file change invalidates its previous receipt even if the archive catalog watermark did not change. Rebinding a claim to the new current version still does not make an old source qualify: the existing verifier's version comparison rejects that old source.

For every newly encountered head, the wrapper first performs a bounded real search/open and validates all committed head sources' execution-binding records. A single private cache entry records a validated head commitment and root identity. This prevents the verifier's cache shortcut from bypassing the execution-binding requirement, including for receipts originally obtained from an unwrapped archive. Unknown or incompletely opened heads remain unresolved. The wrapper never rewrites the archive catalog, source hashes, or verifier policy.

## Bounds and cost accounting

Default capture limits, overridable within fixed hard caps, are:

| Limit | Default | Hard cap |
|---|---:|---:|
| Distinct artifact/lockfile paths | 64 | 256 |
| Bytes in one file | 4 MiB | 16 MiB |
| Total file bytes per pass | 16 MiB | 64 MiB |
| Directory members per directory scan set | 4,096 | 16,384 |
| Explicit public environment JSON | 4 KiB | 16 KiB |

There are two content passes per capture and two captures per wrapper view read. The explicit path length is bounded, and all metadata traversal is restricted to the declared paths and their ancestors. This is not a zero-I/O cache path.

`withLiveState` also accepts `maxBindingSources` (default 64; hard cap 256) and `maxBindingBytes` (default 1 MiB; hard cap 4 MiB). Those bound its head-binding validation. The underlying archive must itself bound each `open` operation; the wrapper can check a returned source's byte size only after that open has completed.

`adapter.metrics` reports captures, files read, bytes read, directory reads, view reads, head-binding searches/opens/bytes, and delegated searches/opens. Failed attempts remain counted. The existing verifier's counters already include its ordinary delegated calls; do not double-count those when adding wrapper-only work. No tokenizer, latency benefit, or total-cost improvement is inferred from fewer original opens.

## Limits of the guarantee

- Equal observations do not establish an atomic filesystem snapshot. There is no filesystem transaction, process-wide execution lock, or OS sandbox installed by this module. A mutation after the final read is outside that read's guarantee. Mutations that happen and disappear entirely between observations can evade detection.
- No-follow opens, canonical path checks, identity checks, and repeated reads reject observed symlinks, escapes, and races. They are not a proof against a malicious process racing every intermediate path lookup. A hostile writable filesystem requires an OS-enforced boundary or locking facility beyond this standard-library component.
- Environment coverage is declared and bounded. External services, undeclared files, an alternative Node binary selected by a remote shell, and unobserved dependency state remain outside the fingerprint. The host must align execution with the observed runtime and directory.
- The observer and execution metadata must come from the trusted controller. Hashing cannot authenticate a fabricated log or a fabricated pair of observations supplied by another producer.
- The archive still uses its trusted complete-state-snapshot contract. This module does not establish general natural-language lifecycle completeness, resolve historical authorization, or guarantee that a model consumes delivered evidence correctly.
- Retrieval can still miss an otherwise valid source. An integration probe using the actual full Node executable path in the command/entity produced no hits for the full claim query, although shorter queries found the same record. The unwrapped archive verifier also abstained (`head_not_opened`); the live wrapper abstained earlier (`binding_head_incomplete`). This is an observed retrieval limitation, not permission to rewrite the actual command, invent a source locator, or treat a missing head as complete.
- Keep archive stores, reports, temporary outputs, and host logs **outside the observed workspace**. Otherwise their creation can correctly invalidate the directory-membership observation itself.

## Verification record

The implementation followed red/green cycles: seven capture tests first failed for absent behavior, six binding/wrapper tests then failed for absent binding APIs, and two targeted tests exposed acceptance of a detected change-and-restoration plus locale-dependent ordering. The corresponding implementations made each group pass. Tests use real temporary files and real Memex L2 storage. Narrow timing controls mutate actual files during actual reads; no fake filesystem result is substituted.

```bash
node --test test/paper1-live-state.mjs
npm test
```

Verification on 2026-11-28:

| Check | Observed result |
|---|---|
| Focused live-state suite | 15 tests passed. |
| Existing project command `npm test` | Exit 0; runner reported 197/197 passed, with 4 skipped because the bundle was not built. This command is separate from `npm run test:paper1`. |
| Real Node execution and normalization | An actual Node v24.22.3 process completed an explicit TAP test command with exit 0; its unchanged stdout normalized to a passed execution source and received the live-state binding. |
| Public archive compatibility | The resulting source, including nested `transport.liveState`, passed `rawrag_adapter.validate_archive`. No Raw-RAG model inference was run. |
| End-to-end probe with the full executable path in the entity | Abstained due to the retrieval limitation above. This probe does not establish successful online host integration. |

The focused tests cover repeatable hashes, same-size content mutation with restored mtime, addition/deletion of a watched directory member, lockfile changes, unavailable files, canonical-path and symlink rejection, bounded reads, observed races, explicit current-workspace claim binding, execution-boundary change detection, actual L2 opens, and invalidation of cached evidence while the archive catalog remains unchanged. They are engineering validation, not model-performance or paired-arm experimental results.
