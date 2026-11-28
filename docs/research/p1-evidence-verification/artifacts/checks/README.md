# Engineering verification evidence

These files record implementation and environment checks, not paper effect estimates. They must not be included as independent research tasks, successful model continuations, or additional pilot samples.

- `baseline-suite.txt`: the unchanged repository suite. Its summary counts 197 total cases, including four skips because the generated bundle was not built: 193 executed passes, zero failures.
- `paper1-suite.txt`: the final combined `npm run test:paper1` output; the execution ledger reports its observed test counts.
- `verification.json`: exact commands, exit codes, environment and tested source hashes.
- `host-preflight*.json`: zero-model-turn local-host failures at initialization. The managed runtime was read-only; the study did not modify credentials, runtime permissions or managed controls to bypass the failure. An existing authorized Mac host was used instead.
- `rawrag-runtime-check.json`: retained first offline dependency check, blocked by missing SOCKS support in the isolated environment. The final check and dependency lock are recorded separately; this original failure is not overwritten.
- `rawrag-preflight.json`: official upstream/config/dependency/credential-presence check, with zero model requests. Missing credentials remain a baseline execution blocker.
- `rawrag-runtime-check-final.json` and `rawrag-requirements-resolved.txt`: the bounded offline runtime check and its resolved package versions. A passing offline check is not an embedding, reranking or quality result.
- `review-fixes-red.tap`, `native-receipt-red.txt`, `fork-warning-red.txt`: retained failing regressions before the corresponding fixes. They document development history, not unresolved failures in the final tested code.

Local absolute workspace paths in the copied logs are replaced with `<REPO>` or `<WORKSPACE>`, and user-home paths with `<USER_HOME>`. Trailing whitespace in the copied failing-regression console log is removed for repository whitespace checks. Timing and native test IDs are retained. The separately archived native JSONL and test stdout are not changed by this console-log normalization. No credential files are copied.
