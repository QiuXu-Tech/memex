---
title: Archive integrity and privacy repairs, 2026-11-02
layout: default
---

# Archive integrity and privacy repairs

These are unreleased changes after 0.65.0. The tests below use local fixtures and injected process or database failures; they do not establish production task accuracy or a cost saving.

- DSH compaction now requires every distinct shadowed sequence before archiving. A partial persistent query can be supplemented from the live buffer. The record, canonical events and completion marker are committed together; unsupported backends skip this archive instead of reporting success. The raw event envelope is retained in SQLite, while `memory_open` exposes a rendered record that can still be clipped. Record-specific canonical event IDs prevent unrelated archives with the same sequence number from overwriting one another.
- A prior completion marker without the new integrity evidence is treated as unverified by the checkpoint path. When the complete original session events are available, a retry replaces it transactionally; otherwise the old record is retained and no new completion is asserted. This is not a bulk audit of existing archives.
- Claude PreCompact copies valid UTF-8 transcripts into ordered, untrusted L2 parts for the actual client session. The part count and SHA-256 support verification; a retry can fill an interrupted copy. When L2 or the actual session id is absent, the hook leaves the source transcript in place and reports a skip. Existing transcripts already copied into L3 are not automatically moved or deleted.
- Detected credential formats in DSH compaction are redirected to L2 or skipped if only L3 is enabled. This heuristic is not a complete privacy filter. Claude's automatic Stop checkpoints also skip these patterns; other sensitive content can still be present in shared memory.
- Explicit adapter level choices now limit the sticky stored settings. An unspecified agent session receives a fresh random id. Project Claude hooks and MCP are pinned to the same configured workspace; user-level setup depends on the hook and MCP process receiving the same working directory. Without a verified host session binding, an MCP server cannot automatically open a hook's private L2 transcript.
- Claude initialization validates existing JSON before writing, retains non-Memex hooks in shared groups, quotes generated shell arguments and registers user-scope MCP under `~/.claude.json`. It stops on conflicting unmanaged Memex server entries. These changes do not retroactively restore overwritten configuration.
- Record reads preserve leading newlines. If `index.db` is missing while record or recovery files exist, opening the store fails instead of creating an apparently empty index. Record files alone cannot reconstruct all canonical events or markers; back up the matching database and files together.

The regression suite covers partial-source retries, legacy marker repair, duplicate event sequences, private cross-session visibility, malformed configuration, long and non-UTF-8 transcripts, and interrupted multipart capture. SQLite fault-injection tests kill a worker after staging, installing and committing a compaction, then check the record, events and marker before retrying. Recovery testing covers process interruption, not sudden power-loss durability.
