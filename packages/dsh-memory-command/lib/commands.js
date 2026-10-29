/**
 * Human-facing `/memory` command for the extra-context memory subsystem.
 *
 * Commands are user-owned controls over the same store the model uses:
 * inspect capacity, search and read record cards, pin/unpin, forget, and write
 * a durable note without involving the model. They resolve identity from the
 * invoking agent's session, so they always operate on the caller's workspace.
 *
 * @module @qiuxu/dsh-memory-command/commands
 */
import { memoryCaptureScope, memoryVisibleScopes, memoryWorkspaceKey } from '@qiuxu/dsh-memory-seam'

/** Command description lines shown by the command palette. */
const DESCRIPTIONS = {
  status: 'Show memory archive capacity and record counts',
  search: 'Search memory records and print matching cards',
  pin: 'Pin one memory record so it stays in the model catalog',
  unpin: 'Unpin one memory record',
  forget: 'Delete one memory record permanently',
  remember: 'Write a durable note: /memory remember <title> :: <body>',
}

/** Resolve the caller's workspace scope from a command invocation. */
function scopeOf(invocation) {
  const agent = invocation?.agent
  const cwd = agent?.session?.header?.cwd
  const sessionId = agent?.session?.id
  return {
    workspaceKey: memoryWorkspaceKey(cwd, sessionId),
    workspace: typeof cwd === 'string' ? cwd : '',
    sessionId: typeof sessionId === 'string' ? sessionId : '',
  }
}

/** Format one card line for human output. */
function cardLine(card) {
  const when = card.useWhen.length > 0 ? `\n    when: ${card.useWhen}` : ''
  return `- ${card.id} [${card.kind}/${card.status}] ${card.title}${when}`
}

/**
 * Resolve the caller's enabled cache levels.
 * @param {object} memory - The `ctx.memory` service.
 * @param {object} invocation - Command invocation.
 * @returns {Promise<{levels: {l2: boolean, l3: boolean}, sessionId: string}>} Levels.
 */
async function levelsOf(memory, invocation) {
  const scope = scopeOf(invocation)
  let levels = { l2: false, l3: false }
  try {
    levels = await memory.getLevels(scope.sessionId)
  } catch {
    levels = { l2: false, l3: false }
  }
  return { levels, sessionId: scope.sessionId }
}

/** Human label for one enabled-level set. */
function levelLabel(levels) {
  if (levels.l2 === true && levels.l3 === true) return 'L2 (session) + L3 (workspace), both sticky'
  return levels.l3 === true ? 'L3 (workspace-shared), sticky' : 'L2 (session-private), sticky'
}

/**
 * Load a record only when it belongs to the caller's enabled levels.
 * @param {object} memory - The `ctx.memory` service.
 * @param {object} scope - Caller workspace scope.
 * @param {{l2: boolean, l3: boolean}} levels - Enabled levels.
 * @param {string} id - Record id.
 * @returns {Promise<object|undefined>} The record when visible.
 */
async function visibleRecord(memory, scope, levels, id) {
  const record = await memory.get(id)
  if (record === undefined) return undefined
  if (record.workspaceKey !== scope.workspaceKey) return undefined
  if (record.scope === 'workspace') return levels.l3 === true ? record : undefined
  if (record.scope === 'session') return levels.l2 === true && record.sessionId === scope.sessionId ? record : undefined
  return undefined
}

/**
 * Register the `/memory` command on one memory service context.
 *
 * @param {import('@deepseek-ai/cordis').Context} ctx - Owning context.
 * @param {import('./seam.js').MemoryStore} memory - The `ctx.memory` service.
 * @returns {(() => void) | undefined} Disposer, or undefined when no command registry is composed.
 */
