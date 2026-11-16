# Audit fixes candidate — 2026-11-08

Implementation baseline: `af389c3a828c8458faae436d246b176c3a403e11`.
The original [audit](reviews/2026-11-08/AUDIT.md), observations and historical
results remain unchanged. This is an uncommitted local candidate; it does not
assign a release version or establish production, security or research acceptance.

## Implemented contracts

| Finding | Change |
| --- | --- |
| F01 | A network-free bootstrap links Core and all adapters. Production entry commands do not depend on the test loader. |
| F02 | Hard materializer budgets include the final rendered prefix, body and formatting, including forced pages. Oversized pages are explicitly omitted. The injection boundary checks the rendered block again. |
| F03 | Numeric block ordinals survive storage and reopen. Source order within a session is preserved; timestamps merge different source streams. Clock ambiguity is marked. Tool dependencies are selected together; orphan calls and results are omitted with explicit reasons. |
| F04 | Required records are fetched explicitly within the visible, current scope, then mapped to canonical page IDs. Unavailable IDs do not disclose whether a record is missing or invisible. |
| F05 | `registerPrefixIds` separates IDs from the existing text-prefix helper. An incomplete/evicted prefix is a miss. Capability negotiation checks required methods. |
| F06 | Grep and open use one-based body line coordinates. Frontmatter is excluded from grep offsets. |
| F07 | Level enabling atomically merges stored and requested bits, never undoing an enabled level. |
| F08 | Default event IDs include record/session identity. Explicit ID collisions cannot transfer ownership. |
| F09 | FTS schema creation, backfill and completion marker commit in one transaction; an interrupted migration is rebuilt on reopen. |
| F10 | Empty postings have an explicit completed marker; a normal reopen does not re-read their bodies. |
| F11 | Card enrichment uses revision-checked metadata patches; it cannot overwrite lifecycle/body/scope state or recreate a deleted record. Revisions do not reset on delete/recreate. |
| F12 | Actual dispatch attempts, including failure/cancellation, are persisted. Reported partial usage is retained; unverified usage/charges stay UNKNOWN. A per-invocation request cap includes retries and both levels. |
| F13 | HTTP body pages end on valid UTF-8/UTF-16 boundaries and return consumed length plus a continuation offset. The panel loads remaining pages and ignores stale responses. |
| F14 | Format, supported file layout, database entry, complete file manifest, hashes, database integrity and record references are validated before claiming restorability. |
| F15 | Restore copies and checks a private sibling candidate before directory exchange. Previous targets are retained, interrupted exchanges are guarded, and explicit recovery is available. |
| F16 | Negative SQLite BM25 scores are normalized in the correct direction; other retrieval weights remain unchanged. |
| A01 | Durable archives no longer await model enrichment. Session queues are separate; enhancement/query concurrency and stream waits are bounded. Disposal cancels local waits, and a timed-out enhancer is stopped for that policy instance. |
| A02 | Unknown/image-bearing/unrenderable message blocks remain in L1. Supported events preserve their original envelope and derived message as JSON, including tool identities. External attachment bytes are not copied. |

## Local verification

```bash
npm run bootstrap
npm run build
npm run check
npm test
npm run test:sqlite
npm run test:integrity
npm run test:audit
```

The audit regressions use temporary synthetic stores and fake model streams.
They include process interruption, I/O failure, late responses, multi-process
level enabling, legacy event checksums, Unicode reconstruction and a real
no-loader MCP subprocess round trip. A separate clean-source installation test
runs the generated Claude/Codex MCP configurations in empty temporary user
directories, verifies unrelated settings are retained, and checks restart
persistence. A VM test runs the actual panel script
with deferred responses; it is not a real-browser or installed DSH test.

## Installation and configuration

Run `npm run bootstrap` from a clean source checkout before starting an adapter.
It creates only local package links, without downloading dependencies or
altering client configuration. Adapter `init` remains a separate, explicit step.

Checkpoint defaults: `cardTimeoutMs=30000`, `maxEnrichmentJobs=4`. Over-capacity
enhancements are skipped after the deterministic archive has been committed.
Query expansion uses the same deadline and a bounded in-flight count. Providers
that ignore abort may continue upstream work; a local timeout is not proof of
provider cancellation or zero charges.

Digest defaults: `llmTimeoutMs=30000`; `maxLlmCalls` is bounded separately from
`maxBatches` and includes retries across the enabled levels. This is a request
cap, not a verified money limit. Usage is provider-reported where available;
charges stay UNKNOWN without request-level receipts.

## Upgrade and rollback

Stop clients and preserve a matching database **and** record-file backup before
upgrading. New columns/metadata record revisions, block order, term-index state
and compression attempts. Existing event checksums remain readable. FTS rebuild
is atomic; missing term markers are backfilled without treating empty postings
as an unfinished index.

Old format-1 backups remain readable, including explicitly preserved recovery
files. Unfinished transaction journals require review. Downgrade uses the
pre-upgrade backup and its matching code; do not open a newly written database
with an older client and assume full compatibility with new event fields.

Backup requires an empty output directory. Source and output may not contain
each other; restore likewise rejects physical source/target overlap before
creating any coordination files, including through parent aliases. Format-1
restorability accepts only the database, records, cold records and preserved
recovery files.

Restore is an **offline operation**: close all Store handles and stop all clients
first, including idle clients. `--force` permits
replacing a nonempty target, but does not delete the previous directory. The
command reports the retained `TARGET.previous-*` path. Each open Store holds a shared SQLite lease in a persistent sibling
`TARGET.store-lease.sqlite`; restore/recovery require an exclusive lease for
the entire operation. The parent directory must be writable. Keep this
coordination file in place while any client is active. Root aliases and missing
targets resolve through their physical parent/target to the same coordination
identity. Stop old versions before upgrading; no online cross-version lease
migration is provided. Guard states are
published by atomic rename; a sibling restore guard prevents Store operations
during an interrupted exchange. Review its state and
recover explicitly:

```bash
node scripts/memory-backup.mjs verify --dir BACKUP
node scripts/memory-backup.mjs restore --dir BACKUP --to TARGET --force
node scripts/memory-backup.mjs recover --to TARGET
```

Recovery acquires the exclusive lease before inspecting even an incomplete
guard. It may clear an inactive incomplete guard only when the target can be
validated; a missing target is retained for manual review. Recovery retains
candidate and previous directories for inspection. Do not
remove them until the restored data has been checked. Database identity checks
also reject operations from a Store handle opened before replacement. These
tests cover process/I/O interruption, not power-loss durability or arbitrary
external SQLite writers that ignore the offline restore contract.

## Remaining gates

Private security findings need their own evidence and review. Real installed
DSH/Claude/Codex sessions, additional Node/platform combinations, GPU KV,
power-loss durability, full cost receipts and prospective production trials
remain unverified. The public audit's A03–A05 and research stages are not marked
complete by these local engineering changes. No model API call, training,
production trial, deployment or release is part of this candidate.
