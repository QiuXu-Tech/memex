# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's private vulnerability reporting:

1. Open the repository's **Security** tab → **Report a vulnerability** (or <https://github.com/QiuXu-Tech/memex/security/advisories/new>).
2. Include: affected version/commit, DSH and Node versions, a minimal reproduction, and the impact you expect.
3. Never include real archived transcripts, credentials, or personal data in a report — reproduce with synthetic fixtures under `/tmp`.

We aim to acknowledge reports within 5 business days and to publish an advisory with the fix. Supported versions: the latest `0.1.x` release line.

## Scope notes

- memex is a local plugin: it stores data under `$DSH_HOME/memories` and makes no network calls beyond the DSH model provider you configure. No telemetry.
- L3 archives are intentionally shared across sessions in the same working directory; treat enabling L3 as a data-sharing decision. Sensitive-looking spans are forced into the private L2 pool (or eviction is skipped when only L3 is available), but the detector is a heuristic, not a DLP system.
- Backup files contain raw conversation data; protect them like transcripts.
- The `memory_search`/`memory_open` tools expose archived content to the model as **data**, and the memory manual instructs the model to treat it as such. Prompt-injection via archived content remains a general LLM risk.
