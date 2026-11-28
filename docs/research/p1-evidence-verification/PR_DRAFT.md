# Proposed draft pull request

Status: **prepared locally; not created**. Publishing to the public repository was blocked by automatic approval review pending explicit user authorization.

- Repository: `QiuXu-Tech/memex`
- Base: `main`
- Head: `research/p1-evidence-verification`
- Draft: `true`

## Proposed title

research(p1): add evidence verification prototype and methods manuscript

## Proposed body

The existing synthetic evidence-gate experiment uses predefined claims and convenient source locations. It cannot establish automatic claim discovery, robust current-state verification, or incremental benefit over strong raw-history retrieval. This research branch prepares the first paper's auditable implementation and evaluation protocol.

### Changes

- Add a separate P1 prototype: observable-input claim contract, real Memex L2 originals, typed verification, trusted source-head commitment, and conservative reuse checks.
- Add a narrow native Node/TAP normalizer and a bounded native-compaction smoke runner. Preserve failed attempts and the successful resumed continuation with path-redacted event logs.
- Replay the two actual terminal test events through real storage and verification. Export identical public-source archives accepted by both method interfaces. Raw-RAG retrieval itself remains unrun.
- Pin official Raw-RAG commit/configuration and exact tokenizer, add bounded retrieval and a zero-request runtime diagnostic, and preserve dependency and credential-presence reports.
- Add task-level analysis with failure-inclusive denominators, separate quality/cost validity, project/task bootstrap and gated H1/H2 criteria, plus research schemas and execution documentation.
- Include a 21-page English methods/protocol working manuscript, editable sources, references and build instructions. Result cells remain explicitly PENDING.

### Validation

- `npm run test:paper1`: 41 Node tests and 74 Python tests passed; no failures or skips.
- `npm test`: 193 executed passes and four generated-bundle skips; runner reports 197 total cases.
- Official Raw-RAG constructor, cached tokenizer and transport-hook attachment checks passed with zero model requests, dispatches or network attempts. Provider HTTP behavior was not exercised.
- One synthetic native workflow completed actual compaction and resumed continuation. The current changed artifact failed its test, the release marker remained absent, and source/test files were not repaired.
- Final local source hashes, whitespace checks, relative artifact links, document build and path/credential-pattern checks were recorded.

### Research limits

This is a research draft, not a completed empirical paper or production-ready deployment. The archive assumes trusted complete normalized snapshots. Live object-state binding, general lifecycle parsing, natural-task extraction quality, new independent task acquisition and annotation, faithful provider retrieval, paired pilot, formal sample size, total-budget matching and confirmatory results remain outstanding. Historical authorization checks never authorize execution. The original experiment files remain unchanged for reproducibility.

The branch contains unpublished manuscript and research material. No conference/journal submission, public preprint or main-branch merge is requested by this draft PR.
