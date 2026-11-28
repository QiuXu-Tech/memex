/** Bounded observations of explicitly declared public workspace artifacts.
 * This is a repeated-read consistency check, not a filesystem transaction or
 * protection against an adversary racing path resolution without an OS lock.
 */
import fs from 'node:fs'
import { createHash } from 'node:crypto'
import { isAbsolute, join, posix, resolve } from 'node:path'
import { digest, headCommitment, validateClaim } from './verification.mjs'

export const LIVE_STATE_POLICY = 'p1-live-workspace-v1'
const DEFAULT_LIMITS = Object.freeze({ maxFiles: 64, maxFileBytes: 4_194_304,
  maxTotalBytes: 16_777_216, maxDirectoryEntries: 4096, maxEnvironmentBytes: 4096 })
const HARD_LIMITS = { maxFiles: 256, maxFileBytes: 16_777_216,
  maxTotalBytes: 67_108_864, maxDirectoryEntries: 16384, maxEnvironmentBytes: 16384 }
const own = (object, key) => Object.hasOwn(object, key)
const plain = object => object !== null && typeof object === 'object' && !Array.isArray(object)

export class LiveStateError extends Error {
  constructor(code, path) { super(code); this.name = 'LiveStateError'; this.code = code; if (path !== undefined) this.path = path }
}
const fail = (code, path) => { throw new LiveStateError(code, path) }
const fingerprint = stat => Object.fromEntries(['dev', 'ino', 'mode', 'size', 'mtimeNs', 'ctimeNs'].map(key => [key, String(stat[key])]))
const same = (a, b) => digest(a) === digest(b)
const lexical = (a, b) => a < b ? -1 : a > b ? 1 : 0

function relativePath(value, allowRoot = false) {
  if (allowRoot && value === '.') return value
  if (typeof value !== 'string' || !value || Buffer.byteLength(value) > 1024 || /[\\\0]/.test(value)
      || isAbsolute(value) || posix.normalize(value) !== value || value.endsWith('/')
      || value.split('/').some(part => !part || part === '.' || part === '..') || /^[A-Za-z]:/.test(value)) fail('noncanonical_path')
  return value
}

function configuration(options) {
  if (!plain(options) || typeof options.root !== 'string' || !isAbsolute(options.root)
      || resolve(options.root) !== options.root) fail('noncanonical_root')
  if (!Number.isInteger(fs.constants.O_NOFOLLOW) || fs.constants.O_NOFOLLOW === 0) fail('unsupported_platform')
  const limits = { ...DEFAULT_LIMITS, ...options.limits }
  if (!Object.keys(limits).every(key => own(HARD_LIMITS, key)
      && Number.isSafeInteger(limits[key]) && limits[key] > 0 && limits[key] <= HARD_LIMITS[key])) fail('invalid_limits')
  const environment = options.environment ?? {}
  if (!plain(environment) || Object.keys(environment).some(key => !['cwd', 'lockfiles', 'values'].includes(key))) fail('unsupported_environment')
  const cwd = relativePath(environment.cwd ?? '.', true)
  const values = environment.values ?? {}
  if (!plain(values) || Object.keys(values).some(key => !/^[A-Za-z0-9_.-]{1,64}$/.test(key)
      || !['string', 'number', 'boolean'].includes(typeof values[key])
      || (typeof values[key] === 'number' && !Number.isFinite(values[key])))) fail('unsupported_environment')
  if (Buffer.byteLength(JSON.stringify(values)) > limits.maxEnvironmentBytes) fail('environment_limit')
  const files = options.files
  const lockfiles = environment.lockfiles ?? []
  if (!Array.isArray(files) || !files.length || !Array.isArray(lockfiles)) fail('invalid_file_list')
  const entries = new Map()
  for (const [list, role] of [[files, 'artifact'], [lockfiles, 'lockfile']]) {
    if (new Set(list).size !== list.length) fail('duplicate_path')
    for (const item of list) {
      const path = relativePath(item)
      if (!entries.has(path)) entries.set(path, new Set())
      entries.get(path).add(role)
    }
  }
  if (entries.size > limits.maxFiles) fail('file_count_limit')
  const directories = new Set(['.'])
  for (const path of [...entries.keys(), `${cwd === '.' ? '' : cwd + '/'}placeholder`]) {
    let parent = posix.dirname(path)
    while (parent !== '.') { directories.add(parent); parent = posix.dirname(parent) }
  }
  return { root: options.root, limits, entries: [...entries].sort(([a], [b]) => lexical(a, b)),
    directories: [...directories].sort(), environment: { cwd, nodeVersion: process.version,
      platform: process.platform, arch: process.arch, values: Object.fromEntries(Object.keys(values).sort().map(key => [key, values[key]])) } }
}

