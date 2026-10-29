---
title: SQLite and file consistency
layout: default
---

# SQLite and file consistency

The SQLite consistency fix after v0.14.1 serializes file-backed mutations with
SQLite's writer lock and a five-second busy timeout. A write, cold archive
or restore installs a separate file before committing the index change;
deletion keeps the old file until its index change commits. A per-operation
manifest lets the next writer or a reopened store
finish cleanup or roll back an interrupted operation according to the committed
SQLite path. Existing files are never replaced merely because a move failed.

If an uncommitted write has staged a new body, recovery retains that file under
the store's `.file-recovery/` directory. If an old file changed externally
before cleanup, it is retained there too. Those files may contain private
memory data; backups include them. Record paths can change after an update, so
use the path returned by the store instead of assuming that a previous path
remains current.

A failed write reports its record ID on the error and in the error message.
If commit acknowledgement was lost, inspect that ID before retrying a write
with an automatically generated ID.

For a legacy store already affected by the earlier bug, a missing indexed
body is reported as an error. The store does not guess whether a file in the
other tier is the correct recovery candidate and does not overwrite it.
Preserve the database, WAL/SHM files and record directories before inspecting
such a case.

Backup holds the SQLite writer lock while it reconciles pending operations,
snapshots the database and copies files. Restore checks the manifest and paths
before touching the destination, then rebases indexed paths to the restored
root. These guarantees cover cooperating versions of this store; external
programs modifying files without the lock can still create conflicts.

The recovery tests kill processes at file and commit boundaries and verify
reopening and concurrent operations. They do not establish durability against
sudden power loss or storage hardware failure; the store does not fsync every
file and directory as part of this protocol.
