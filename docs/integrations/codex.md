---
title: OpenAI Codex
layout: default
---

# OpenAI Codex

```bash
node packages/dsh-memory-codex/bin/cli.mjs init --model gpt-5-codex --write-config
# or print the config only:  node packages/dsh-memory-codex/bin/cli.mjs config
```

Codex has **no hook surface**, so the integration is:

1. **MCP server** for tools. `--write-config` appends (and backs up) `~/.codex/config.toml`:

   ```toml
   [mcp_servers.dsh-memory]
   command = "/path/to/node"
   args = ["/path/to/packages/dsh-memory-mcp/bin/server.mjs", "--root", "/Users/you/.dsh-memory", "--agent", "codex", "--model", "gpt-5-codex", "--levels", "l3"]
   ```

   Equivalent one-liner: `codex mcp add dsh-memory -- node <server.mjs> --root ~/.dsh-memory --agent codex --model gpt-5-codex --levels l3`

2. **AGENTS.md** manual in the project: tells Codex when to search/open/write memory, with the profile-tuned budget guidance.

Because there is no transcript hook, capture happens when the agent calls `memory_write` (the manual instructs it to write durable decisions/facts). For verbatim transcript archiving in Codex, run the MCP server in the same root and let the agent call `memory_write` with the span, or use a wrapper script that pipes the session log into `memory_write`.