async function inspect(root, relative, kind) {
  const parts = relative === '.' ? [] : relative.split('/')
  let absolute = root
  let stat
  for (let i = -1; i < parts.length; i++) {
    if (i >= 0) absolute = join(absolute, parts[i])
    try { stat = await fs.promises.lstat(absolute, { bigint: true }) }
    catch (error) { fail(error.code === 'ENOENT' ? 'file_missing' : 'file_unavailable', relative) }
    if (stat.isSymbolicLink()) fail('symlink', relative)
    if (i < parts.length - 1 || kind === 'directory') {
      if (!stat.isDirectory()) fail('unsupported_file', relative)
    } else if (!stat.isFile()) fail('unsupported_file', relative)
  }
  let real
  try { real = await fs.promises.realpath(absolute) } catch { fail('file_unavailable', relative) }
  if (real !== absolute) fail('noncanonical_path', relative)
  return stat
}

async function directoryView(config, metrics) {
  const directories = []
  const guards = []
  let count = 0
  for (const path of config.directories) {
    const before = fingerprint(await inspect(config.root, path, 'directory'))
    const entries = []
    const handle = await fs.promises.opendir(path === '.' ? config.root : join(config.root, path))
    metrics.directoryReads++
    for await (const entry of handle) {
      if (++count > config.limits.maxDirectoryEntries) fail('directory_entry_limit', path)
      const kind = entry.isSymbolicLink() ? 'symlink' : entry.isFile() ? 'file' : entry.isDirectory() ? 'directory' : 'other'
      entries.push([entry.name, kind])
    }
    const after = fingerprint(await inspect(config.root, path, 'directory'))
    if (!same(before, after)) fail('workspace_changed', path)
    entries.sort(([a], [b]) => lexical(a, b))
    directories.push({ path, entryCount: entries.length, membershipDigest: digest(entries) })
    guards.push([path, after])
  }
  return { directories, guards }
}

async function fileView(config, path, roles, remaining, metrics) {
  const before = await inspect(config.root, path, 'file')
  if (before.size > BigInt(config.limits.maxFileBytes) || before.size > BigInt(remaining)) fail('byte_limit', path)
  const absolute = join(config.root, path)
  let handle
  try {
    handle = await fs.promises.open(absolute, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK)
    const opened = await handle.stat({ bigint: true })
    if (!opened.isFile() || !same(fingerprint(before), fingerprint(opened))) fail('workspace_changed', path)
    metrics.filesRead++
    const size = Number(opened.size)
    let position = 0
    const hash = createHash('sha256')
    const buffer = Buffer.alloc(Math.min(65536, Math.max(1, size)))
    while (position < size) {
      const { bytesRead } = await handle.read(buffer, 0, Math.min(buffer.length, size - position), position)
      if (!bytesRead) fail('workspace_changed', path)
      position += bytesRead
      metrics.bytesRead += bytesRead
      hash.update(buffer.subarray(0, bytesRead))
    }
    const after = await handle.stat({ bigint: true })
    const pathAfter = await inspect(config.root, path, 'file')
    if (!same(fingerprint(before), fingerprint(after)) || !same(fingerprint(after), fingerprint(pathAfter))) fail('workspace_changed', path)
    return { file: { path, roles: [...roles].sort(), bytes: size, sha256: hash.digest('hex'),
      mode: Number(opened.mode & 0o777n) }, guard: fingerprint(after) }
  } catch (error) {
    if (error instanceof LiveStateError) throw error
    fail(error.code === 'ELOOP' ? 'symlink' : 'file_unavailable', path)
  } finally { if (handle) await handle.close() }
}

async function pass(config, metrics) {
  const start = await directoryView(config, metrics)
  const files = []
  const guards = []
  let total = 0
  for (const [path, roles] of config.entries) {
    const value = await fileView(config, path, roles, config.limits.maxTotalBytes - total, metrics)
    total += value.file.bytes
    files.push(value.file)
    guards.push([path, value.guard])
  }
  const end = await directoryView(config, metrics)
  if (!same(start, end)) fail('workspace_changed')
  return { manifest: { schema: 1, policy: LIVE_STATE_POLICY, environment: config.environment,
    files, directories: end.directories }, guards: { files: guards, directories: end.guards } }
}

/** Two full bounded passes; never returns a usable version for a failed capture. */
export async function captureWorkspace(options) {
  const metrics = { filesRead: 0, bytesRead: 0, directoryReads: 0 }
  try {
    const config = configuration(options)
    const root = await inspect(config.root, '.', 'directory')
    const rootIdentity = digest([config.root, String(root.dev), String(root.ino)])
    const first = await pass(config, metrics)
    const second = await pass(config, metrics)
    if (!same(first, second)) fail('workspace_changed')
    const finalRoot = await inspect(config.root, '.', 'directory')
    if (rootIdentity !== digest([config.root, String(finalRoot.dev), String(finalRoot.ino)])) fail('workspace_changed')
    return { ok: true, schema: 1, policy: LIVE_STATE_POLICY, version: digest(second.manifest),
      rootIdentity, manifest: second.manifest, observation: { passes: 2, changeGuard: digest(second.guards), ...metrics } }
  } catch (error) {
    return { ok: false, version: null, reason: error instanceof LiveStateError ? error.code : 'file_unavailable',
      ...(error instanceof LiveStateError && error.path !== undefined ? { path: error.path } : {}), observation: metrics }
  }
}

