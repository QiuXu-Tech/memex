# Native wire routing check 01

This is an engineering failure analysis, not an experiment result or a retry.
The failed `w-101` replicate 1 remains consumed. Its retained relay state has no
provider records or dispatches. Before a provider dispatch, the current relay
Handler returns 400/401/409 rather than the observed 502, supporting a failure
before the request reached that Handler.

The source chain is pinned to Codex `0.153.0`, commit
`41e22fee981a63b3698df7ed36bad393cda24715`, reqwest `0.12.28`, and hyper-util
`0.1.20`. The default Codex proxy policy retains reqwest system discovery.
hyper-util's macOS loader imports HTTP/HTTPS proxy endpoints without copying
the system exception list; its exception list comes from `NO_PROXY`/`no_proxy`.
The actual Mac feature check was reported by the coordinating agent as
`respect_system_proxy=false`, with zero turns started. Proxy addresses and
credential values are not recorded here.

The change adds only `NO_PROXY=127.0.0.1,localhost` and the identical lowercase
variable to the newly constructed host process environment. It neither reads
nor forwards user proxy URLs or exception lists, mutates the parent environment,
changes system or managed proxy policy, nor overrides `respect_system_proxy`.
The separate `RespectSystemProxy` route is not claimed to honor this environment
override. Provider-domain routing is not added to the exception list.

The eight reader-profile tests first ran with three failures, then passed after
the change. They verify exact local exception values, no inherited wildcard or
external-domain exceptions, no private proxy/provider value reads, unchanged
parent mappings, and no proxy-policy feature override. No Mac transport canary
or provider request was executed by the implementing agent. Actual pinned wire
payload compatibility remains a separate gate before another preparation grant.

See [proxy-analysis.json](proxy-analysis.json) for the versioned source URLs,
Git blob hashes, retained failure hashes, change hash, and red/green test record.

## Separate reasoning-summary configuration

The same pinned Codex release gives an unknown model an automatic reasoning
summary by default. The separately authorized host flag
`model_reasoning_summary="none"` makes its request builder use an empty summary
option, which the wire serializer omits. The relay still requires
`reasoning={"effort":"none"}`; its reasoning contract was not broadened. This
second test first failed, then all nine reader-profile tests passed. The profile
JSON, grant, original budget and already-consumed attempt were not changed.
See [summary-configuration.json](summary-configuration.json) for that source chain
and the combined reader implementation hash.

## Explicit builtin-tool registration controls

The pinned host enables `request_user_input` when its tool configuration is
absent. Disabling its default-mode feature changes the permitted modes but does
not suppress registration. The host flags now also set
`tools.experimental_request_user_input.enabled=false`. They explicitly set
`tools.update_plan.enabled=false` so an inherited user configuration cannot
enable that extra tool. Both settings restrict the requested tool surface; the
relay's accepted tool list is unchanged.

The new test first reported two failing subtests, then all ten reader-profile
tests passed after the flags were added. No Codex turn, provider request or Mac
operation was executed by the implementing agent. See
[tool-registration-configuration.json](tool-registration-configuration.json)
for the pinned configuration and registration source blobs, current reader hash,
and red/green record.

## Compaction and persisted dynamic tools

For the configured custom provider, pinned Codex advertises no remote compaction
capability. With the effective `token_budget=false` reported by the coordinating
agent's zero-turn Mac check, `thread/compact/start` invokes the ordinary Responses
streaming summary path. It does not require a `/responses/compact` relay route.

The parent thread's dynamic tool definitions are persisted in `SessionMeta`.
Cold resume and fork restore those definitions when no replacement tools are
supplied. The existing backend may therefore omit `dynamicTools` for those two
operations. See [host-lifecycle-routing.json](host-lifecycle-routing.json) for the
pinned source chain and the explicit boundary between source inspection and an
actual native execution. No new host override or runtime feature was added.