export function registerMemoryCommands(ctx, memory) {
  let commands
  try {
    commands = ctx.get('commands')
  } catch {
    return undefined
  }
  if (commands === undefined) return undefined

  return commands.register({
    definitionId: '@qiuxu/dsh-memory/commands/memory',
    name: 'memory',
    description: 'Inspect and control the extra-context cache levels: on l2|l3|both, status, search, pin, unpin, forget, remember. Levels are sticky and cannot be switched off.',
    input: { hint: 'on l2|l3|both | status | compress [l2|l3] [targetRatio] | search <terms> | pin <id> | unpin <id> | forget <id> | remember <title> :: <body> | restore <id> | gc <keepTokens>' },
    handler: async (invocation) => {
      const raw = String(invocation.rawInput ?? '').trim()
      const [verb = 'status'] = raw.length === 0 ? ['status'] : raw.split(/\s+/)
      const argument = raw.slice(raw.indexOf(verb) + verb.length).trim()
      const scope = scopeOf(invocation)
      switch (verb) {
        case 'status': {
          const state = await levelsOf(memory, invocation)
          const workspace = await memory.facets({ workspaceKey: scope.workspaceKey, scope: 'workspace' })
          const session = await memory.facets({ workspaceKey: scope.workspaceKey, scope: 'session', sessionId: scope.sessionId })
          const evictions = await memory.evictionStats(scope.sessionId)
          const history = await memory.compressionStats(scope.sessionId, 3)
          const historyLine = history.count === 0
            ? 'Compression runs: 0'
            : `Compression runs: ${history.count}; last ${history.last.strategy} ${history.last.level} ${new Date(history.last.createdAt).toISOString()} (hot ${history.last.beforeHot} → ${history.last.afterHot}, cold ${history.last.coldMoved}, digests ${history.last.digests})`
          const lines = [
            'Cache levels: L1 = model context window; L2 = session-private archive; L3 = workspace-shared archive.',
            `L2: ${state.levels.l2 ? 'ON (sticky)' : 'off'} — ${session.hotCount ?? session.count} hot / ${session.coldCount ?? 0} cold records, ~${session.hotTokens ?? session.tokens} hot + ${session.coldTokens ?? 0} cold / ${session.sessionCapacityTokens ?? 10_000_000} capacity tokens.`,
            `L3: ${state.levels.l3 ? 'ON (sticky)' : 'off'} — ${workspace.hotCount ?? workspace.count} hot / ${workspace.coldCount ?? 0} cold records, ~${workspace.hotTokens ?? workspace.tokens} hot + ${workspace.coldTokens ?? 0} cold / ${workspace.capacityTokens ?? 100_000_000} capacity tokens.`,
            `L1 evicted to L2/L3: ${evictions.count} batches, ~${evictions.tokens} tokens.`,
            historyLine,
            `Store: ${memory.root ?? '(configured by the backend)'}`,
          ]
          return { kind: 'success', text: lines.join('\n') }
        }
        case 'on': {
          const requested = argument.length === 0 ? 'both' : argument
          if (requested !== 'l2' && requested !== 'l3' && requested !== 'both') {
            return { kind: 'error', text: 'Usage: /memory on l2|l3|both (L2 and L3 are sticky: once on they cannot be switched off)' }
          }
          const before = await memory.getLevels(scope.sessionId)
          if (requested === 'l2' || requested === 'both') await memory.enableLevel(scope.sessionId, 'l2')
          if (requested === 'l3' || requested === 'both') await memory.enableLevel(scope.sessionId, 'l3')
          const after = await memory.getLevels(scope.sessionId)
          const changed = (requested === 'l2' && !before.l2) || (requested === 'l3' && !before.l3) || (requested === 'both' && (!before.l2 || !before.l3))
          return { kind: 'success', text: `${changed ? 'Enabled' : 'Already enabled'}: ${levelLabel(after)}. Sticky — cannot be disabled.` }
        }
        case 'off': {
          return { kind: 'error', text: 'L2/L3 are sticky: once enabled they cannot be switched off. Nothing was changed.' }
        }
        case 'search': {
          if (argument.length === 0) return { kind: 'error', text: 'Usage: /memory search <terms>' }
          const state = await levelsOf(memory, invocation)
          if (state.levels.l2 !== true && state.levels.l3 !== true) return { kind: 'error', text: 'Extra context is off for this session. Use /memory on l2|l3 first.' }
          const filter = { workspaceKey: scope.workspaceKey, scopes: memoryVisibleScopes(state.levels), sessionId: scope.sessionId }
          const { hits } = await memory.search({ ...filter, query: argument, limit: 8 })
          if (hits.length === 0) return { kind: 'success', text: `No memory records match "${argument}".` }
          return { kind: 'success', text: `${hits.length} records match "${argument}":\n${hits.map(cardLine).join('\n')}` }
        }
        case 'pin':
        case 'unpin': {
          if (argument.length === 0) return { kind: 'error', text: `Usage: /memory ${verb} <id>` }
          const state = await levelsOf(memory, invocation)
          if (state.levels.l2 !== true && state.levels.l3 !== true) return { kind: 'error', text: 'Extra context is off for this session. Use /memory on l2|l3 first.' }
          const record = await visibleRecord(memory, scope, state.levels, argument)
          if (record === undefined) return { kind: 'error', text: `No memory record with id "${argument}" in the enabled extra-context levels.` }
          const updated = await memory.setStatus(argument, verb === 'pin' ? 'pinned' : 'active')
          return { kind: 'success', text: `${verb === 'pin' ? 'Pinned' : 'Unpinned'} ${updated.id} · ${updated.title}` }
        }
        case 'compress': {
          const [levelArg, ratioArg] = argument.split(/\s+/).filter((part) => part.length > 0)
          const ratio = Number(ratioArg)
          const targetRatio = Number.isFinite(ratio) ? Math.min(Math.max(ratio, 0.1), 0.95) : 0.6
          const state = await levelsOf(memory, invocation)
          if (state.levels.l2 !== true && state.levels.l3 !== true) return { kind: 'error', text: 'Extra context is off for this session. Use /memory on l2|l3 first.' }
          const requested = levelArg === 'l2' || levelArg === 'l3' ? [levelArg] : ['l2', 'l3'].filter((candidate) => state.levels[candidate] === true)
          const lines = []
          for (const candidate of requested) {
            if (state.levels[candidate] !== true) return { kind: 'error', text: `${candidate.toUpperCase()} is not enabled for this session.` }
            const levelScope = candidate === 'l2' ? 'session' : 'workspace'
            const filter = { workspaceKey: scope.workspaceKey, scope: levelScope, ...levelScope === 'session' ? { sessionId: scope.sessionId } : {} }
            const result = await memory.compressCold({ ...filter, targetRatio, minAgeMs: 60 * 60 * 1000 })
            const after = await memory.facets(filter)
            await memory.recordCompression({
              sessionId: scope.sessionId,
              level: candidate,
              strategy: 'cold',
              beforeHot: result.before.hot,
              afterHot: Number(after.hotTokens ?? after.tokens) || 0,
              coldMoved: result.coldMoved.length,
              digests: 0,
              llmCalls: 0,
              errors: [],
            })
            lines.push(`${candidate.toUpperCase()}: moved ${result.coldMoved.length} records cold, freed ${result.freedTokens} tokens (target ${result.targetTokens})`)
          }
          return { kind: 'success', text: `Compressed (lossless cold, target ${targetRatio}):\n${lines.join('\n')}` }
        }
        case 'restore': {
          if (argument.length === 0) return { kind: 'error', text: 'Usage: /memory restore <id>' }
          const state = await levelsOf(memory, invocation)
          if (state.levels.l2 !== true && state.levels.l3 !== true) return { kind: 'error', text: 'Extra context is off for this session. Use /memory on l2|l3 first.' }
          const record = await visibleRecord(memory, scope, state.levels, argument)
          if (record === undefined) return { kind: 'error', text: `No memory record with id "${argument}" in the enabled extra-context levels.` }
          if (record.cold !== true) return { kind: 'error', text: `Record ${argument} is already hot.` }
          const restored = await memory.restoreCold(argument)
          return { kind: 'success', text: `Restored ${restored.id} "${restored.title}" (~${restored.tokens} tokens) back into the hot pool.` }
        }
        case 'gc': {
          const keep = Number(argument)
          if (!Number.isFinite(keep) || keep < 0) return { kind: 'error', text: 'Usage: /memory gc <keepTokens> — deletes oldest cold records above this token budget' }
          const state = await levelsOf(memory, invocation)
          if (state.levels.l2 !== true && state.levels.l3 !== true) return { kind: 'error', text: 'Extra context is off for this session. Use /memory on l2|l3 first.' }
          const reports = []
          if (state.levels.l2 === true) {
            const result = await memory.gcCold({ workspaceKey: scope.workspaceKey, scope: 'session', sessionId: scope.sessionId, keepTokens: keep })
            reports.push(`L2 removed ${result.removed.length} (~${result.freedTokens} tokens)`)
          }
          if (state.levels.l3 === true) {
            const result = await memory.gcCold({ workspaceKey: scope.workspaceKey, scope: 'workspace', keepTokens: keep })
            reports.push(`L3 removed ${result.removed.length} (~${result.freedTokens} tokens)`)
          }
          return { kind: 'success', text: `Cold GC (keep ≤ ${keep} tokens): ${reports.join('; ')}.` }
        }
        case 'forget': {
          if (argument.length === 0) return { kind: 'error', text: 'Usage: /memory forget <id>' }
          const state = await levelsOf(memory, invocation)
          if (state.levels.l2 !== true && state.levels.l3 !== true) return { kind: 'error', text: 'Extra context is off for this session. Use /memory on l2|l3 first.' }
          const record = await visibleRecord(memory, scope, state.levels, argument)
          if (record === undefined) return { kind: 'error', text: `No memory record with id "${argument}" in the enabled extra-context levels.` }
          await memory.forget(argument)
          return { kind: 'success', text: `Forgot memory record ${argument}.` }
        }
        case 'remember': {
          const state = await levelsOf(memory, invocation)
          if (state.levels.l2 !== true && state.levels.l3 !== true) return { kind: 'error', text: 'Extra context is off for this session. Use /memory on l2|l3 first.' }
          const separator = argument.indexOf('::')
          if (separator < 0) return { kind: 'error', text: 'Usage: /memory remember <title> :: <body>' }
          const title = argument.slice(0, separator).trim()
          const body = argument.slice(separator + 2).trim()
          if (title.length === 0 || body.length === 0) return { kind: 'error', text: 'Usage: /memory remember <title> :: <body>' }
          const record = await memory.write({
            kind: 'fact',
            title,
            body,
            summary: body.split('\n')[0].slice(0, 200),
            useWhen: '',
            status: 'active',
            trust: 'trusted',
            scope: memoryCaptureScope(state.levels),
            workspace: scope.workspace,
            workspaceKey: scope.workspaceKey,
            sessionId: scope.sessionId,
            tags: { user: ['command', 'note'] },
            provenance: { source: 'command', sessionId: scope.sessionId },
          })
          return { kind: 'success', text: `Saved ${record.id} "${record.title}" (~${record.tokens} tokens).` }
        }
        default:
          return { kind: 'error', text: `Unknown /memory subcommand "${verb}".\n${Object.entries(DESCRIPTIONS).map(([name, text]) => `  ${name} — ${text}`).join('\n')}` }
      }
    },
  })
}