function validSnapshot(snapshot) {
  if (snapshot?.ok !== true) fail('capture_unavailable')
  if (snapshot.schema !== 1 || snapshot.policy !== LIVE_STATE_POLICY
      || !/^[a-f0-9]{64}$/.test(snapshot.version ?? '') || !/^[a-f0-9]{64}$/.test(snapshot.rootIdentity ?? '')
      || snapshot.manifest?.policy !== LIVE_STATE_POLICY || snapshot.observation?.passes !== 2
      || !/^[a-f0-9]{64}$/.test(snapshot.observation.changeGuard ?? '')
      || digest(snapshot.manifest) !== snapshot.version) fail('invalid_snapshot')
  return snapshot
}

/** Caller must establish that the request targets the current workspace.
 * Serialized snapshots must arrive through the trusted observer transport;
 * checking a content digest does not authenticate their producer.
 */
export function bindObservedClaim(claim, snapshot, { target } = {}) {
  if (target !== 'current_workspace') fail('current_workspace_target_required')
  if (claim && (own(claim, 'asOf') || own(claim, 'historicalAt') || claim.historical === true
      || (own(claim, 'target') && claim.target !== 'current_workspace'))) fail('historical_query')
  validateClaim(claim)
  if (claim.type !== 'test_result') fail('unsupported_claim_type')
  validSnapshot(snapshot)
  const proposedVersion = claim.versionBinding?.source === 'live_workspace_snapshot' && own(claim, 'proposedVersion')
    ? claim.proposedVersion : claim.version
  return { ...structuredClone(claim), proposedVersion, version: snapshot.version,
    versionBinding: { source: 'live_workspace_snapshot', target, policy: LIVE_STATE_POLICY,
      version: snapshot.version, rootIdentity: snapshot.rootIdentity } }
}

function executionBinding(source, rootIdentity) {
  const binding = source?.transport?.liveState
  if (!binding || binding.schema !== 1 || binding.policy !== LIVE_STATE_POLICY
      || source.type !== 'test_result' || source.kind !== 'command_execution' || source.role !== 'tool'
      || source.completed !== true || source.executed !== true
      || binding.beforeVersion !== source.version || binding.afterVersion !== source.version
      || !/^[a-f0-9]{64}$/.test(binding.beforeChangeGuard ?? '') || binding.beforeChangeGuard !== binding.afterChangeGuard
      || binding.version !== source.version || !/^[a-f0-9]{64}$/.test(source.version ?? '')
      || binding.rootIdentity !== rootIdentity || digest(binding.manifest) !== source.version) fail('unbound_execution_source')
  return binding
}

/** This records the observer's execution boundary; it does not execute a command. */
export function bindExecutionSource(source, { before, after } = {}) {
  validSnapshot(before)
  validSnapshot(after)
  if (before.version !== after.version || before.rootIdentity !== after.rootIdentity
      || before.observation.changeGuard !== after.observation.changeGuard) fail('execution_state_changed')
  if (source?.version !== before.version) fail('source_version_mismatch')
  if (source.type !== 'test_result' || source.kind !== 'command_execution' || source.role !== 'tool'
      || source.completed !== true || source.executed !== true) fail('unsupported_execution_source')
  if (source.transport !== undefined && !plain(source.transport)) fail('unsupported_transport')
  const liveState = { schema: 1, policy: LIVE_STATE_POLICY, version: before.version,
    beforeVersion: before.version, afterVersion: after.version, rootIdentity: before.rootIdentity,
    beforeChangeGuard: before.observation.changeGuard, afterChangeGuard: after.observation.changeGuard,
    manifest: structuredClone(before.manifest) }
  if (source.transport?.liveState && !same(source.transport.liveState, liveState)) fail('existing_binding_conflict')
  return { ...structuredClone(source), transport: { ...structuredClone(source.transport ?? {}), liveState } }
}

/** Adds live-state qualification without changing the archive or verifier API.
 * The first use of a new source head validates its execution binding through
 * actual bounded archive I/O. This also protects the verifier's cached path.
 * The caller owns and closes the underlying archive.
 */
