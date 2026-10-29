/**
 * Extra-context panel — browser half of the context-layer subsystem.
 *
 * Hand-written client module (same factory format the built client bundles use):
 * a trigger button in the composer tool row and a floating panel rendered in the
 * shell overlay. Data comes from the owner-authenticated `/api/memory.*` Fetch
 * routes registered by the `memory-api` host row; the panel never talks to the
 * host beyond that JSON API.
 */
window.__ModuleLoader__.load({
  id: '@qiuxu/memex-ui',
  factory(require) {
    const React = require('react')
    const h = React.createElement

    const STYLE_ID = '@qiuxu/memex/panel.css'

    const CSS = `
.memex-trigger {
  display: inline-flex; align-items: center; gap: 5px;
  height: 26px; padding: 0 8px; border-radius: 7px;
  border: 1px solid color-mix(in srgb, currentColor 18%, transparent);
  background: color-mix(in srgb, currentColor 6%, transparent);
  color: inherit; font: inherit; font-size: 12px; cursor: pointer;
  opacity: .82;
}
.memex-trigger:hover { opacity: 1; background: color-mix(in srgb, currentColor 12%, transparent); }
.memex-trigger-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--dsw-alias-brand-primary, #4c6fff); }
.memex-backdrop { position: fixed; inset: 0; z-index: 2147482000; background: rgba(0,0,0,.18); }
.memex-panel {
  position: fixed; z-index: 2147482100; top: 64px; right: 16px; bottom: 96px;
  width: min(460px, calc(100vw - 32px));
  display: flex; flex-direction: column; overflow: hidden;
  border-radius: 14px; border: 1px solid rgba(127,127,127,.28);
  background: var(--dsw-alias-bg-layer-1, #fff);
  color: var(--dsw-alias-label-primary, #1c1f26);
  box-shadow: 0 18px 60px rgba(0,0,0,.28);
  font-size: 13px; line-height: 1.45;
}
/* Host tokens above carry light/dark; the media fallback only applies when a
   deployment does not expose the --dsw-alias-* table. */
@supports not (color: var(--dsw-alias-bg-layer-1)) {
  @media (prefers-color-scheme: dark) {
    .memex-panel { background: #1e2027; color: #e7e9ee; border-color: rgba(255,255,255,.14); }
  }
}
.memex-head { display: flex; align-items: center; gap: 8px; padding: 12px 14px 10px; border-bottom: 1px solid rgba(127,127,127,.2); }
.memex-title { font-weight: 600; font-size: 14px; }
.memex-count { opacity: .65; font-size: 12px; flex: 1; }
.memex-close { border: 0; background: transparent; color: inherit; font-size: 18px; line-height: 1; cursor: pointer; opacity: .6; padding: 2px 6px; border-radius: 6px; }
.memex-close:hover { opacity: 1; background: color-mix(in srgb, currentColor 10%, transparent); }
.memex-sub { display: flex; gap: 8px; padding: 10px 14px; border-bottom: 1px solid rgba(127,127,127,.14); }
.memex-search { flex: 1; height: 30px; padding: 0 10px; border-radius: 8px; outline: none; color: inherit;
  border: 1px solid rgba(127,127,127,.35); background: color-mix(in srgb, currentColor 4%, transparent); font: inherit; }
.memex-search:focus { border-color: var(--dsw-alias-brand-primary, #4c6fff); }
.memex-body { flex: 1; overflow-y: auto; padding: 6px 8px 12px; }
.memex-empty { padding: 28px 16px; text-align: center; opacity: .6; }
.memex-row { padding: 9px 10px; border-radius: 9px; cursor: pointer; border: 1px solid transparent; }
.memex-row:hover { background: color-mix(in srgb, currentColor 6%, transparent); }
.memex-row.open { border-color: color-mix(in srgb, var(--dsw-alias-brand-primary, #4c6fff) 40%, transparent); background: color-mix(in srgb, var(--dsw-alias-brand-primary, #4c6fff) 8%, transparent); }
.memex-row-title { font-weight: 550; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.memex-row-meta { opacity: .6; font-size: 11.5px; margin-top: 2px; display: flex; gap: 8px; flex-wrap: wrap; }
.memex-row-when { opacity: .8; font-size: 12px; margin-top: 3px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.memex-badge { display: inline-block; padding: 0 5px; border-radius: 4px; background: color-mix(in srgb, var(--dsw-alias-brand-primary, #4c6fff) 16%, transparent); color: var(--dsw-alias-brand-primary, #4c6fff); font-size: 10.5px; }
.memex-badge.pinned { background: rgba(255,170,60,.2); color: #d98816; }
.memex-row-actions { display: flex; gap: 6px; margin-top: 6px; }
.memex-btn { border: 1px solid rgba(127,127,127,.35); background: transparent; color: inherit; border-radius: 6px; height: 24px; padding: 0 8px; font-size: 11.5px; cursor: pointer; }
.memex-btn:hover { border-color: var(--dsw-alias-brand-primary, #4c6fff); color: var(--dsw-alias-brand-primary, #4c6fff); }
.memex-btn.danger:hover { border-color: #e05c5c; color: #e05c5c; }
.memex-pre { margin: 8px 0 2px; padding: 10px; border-radius: 8px; max-height: 320px; overflow: auto;
  background: color-mix(in srgb, currentColor 5%, transparent); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11.5px; white-space: pre-wrap; word-break: break-word; }
.memex-modes { display: flex; gap: 4px; padding: 8px 14px; border-bottom: 1px solid rgba(127,127,127,.14); align-items: center; }
.memex-mode { border: 1px solid rgba(127,127,127,.3); background: transparent; color: inherit; border-radius: 7px; height: 26px; padding: 0 10px; font: inherit; font-size: 12px; cursor: pointer; opacity: .72; }
.memex-mode:hover { opacity: 1; }
.memex-mode.active { border-color: var(--dsw-alias-brand-primary, #4c6fff); color: var(--dsw-alias-brand-primary, #4c6fff); background: color-mix(in srgb, var(--dsw-alias-brand-primary, #4c6fff) 10%, transparent); opacity: 1; font-weight: 600; }
.memex-mode-hint { margin-left: auto; font-size: 11.5px; opacity: .6; }
.memex-kinds { display: flex; flex-wrap: wrap; gap: 4px 10px; padding: 6px 14px; border-bottom: 1px solid rgba(127,127,127,.14); font-size: 11.5px; }
.memex-kind { display: inline-flex; align-items: center; gap: 5px; opacity: .9; }
.memex-kind i { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.memex-off { padding: 26px 18px; text-align: center; opacity: .78; line-height: 1.7; }
.memex-off strong { display: block; margin-bottom: 6px; font-size: 13px; opacity: 1; }
.memex-scope { opacity: .7; font-size: 11px; border: 1px solid rgba(127,127,127,.28); border-radius: 4px; padding: 0 4px; }
.memex-error { margin: 10px 14px; padding: 8px 10px; border-radius: 8px; background: rgba(224,92,92,.14); color: #d64545; font-size: 12px; }
.memex-foot { padding: 8px 14px; border-top: 1px solid rgba(127,127,127,.16); font-size: 11.5px; opacity: .62; display: flex; justify-content: space-between; gap: 8px; }
`

    /** Tiny shared store: the trigger and the overlay are separate slot components. */
    const panelStore = {
      state: { open: false, sessionId: undefined },
      listeners: new Set(),
      emit() {
        for (const listener of this.listeners) listener()
      },
      set(sessionId, open) {
        this.state = { open, sessionId: open ? sessionId : undefined }
        this.emit()
      },
      toggle(sessionId) {
        const nextOpen = !(this.state.open && this.state.sessionId === sessionId)
        this.set(sessionId, nextOpen)
      },
      close() {
        this.set(this.state.sessionId, false)
      },
    }

    function usePanelState() {
      const [state, setState] = React.useState(panelStore.state)
      React.useEffect(() => {
        const listener = () => setState(panelStore.state)
        panelStore.listeners.add(listener)
        return () => panelStore.listeners.delete(listener)
      }, [])
      return state
    }

    /** Host route helper; routes are document-relative, like `api/session.export`. */
    async function api(path, options) {
      const response = await fetch(path, options)
      const text = await response.text()
      let data
      try {
        data = text.length === 0 ? {} : JSON.parse(text)
      } catch {
        throw new Error(`memory API returned non-JSON (${response.status})`)
      }
      if (!response.ok || data.ok === false) {
        throw new Error(data.message ?? `memory API failed (${response.status})`)
      }
      return data
    }

    /** Load the catalog for one session. */
    async function loadIndex(sessionId) {
      return api(`api/memory.index?sessionId=${encodeURIComponent(sessionId)}&limit=200`)
    }

    /** Load one record body. */
    async function loadRecord(sessionId, id) {
      return api(`api/memory.record?sessionId=${encodeURIComponent(sessionId)}&id=${encodeURIComponent(id)}`)
    }

    /** Persist one extra-context mode for a session. */
    async function enableLevel(sessionId, level) {
      return api('api/memory.level', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ sessionId, level }),
      })
    }

    /** Search the archive. */
    async function search(sessionId, query) {
      return api(`api/memory.search?sessionId=${encodeURIComponent(sessionId)}&q=${encodeURIComponent(query)}&limit=50`)
    }

    /** Change one record's lifecycle status. */
    async function setStatus(sessionId, id, status) {
      return api('api/memory.status', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ sessionId, id, status }),
      })
    }

    /** Format a token count for the header/footer. */
    function formatTokens(tokens) {
      if (typeof tokens !== 'number' || !Number.isFinite(tokens)) return '0'
      if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(2)}M`
      if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}k`
      return String(tokens)
    }

    /** Format a timestamp for a row. */
    function formatTime(ms) {
      if (typeof ms !== 'number') return ''
      try {
        return new Date(ms).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
      } catch {
        return ''
      }
    }

    /** Composer tool-row trigger. */
    function MemoryTrigger(props) {
      const sessionId = props.sessionId
      const state = usePanelState()
      const active = state.open && state.sessionId === sessionId
      return h(
        'button',
        {
          type: 'button',
          className: 'memex-trigger',
          title: '打开上下文面板：浏览/搜索额外上下文页',
          'aria-pressed': active ? 'true' : 'false',
          onClick: () => {
            if (sessionId === undefined) return
            panelStore.toggle(sessionId)
          },
        },
        h('span', { className: 'memex-trigger-dot' }),
        '上下文',
      )
    }

    /** One record row, expandable to its raw archived body. */
    function MemoryRow(props) {
      const { record, expanded, body, loading, onToggle, onPin, onRestore } = props
      const pinned = record.status === 'pinned'
      return h(
        'div',
        { className: `memex-row${expanded ? ' open' : ''}`, onClick: onToggle },
        h('div', { className: 'memex-row-title', title: record.title }, record.title),
        h(
          'div',
          { className: 'memex-row-meta' },
          h('span', null, record.kind),
          h('span', { className: 'memex-scope' }, record.scope === 'session' ? 'L2 本会话' : 'L3 工作区'),
          record.cold === true ? h('span', { className: 'memex-scope' }, '冷存') : null,
          h('span', { className: `memex-badge${pinned ? ' pinned' : ''}` }, pinned ? '已置顶' : record.status),
          h('span', null, `${formatTokens(record.tokens)} tokens`),
          h('span', null, formatTime(record.updatedAt)),
        ),
        record.useWhen ? h('div', { className: 'memex-row-when' }, record.useWhen) : null,
        h(
          'div',
          { className: 'memex-row-actions', onClick: (event) => event.stopPropagation() },
          h(
            'button',
            {
              type: 'button',
              className: 'memex-btn',
              onClick: (event) => {
                event.stopPropagation()
                onPin(record, pinned ? 'active' : 'pinned')
              },
            },
            pinned ? '取消置顶' : '置顶',
          ),
          record.cold === true && typeof onRestore === 'function'
            ? h(
                'button',
                {
                  type: 'button',
                  className: 'memex-btn',
                  onClick: (event) => {
                    event.stopPropagation()
                    onRestore(record)
                  },
                },
                '回热',
              )
            : null,
        ),
        expanded
          ? loading
            ? h('div', { className: 'memex-pre' }, '加载中…')
            : body !== undefined
              ? h('pre', { className: 'memex-pre' }, body)
              : null
          : null,
      )
    }

    /** Floating panel rendered in the shell overlay. */
    function MemoryPanel() {
      const state = usePanelState()
      const sessionId = state.sessionId
      const [catalog, setCatalog] = React.useState(undefined)
      const [error, setError] = React.useState(undefined)
      const [query, setQuery] = React.useState('')
      const [searching, setSearching] = React.useState(false)
      const [expandedId, setExpandedId] = React.useState(undefined)
      const [expandedBody, setExpandedBody] = React.useState(undefined)
      const [expandedLoading, setExpandedLoading] = React.useState(false)
      const [reloadKey, setReloadKey] = React.useState(0)
      const [notice, setNotice] = React.useState(undefined)

      React.useEffect(() => {
        if (!state.open || sessionId === undefined) return undefined
        let cancelled = false
        setError(undefined)
        loadIndex(sessionId)
          .then((data) => {
            if (!cancelled) setCatalog(data)
          })
          .catch((failure) => {
            if (!cancelled) setError(failure.message)
          })
        return () => {
          cancelled = true
        }
      }, [state.open, sessionId, reloadKey])

      React.useEffect(() => {
        if (!state.open) return undefined
        const onKeyDown = (event) => {
          if (event.key === 'Escape') panelStore.close()
        }
        window.addEventListener('keydown', onKeyDown)
        return () => window.removeEventListener('keydown', onKeyDown)
      }, [state.open])

      if (!state.open || sessionId === undefined) return null

      const levels = { l2: catalog?.levels?.l2 === true, l3: catalog?.levels?.l3 === true }
      const anyLevel = levels.l2 || levels.l3
      const levelText = levels.l2 && levels.l3 ? 'L2+L3' : levels.l3 ? 'L3' : levels.l2 ? 'L2' : '关闭'
      const kindTokens = catalog?.byKindTokens ?? {}
      const kindEntries = Object.entries(kindTokens)
        .filter(([, tokens]) => Number(tokens) > 0)
        .sort((left, right) => Number(right[1]) - Number(left[1]))
      const kindMeta = (kind) => ({
        episode: { label: '对话归档', color: '#d4b45a' },
        artifact: { label: '产出物', color: '#6ea8fe' },
        decision: { label: '决策', color: '#8b7cf6' },
        fact: { label: '事实', color: '#2dd4bf' },
        procedure: { label: '流程', color: '#f59e0b' },
        'open-thread': { label: '待办', color: '#f97316' },
        incident: { label: '故障', color: '#ef4444' },
        preference: { label: '偏好', color: '#a3e635' },
      }[kind] ?? { label: kind, color: '#999' })
      const records = catalog?.records ?? []
      const enable = (level) => {
        if (levels[level]) return
        enableLevel(sessionId, level)
          .then(() => setReloadKey((value) => value + 1))
          .catch((failure) => setError(failure.message))
      }
      const setRecords = (nextRecords) => setCatalog((current) => (current === undefined ? current : { ...current, records: nextRecords }))

      const compressPool = () => {
        const targetLevel = levels.l3 ? 'l3' : levels.l2 ? 'l2' : undefined
        if (targetLevel === undefined) {
          setNotice('没有启用的层级可压缩')
          return
        }
        setNotice('压缩中…')
        api('api/memory.compress', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ sessionId, level: targetLevel, strategy: 'cold', targetRatio: 0.6 }),
        })
          .then((data) => {
            const moved = (data.reports ?? []).reduce((sum, report) => sum + (report.coldMoved ?? 0), 0)
            setNotice(moved > 0 ? `已冷移 ${moved} 条记录（无损）` : '当前已低于目标比例，无需压缩')
            setReloadKey((value) => value + 1)
          })
          .catch((failure) => setNotice(`压缩失败：${failure.message}`))
      }

      const restoreRecord = (record) => {
        api('api/memory.restore', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ sessionId, id: record.id }),
        })
          .then(() => {
            setNotice(`已回热 ${record.id}`)
            setReloadKey((value) => value + 1)
          })
          .catch((failure) => setNotice(`回热失败：${failure.message}`))
      }

      const toggleRow = (record) => {
        if (expandedId === record.id) {
          setExpandedId(undefined)
          setExpandedBody(undefined)
          return
        }
        setExpandedId(record.id)
        setExpandedBody(undefined)
        setExpandedLoading(true)
        loadRecord(sessionId, record.id)
          .then((data) => {
            setExpandedBody(data.body)
          })
          .catch((failure) => setExpandedBody(`读取失败：${failure.message}`))
          .finally(() => setExpandedLoading(false))
      }

      const pin = (record, status) => {
        setStatus(sessionId, record.id, status)
          .then((data) => {
            setRecords(records.map((entry) => (entry.id === record.id ? { ...entry, status: data.record.status } : entry)))
          })
          .catch((failure) => setError(failure.message))
      }

      const submitSearch = (event) => {
        event.preventDefault()
        const text = query.trim()
        if (text.length === 0) {
          setReloadKey((value) => value + 1)
          return
        }
        setSearching(true)
        setError(undefined)
        search(sessionId, text)
          .then((data) => setCatalog((current) => ({ ...(current ?? {}), records: data.records })))
          .catch((failure) => setError(failure.message))
          .finally(() => setSearching(false))
      }

      return h(
        React.Fragment,
        null,
        h('div', { className: 'memex-backdrop', onClick: () => panelStore.close() }),
        h(
          'div',
          { className: 'memex-panel', role: 'dialog', 'aria-label': '额外上下文面板', 'data-memex-panel': '' },
          h(
            'div',
            { className: 'memex-head' },
            h('span', { className: 'memex-title' }, '额外上下文'),
            h(
              'span',
              { className: 'memex-count' },
              catalog === undefined
                ? '加载中…'
                : !anyLevel
                  ? '额外上下文：关闭'
                  : `${levelText} · ${catalog.hotCount ?? catalog.count} 条热 · ${formatTokens(catalog.hotTokens ?? catalog.tokens)} / ${formatTokens(catalog.capacityTokens)} tokens${catalog.coldCount > 0 ? ` · 冷存 ${catalog.coldCount}` : ''}`,
            ),
            anyLevel
              ? h('button', { type: 'button', className: 'memex-btn', title: '把最老的记录无损移入冷层，释放热池', onClick: compressPool }, '压缩')
              : null,
            h('button', { type: 'button', className: 'memex-close', title: '关闭', onClick: () => panelStore.close() }, '×'),
          ),
          notice !== undefined ? h('div', { className: 'memex-error' }, notice) : null,
          h(
            'div',
            { className: 'memex-modes' },
            h(
              'button',
              { type: 'button', className: `memex-mode${levels.l2 ? ' active' : ''}`, onClick: () => enable('l2'), title: levels.l2 ? 'L2 已开启（粘性，不可关闭）' : '开启 L2 本会话私有 10M' },
              levels.l2 ? '🔒 L2 本会话 10M' : 'L2 本会话 10M',
            ),
            h(
              'button',
              { type: 'button', className: `memex-mode${levels.l3 ? ' active' : ''}`, onClick: () => enable('l3'), title: levels.l3 ? 'L3 已开启（粘性，不可关闭）' : '开启 L3 工作区共享 100M' },
              levels.l3 ? '🔒 L3 工作区 100M' : 'L3 工作区 100M',
            ),
            h('span', { className: 'memex-mode-hint' }, anyLevel
              ? (() => {
                  const hot = catalog?.hotTokens ?? catalog?.tokens ?? 0
                  const cap = catalog?.capacityTokens ?? 0
                  const ratio = cap > 0 ? hot / cap : 0
                  return `${ratio >= 0.8 ? '⚠ 热池 ' : ''}${Math.round(ratio * 100)}% 热 · L1↓${formatTokens(catalog?.l1Evicted?.tokens ?? 0)}`
                })()
              : '默认关闭 · 开启后不可关闭'),
          ),
          anyLevel && kindEntries.length > 0
            ? h(
                'div',
                { className: 'memex-kinds' },
                kindEntries.map(([kind, tokens]) => {
                  const meta = kindMeta(kind)
                  return h(
                    'span',
                    { key: kind, className: 'memex-kind' },
                    h('i', { style: { background: meta.color } }),
                    meta.label,
                    ' ',
                    formatTokens(Number(tokens)),
                  )
                }),
              )
            : null,
          h(
            'form',
            { className: 'memex-sub', onSubmit: submitSearch },
            h('input', {
              className: 'memex-search',
              value: query,
              placeholder: !anyLevel ? 'L1 额外上下文尚未开启 — 开启 L2/L3 后可搜索' : '搜索上下文页（文件名、报错、标识符…）',
              onChange: (event) => setQuery(event.target.value),
              disabled: searching || !anyLevel,
            }),
          ),
          error !== undefined ? h('div', { className: 'memex-error' }, error) : null,
          h(
            'div',
            { className: 'memex-body' },
            !anyLevel
              ? h(
                  'div',
                  { className: 'memex-off' },
                  h('strong', null, 'L1 额外上下文当前关闭'),
                  '开启 L2/L3 后，超出阈值的 L1 上下文会被原样搬到额外上下文并释放 L1 空间（不调用 LLM 摘要），随后可随时检索回原文。',
                  h('br', null),
                  h('span', null, 'L2（本会话私有 10M）与 L3（工作区共享 100M）独立开启，开启后不可关闭；新归档写入最深启用层（L3 优先）。'),
                )
              : records.length === 0 && catalog !== undefined
              ? h('div', { className: 'memex-empty' }, '已启用层级还没有归档记录：上下文接近阈值时，较老的 L1 内容会自动转移到这里。')
              : records.map((record) =>
                  h(MemoryRow, {
                    key: record.id,
                    record,
                    expanded: expandedId === record.id,
                    loading: expandedLoading && expandedId === record.id,
                    body: expandedId === record.id ? expandedBody : undefined,
                    onToggle: () => toggleRow(record),
                    onPin: pin,
                    onRestore: restoreRecord,
                  }),
                ),
          ),
          h(
            'div',
            { className: 'memex-foot' },
            h(
              'span',
              null,
              !anyLevel
                ? 'L1 额外上下文：关闭'
                : `${levelText} · 本次会话 L1 已转移 ${catalog?.l1Evicted?.count ?? 0} 批 / ${formatTokens(catalog?.l1Evicted?.tokens ?? 0)} tokens`,
            ),
            h('span', null, `点记录展开原文${catalog?.coldCount > 0 ? '（含冷存记录，可按 id 打开）' : ''}${catalog?.compression?.count > 0 ? ` · 已压缩 ${catalog.compression.count} 次` : ''}${levels.l3 ? ' · L3 共享（敏感内容自动留在 L2）' : ''} · 接近容量时模型会先询问 · Esc 关闭`),
          ),
        ),
      )
    }


    /**
     * Merge the archive-capacity reading into the shipped composer context meter.
     *
     * ui-conversation renders its `ContextMeter` inline (it has no slot), so this
     * bridge decorates it instead: an inner arc inside the existing 14px ring
     * shows how much of the 10M-token archive is used, and the meter's popover
     * gains a "额外上下文" row plus a shortcut into the full memory panel. Only
     * DOM nodes this bridge creates are written, and they are removed on
     * teardown; re-renders of the meter are re-decorated by the tick.
     */
    function installContextRingBridge(ctx) {
      if (typeof document === 'undefined' || typeof window === 'undefined') return () => {}
      const SESSION_COLOR = 'var(--dsw-static-teal-450, #14b8a6)'
      const WORKSPACE_COLOR = 'var(--dsw-alias-brand-primary, #4c6fff)'
      const INNER_RADIUS = 3.2
      const INNER_CIRCUMFERENCE = 2 * Math.PI * INNER_RADIUS
      const METER_BUTTON_SELECTOR = 'button[aria-haspopup="dialog"]'
      const LEVELS = [
        { id: 'l2', label: 'L2 本会话' },
        { id: 'l3', label: 'L3 工作区' },
      ]
      // Content classification for the archive, mirroring the shipped context
      // meter's breakdown (label + stable swatch per record kind).
      const KIND_META = {
        episode: { label: '对话归档', color: '#d4b45a' },
        artifact: { label: '产出物', color: '#6ea8fe' },
        decision: { label: '决策', color: '#8b7cf6' },
        fact: { label: '事实', color: '#2dd4bf' },
        procedure: { label: '流程', color: '#f59e0b' },
        'open-thread': { label: '待办', color: '#f97316' },
        incident: { label: '故障', color: '#ef4444' },
        preference: { label: '偏好', color: '#a3e635' },
      }
      const kindMeta = (kind) => KIND_META[kind] ?? { label: kind, color: 'var(--dsw-alias-label-tertiary, #999)' }
      let disposed = false
      let memory = {
        levels: { l2: false, l3: false },
        captureScope: undefined,
        tokens: 0,
        capacityTokens: 0,
        byKindTokens: {},
        l1Evicted: { count: 0, tokens: 0 },
        hotTokens: 0,
        coldTokens: 0,
        coldCount: 0,
        l2: { enabled: false, tokens: 0, hotTokens: 0, coldCount: 0, count: 0, capacityTokens: 10_000_000 },
        l3: { enabled: false, tokens: 0, hotTokens: 0, coldCount: 0, count: 0, capacityTokens: 100_000_000 },
      }
      let sessionId
      let dataTimer
      let decorateTimer
      const touchedLabels = new Set()

      const currentSession = () => {
        try {
          return ctx.uiSession.adapter.current
        } catch {
          return undefined
        }
      }
      const currentSessionId = () => {
        const current = currentSession()
        if (current === undefined) return sessionId
        try {
          return current.getSnapshot().key
        } catch {
          return sessionId
        }
      }

      /** Color of the active capture target. */
      const modeColor = () => (memory.captureScope === 'session' ? SESSION_COLOR : WORKSPACE_COLOR)

      /** Enable one sticky cache level, then re-read the panel state. */
      async function enableLevel(level) {
        const id = currentSessionId()
        if (typeof id !== 'string' || id.length === 0) return
        if (memory.levels[level] === true) return
        try {
          await api('api/memory.level', {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ sessionId: id, level }),
          })
        } catch {
          return
        }
        await refresh()
      }

      /** Fetch the aggregate memory reading for the focused session. */
      async function refresh() {
        const id = currentSessionId()
        if (typeof id !== 'string' || id.length === 0) return
        sessionId = id
        try {
          const data = await api(`api/memory.index?sessionId=${encodeURIComponent(id)}&limit=1`)
          const levels = {
            l2: data.levels?.l2 === true,
            l3: data.levels?.l3 === true,
          }
          memory = {
            levels,
            captureScope: data.captureScope ?? (levels.l3 ? 'workspace' : levels.l2 ? 'session' : undefined),
            tokens: Number(data.hotTokens ?? data.tokens) || 0,
            capacityTokens: Number(data.capacityTokens) || 0,
            hotTokens: Number(data.hotTokens ?? data.tokens) || 0,
            coldTokens: Number(data.coldTokens) || 0,
            coldCount: Number(data.coldCount) || 0,
            byKindTokens: data.byKindTokens !== null && typeof data.byKindTokens === 'object' ? data.byKindTokens : {},
            l1Evicted: data.l1Evicted ?? { count: 0, tokens: 0 },
            l2: data.l2 ?? { enabled: false, tokens: 0, count: 0, capacityTokens: 10_000_000 },
            l3: data.l3 ?? { enabled: false, tokens: 0, count: 0, capacityTokens: 100_000_000 },
          }
        } catch {
          return
        }
        decorate()
      }

      /** All composer context meters currently in the document. */
      function findMeters() {
        const meters = []
        for (const button of document.querySelectorAll(METER_BUTTON_SELECTOR)) {
          const svg = button.querySelector('svg[viewBox="0 0 14 14"]')
          if (svg !== null) meters.push({ button, svg })
        }
        return meters
      }

      /** The shipped context-meter popover, if open (our own dialog is marked). */
      function findContextPanel() {
        for (const dialog of document.querySelectorAll('[role="dialog"]')) {
          if (dialog.hasAttribute('data-memex-panel')) continue
          if (dialog.hasAttribute('data-memex-meter-row')) continue
          const text = dialog.textContent ?? ''
          if (/上下文|context/i.test(text) && /%/.test(text)) return dialog
        }
        return undefined
      }

      /** Format the visible-pool figures for the popover row. */
      function figuresText() {
        const any = memory.levels.l2 || memory.levels.l3
        if (!any) return `关闭 · L2 ${formatTokens(memory.l2.tokens)}/10M · L3 ${formatTokens(memory.l3.tokens)}/100M`
        const evicted = memory.l1Evicted?.tokens > 0 ? ` · L1↓${formatTokens(memory.l1Evicted.tokens)}` : ''
        const cold = memory.coldCount > 0 ? ` · 冷存 ${memory.coldCount}` : ''
        const ratio = memory.capacityTokens > 0 ? memory.tokens / memory.capacityTokens : 0
        const warn = ratio >= 0.8 ? ' · ⚠ 接近容量' : ''
        return `${formatTokens(memory.tokens)} / ${formatTokens(memory.capacityTokens)}${evicted}${cold}${warn}`
      }

      /** Draw the sticky-level switches (L2 / L3) inside the popover row. */
      function levelSegment() {
        const segment = document.createElement('span')
        segment.setAttribute('data-memex-meter-modes', '')
        segment.style.cssText = 'display:inline-flex;gap:2px;flex:none;'
        for (const entry of LEVELS) {
          const button = document.createElement('button')
          button.type = 'button'
          button.setAttribute('data-memex-meter-mode', entry.id)
          button.textContent = entry.label
          button.style.cssText = 'border:0;border-radius:5px;padding:0 6px;height:18px;font:inherit;font-size:11px;line-height:18px;cursor:pointer;background:transparent;color:inherit;'
          button.addEventListener('click', (event) => {
            event.preventDefault()
            event.stopPropagation()
            void enableLevel(entry.id)
          })
          segment.appendChild(button)
        }
        return segment
      }

      /** Build/refresh the per-kind breakdown block under the memory row. */
      function decorateBreakdown(panel, row) {
        let block = panel.querySelector('[data-memex-breakdown]')
        if (block === null) {
          block = document.createElement('div')
          block.setAttribute('data-memex-breakdown', '')
          block.style.cssText = 'margin-top:6px;font-size:11.5px;line-height:18px;color:inherit;'
          row.insertAdjacentElement('afterend', block)
        }
        const entries = Object.entries(memory.byKindTokens ?? {})
          .filter(([, tokens]) => Number(tokens) > 0)
          .sort((left, right) => Number(right[1]) - Number(left[1]))
        const total = entries.reduce((sum, [, tokens]) => sum + Number(tokens), 0)
        if ((memory.levels.l2 !== true && memory.levels.l3 !== true) || total <= 0) {
          block.style.display = 'none'
          return
        }
        block.style.display = 'block'
        const signature = `${memory.levels.l2 ? 'L2' : ''}${memory.levels.l3 ? 'L3' : ''}|${entries.map(([kind, tokens]) => `${kind}:${tokens}`).join(',')}`
        if (block.dataset.dshMemoryBreakdown === signature) return
        block.dataset.dshMemoryBreakdown = signature
        block.textContent = ''
        const bar = document.createElement('div')
        bar.style.cssText = 'display:flex;gap:1px;height:4px;border-radius:999px;overflow:hidden;margin:2px 0 6px;background:var(--dsw-alias-interactive-bg-hover, rgba(127,127,127,.15));'
        const rows = document.createElement('div')
        rows.style.cssText = 'display:flex;flex-direction:column;gap:2px;'
        for (const [kind, tokens] of entries) {
          const meta = kindMeta(kind)
          const segment = document.createElement('span')
          segment.style.cssText = `height:100%;flex:0 0 ${Math.max(2, (Number(tokens) / total) * 100)}%;background:${meta.color};`
          segment.title = `${meta.label} ${formatTokens(Number(tokens))}`
          bar.appendChild(segment)
          const line = document.createElement('div')
          line.style.cssText = 'display:flex;align-items:center;gap:6px;'
          const swatch = document.createElement('span')
          swatch.style.cssText = `width:8px;height:8px;border-radius:2px;flex:none;background:${meta.color};`
          const label = document.createElement('span')
          label.textContent = meta.label
          const figures = document.createElement('span')
          figures.style.cssText = 'margin-left:auto;font-variant-numeric:tabular-nums;color:var(--dsw-alias-label-primary, inherit);'
          figures.textContent = formatTokens(Number(tokens))
          line.append(swatch, label, figures)
          rows.appendChild(line)
        }
        block.append(bar, rows)
      }

      /** Write the memory row into the open context-meter popover. */
      function decoratePanel(panel) {
        let row = panel.querySelector('[data-memex-meter-row]')
        if (row === null) {
          row = document.createElement('div')
          row.setAttribute('data-memex-meter-row', '')
          row.style.cssText = 'margin-top:8px;padding-top:8px;border-top:1px solid var(--dsw-alias-border-l1, rgba(127,127,127,.25));display:flex;align-items:center;gap:8px;font-size:12px;line-height:20px;flex-wrap:wrap;'
          const swatch = document.createElement('span')
          swatch.setAttribute('data-memex-meter-swatch', '')
          swatch.style.cssText = 'width:8px;height:8px;border-radius:2px;flex:none;background:var(--dsw-static-teal-450, #14b8a6);'
          const label = document.createElement('span')
          label.textContent = '额外上下文'
          label.style.color = 'var(--dsw-alias-label-secondary, inherit)'
          const figures = document.createElement('span')
          figures.setAttribute('data-memex-meter-figures', '')
          figures.style.cssText = 'margin-left:auto;font-variant-numeric:tabular-nums;color:var(--dsw-alias-label-primary, inherit);font-weight:500;'
          const link = document.createElement('button')
          link.type = 'button'
          link.setAttribute('data-memex-meter-open', '')
          link.textContent = '查看记录 →'
          link.style.cssText = 'border:0;background:0 0;color:var(--dsw-alias-brand-primary, #4c6fff);cursor:pointer;font:inherit;padding:0;flex:none;'
          link.addEventListener('click', (event) => {
            event.preventDefault()
            event.stopPropagation()
            panelStore.set(currentSessionId(), true)
          })
          row.append(swatch, label, levelSegment(), figures, link)
          panel.appendChild(row)
        }
        const anyLevel = memory.levels.l2 === true || memory.levels.l3 === true
        const swatch = row.querySelector('[data-memex-meter-swatch]')
        if (swatch !== null) {
          swatch.style.background = anyLevel ? modeColor() : 'var(--dsw-alias-border-l3, #999)'
          swatch.style.opacity = anyLevel ? '1' : '0.5'
        }
        for (const button of row.querySelectorAll('[data-memex-meter-mode]')) {
          const level = button.getAttribute('data-memex-meter-mode')
          const active = memory.levels[level] === true
          button.textContent = active ? `🔒 ${level === 'l2' ? 'L2 本会话' : 'L3 工作区'}` : level === 'l2' ? 'L2 本会话' : 'L3 工作区'
          button.style.background = active ? 'color-mix(in srgb, var(--dsw-alias-brand-primary, #4c6fff) 16%, transparent)' : 'transparent'
          button.style.color = active ? 'var(--dsw-alias-label-primary, inherit)' : 'var(--dsw-alias-label-tertiary, inherit)'
          button.style.fontWeight = active ? '600' : '400'
          button.style.cursor = active ? 'default' : 'pointer'
          button.title = active ? '已开启（粘性，不可关闭）' : `开启 ${level === 'l2' ? 'L2 本会话' : 'L3 工作区'}`
        }
        const figures = row.querySelector('[data-memex-meter-figures]')
        if (figures !== null) figures.textContent = figuresText()
        decorateBreakdown(panel, row)
      }

      /** Draw/update the inner memory arc and the meter's a11y label. */
      function decorate() {
        if (disposed) return
        const active = memory.levels.l2 === true || memory.levels.l3 === true
        const percent = active && memory.capacityTokens > 0 ? Math.min(100, (memory.tokens / memory.capacityTokens) * 100) : 0
        for (const { button, svg } of findMeters()) {
          let arc = svg.querySelector('circle[data-memex-arc]')
          if (arc === null) {
            arc = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
            arc.setAttribute('data-memex-arc', '')
            arc.setAttribute('cx', '7')
            arc.setAttribute('cy', '7')
            arc.setAttribute('r', String(INNER_RADIUS))
            arc.setAttribute('fill', 'none')
            arc.setAttribute('stroke-width', '1.4')
            arc.setAttribute('stroke-linecap', 'round')
            arc.setAttribute('transform', 'rotate(-90 7 7)')
            arc.setAttribute('pointer-events', 'none')
            svg.appendChild(arc)
          }
          arc.setAttribute('stroke', modeColor())
          arc.style.opacity = percent > 0 ? '0.9' : '0'
          arc.setAttribute('stroke-dasharray', `${(INNER_CIRCUMFERENCE * percent) / 100} ${INNER_CIRCUMFERENCE}`)
          const base = button.dataset.dshMemoryBaseLabel ?? button.getAttribute('aria-label') ?? ''
          if (button.dataset.dshMemoryBaseLabel === undefined) button.dataset.dshMemoryBaseLabel = base
          const levelText = memory.levels.l2 && memory.levels.l3 ? 'L2+L3' : memory.levels.l3 ? 'L3' : memory.levels.l2 ? 'L2' : ''
          const suffix = active
            ? ` · 额外上下文 ${Math.round(percent)}%（${levelText}）`
            : ' · 额外上下文 关'
          const label = `${button.dataset.dshMemoryBaseLabel}${suffix}`
          if (button.getAttribute('aria-label') !== label) button.setAttribute('aria-label', label)
          touchedLabels.add(button)
          if (button.getAttribute('aria-expanded') === 'true') {
            const panel = findContextPanel()
            if (panel !== undefined) decoratePanel(panel)
          }
        }
      }

      const unsubscribe = (() => {
        const current = currentSession()
        if (current === undefined) return () => {}
        try {
          return current.subscribe(() => {
            sessionId = currentSessionId()
            void refresh()
          })
        } catch {
          return () => {}
        }
      })()

      sessionId = currentSessionId()
      void refresh()
      decorateTimer = window.setInterval(decorate, 600)
      dataTimer = window.setInterval(() => void refresh(), 15000)

      return () => {
        disposed = true
        window.clearInterval(decorateTimer)
        window.clearInterval(dataTimer)
        unsubscribe()
        for (const button of touchedLabels) {
          const base = button.dataset.dshMemoryBaseLabel
          if (base !== undefined) button.setAttribute('aria-label', base)
        }
        for (const arc of document.querySelectorAll('circle[data-memex-arc]')) arc.remove()
        for (const row of document.querySelectorAll('[data-memex-meter-row]')) row.remove()
        for (const block of document.querySelectorAll('[data-memex-breakdown]')) block.remove()
      }
    }

    function apply(ctx) {
      ctx.effect(() => {
        if (typeof document === 'undefined') return () => {}
        const tag = document.createElement('style')
        tag.dataset.plugin = '@qiuxu/memex-ui'
        tag.dataset.pluginCss = STYLE_ID
        tag.textContent = CSS
        document.head.appendChild(tag)
        return () => tag.remove()
      }, 'memory-panel: styles')

      ctx.effect(() => installContextRingBridge(ctx), 'memory-panel: context ring bridge')

      ctx.slots.inject('conversation.input.left', () =>
        ctx.slots.register({ name: 'conversation.input.left', id: 'memory-panel-trigger', order: 30 }, MemoryTrigger),
      )
      ctx.slots.inject('shell.overlay', () =>
        ctx.slots.register({ name: 'shell.overlay', id: 'memory-panel', order: 10 }, MemoryPanel),
      )
    }

    return { inject: ['slots', 'uiSession'], apply }
  },
})