export function withLiveState(archive, options) {
  if (!archive || !['readView', 'search', 'open'].every(key => typeof archive[key] === 'function')) fail('invalid_archive')
  const config = structuredClone(options)
  configuration(config)
  const maxBindingSources = config.maxBindingSources ?? 64
  const maxBindingBytes = config.maxBindingBytes ?? 1_048_576
  if (!Number.isSafeInteger(maxBindingSources) || maxBindingSources < 1 || maxBindingSources > 256
      || !Number.isSafeInteger(maxBindingBytes) || maxBindingBytes < 1 || maxBindingBytes > 4_194_304) fail('invalid_binding_limits')
  const metrics = { captures: 0, filesRead: 0, bytesRead: 0, directoryReads: 0, viewReads: 0,
    bindingSearches: 0, bindingOpens: 0, bindingBytes: 0, delegatedSearches: 0, delegatedOpens: 0 }
  let validatedHead = null
  let lastSnapshot = null
  const observe = async () => {
    const snapshot = await captureWorkspace(config)
    metrics.captures++
    for (const key of ['filesRead', 'bytesRead', 'directoryReads']) metrics[key] += snapshot.observation[key] ?? 0
    return snapshot
  }
  const validateHead = async (view, claim, snapshot) => {
    const key = digest([view.key, view.epoch, view.headCommitment, view.headEventCount, view.sourceId, snapshot.rootIdentity])
    if (validatedHead === key) return null
    if (!Number.isSafeInteger(view.headEventCount) || view.headEventCount < 1 || view.headEventCount > maxBindingSources) return 'binding_source_limit'
    try {
      metrics.bindingSearches++
      const hits = await archive.search({ type: claim.type, scope: claim.scope, entity: claim.entity,
        query: [claim.scope, claim.entity, claim.type].join(' '), limit: maxBindingSources })
      if (!Array.isArray(hits) || hits.length > maxBindingSources) return 'binding_source_limit'
      const opened = new Map()
      let bytes = 0
      for (const hit of hits) {
        metrics.bindingOpens++
        const source = await archive.open(hit)
        const size = Buffer.byteLength(JSON.stringify(source))
        metrics.bindingBytes += size
        bytes += size
        if (bytes > maxBindingBytes) return 'binding_byte_limit'
        if (source?.eventId !== hit.eventId || (hit.sourceDigest !== undefined && digest(source) !== hit.sourceDigest)) return 'binding_source_mismatch'
        if (source.sourceId === view.sourceId && source.sourceSequence === view.headSequence) opened.set(source.eventId, source)
      }
      const latest = [...opened.values()]
      if (latest.length !== view.headEventCount || headCommitment(latest) !== view.headCommitment) return 'binding_head_incomplete'
      for (const source of latest) executionBinding(source, snapshot.rootIdentity)
      validatedHead = key
      return null
    } catch (error) { return error instanceof LiveStateError ? error.code : 'execution_binding_unavailable' }
  }
  const adapter = {
    get metrics() { return { ...metrics } },
    async bindClaim(claim, bindingOptions) { return bindObservedClaim(claim, await observe(), bindingOptions) },
    async readView(claim) {
      metrics.viewReads++
      const before = await observe()
      const view = await archive.readView(claim)
      let issue = before.ok ? null : before.reason
      if (!issue && (claim.type !== 'test_result' || claim.versionBinding?.source !== 'live_workspace_snapshot'
          || claim.versionBinding.target !== 'current_workspace' || claim.versionBinding.policy !== LIVE_STATE_POLICY)) issue = 'unbound_current_claim'
      if (!issue && (claim.version !== before.version || claim.versionBinding.version !== before.version
          || claim.versionBinding.rootIdentity !== before.rootIdentity)) issue = 'claim_version_mismatch'
      if (!issue && view.complete === true) issue = await validateHead(view, claim, before)
      const after = await observe()
      if (!after.ok) issue = after.reason
      else if (before.ok && (before.version !== after.version || before.rootIdentity !== after.rootIdentity
          || before.observation.changeGuard !== after.observation.changeGuard)) issue = 'live_state_changed'
      lastSnapshot = after.ok ? after : null
      return { ...view, complete: view.complete === true && issue === null,
        liveBinding: { policy: LIVE_STATE_POLICY, version: after.ok ? after.version : null,
          rootIdentity: after.ok ? after.rootIdentity : null, changeGuard: after.ok ? after.observation.changeGuard : null },
        ...(issue ? { bindingIssue: issue } : {}) }
    },
    async search(input) { metrics.delegatedSearches++; return archive.search(input) },
    async open(hit) {
      metrics.delegatedOpens++
      const source = await archive.open(hit)
      if (!lastSnapshot) fail('live_view_required')
      executionBinding(source, lastSnapshot.rootIdentity)
      return source
    },
  }
  if (typeof archive.countTokens === 'function') adapter.countTokens = archive.countTokens.bind(archive)
  return adapter
}
