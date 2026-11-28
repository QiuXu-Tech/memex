# P1 Raw-RAG baseline: implementation and runtime evidence

## Current status

The **constructor-only runtime check passed on 2026-11-28 (Asia/Shanghai)**, using Python
3.12.14 and the official Raw-RAG checkout pinned below. It constructed the real
`RAGAdapter`, loaded the exact tokenizer from its verified local cache, and
attached the P1 transport instrumentation to the installed SDK. The report
records **0 model requests, 0 observed dispatches, 0 attempted network operations,
and no calls to `add`, `search`, or `answer`**.

The actual embedding and reranker credential variables were both absent. The
check inspected variable names only; it did not retrieve credential values or
read `.env`. **Formal Raw-RAG retrieval, provider connectivity, ranking quality,
the shared reader, task outcomes, and the performance pilot remain untested.**
Runtime readiness does not establish that the formal baseline has passed.

The earlier failure is preserved in
[rawrag-runtime-check.json](artifacts/checks/rawrag-runtime-check.json). It reported
a missing `socksio` dependency while constructing the SDK's SOCKS-aware client.
Installing `socksio==1.0.0` in the separate virtual environment resolved that
failure. No proxy setting was removed, changed, or bypassed.

Preserved artifacts and reproducible local dependencies:

| Artifact | Path |
| --- | --- |
| Runtime result | [runtime report](artifacts/checks/rawrag-runtime-check-final.json) |
| Frozen installed package inventory | [package inventory](artifacts/checks/rawrag-requirements-resolved.txt) |
| Official checkout | External checkout at the pinned commit; recreate using the commands below |
| Isolated Python environment | Separate Python 3.12 environment; recreate from the preserved package inventory |

The requirements file SHA256 is
`9756c03efe4ea45289fc86a4a9b272873fbcd30a9443a8853ff39aaea73f577a`.
The report also records the check-script hash, canonical baseline-config hash,
source verification, interpreter version, tokenizer identity and hook results.
This is an installed-version inventory, not a wheel-hash or container-image lock.

## Official implementation and retained behavior

Repository: [Litmeb/RAW-RAG](https://github.com/Litmeb/RAW-RAG).
Pinned commit: [`95639191e9547219b426710e50fe1a36235e26fc`](https://github.com/Litmeb/RAW-RAG/tree/95639191e9547219b426710e50fe1a36235e26fc).
The adapter checks this commit, a clean tracked worktree, the checkout root and
nine pinned source/configuration files before importing the official adapter.

The P1 retrieval entry point is `scripts/paper1/rawrag_adapter.py`; its fixed
configuration is `scripts/paper1/rawrag-config.json`. Its model/profile choices
come from the official [textemb3/gpt4omini paper profile](https://github.com/Litmeb/RAW-RAG/blob/95639191e9547219b426710e50fe1a36235e26fc/scripts/paper/configs/systems/textemb3-gpt4omini.yaml)
and [adapter implementation](https://github.com/Litmeb/RAW-RAG/blob/95639191e9547219b426710e50fe1a36235e26fc/methods/EverCore/evaluation/src/adapters/rag_adapter.py).

| Component | Frozen P1 setting |
| --- | --- |
| Query | Original user request, unchanged |
| Chunking | 256 `gpt-4` tokenizer tokens, overlap 32 |
| Tokenizer | `cl100k_base`; word fallback is forbidden |
| Embedding | `text-embedding-3-small`, dense top 128 |
| Reranker | `rerank-v3.5`, final local top 15 |
| Rerank HTTP response | Scores for every candidate; the upstream requests `top_n=len(candidates)` |
| Display expansion | `expand_turns_on_display=true` |
| Repeated turns | Preserved: `dedup_turns_on_display=false` |
| Storage | Official local per-conversation index |
| Reader | External shared native host; this entry point does not call the upstream reader |

The implementation directly invokes the official `RAGAdapter.add/search` only
when the separate retrieval command receives explicit `--run`. No BM25, lexical
ranking, synthetic embedding or simulated model output substitutes for Raw-RAG.
The root upstream license is [MIT](https://github.com/Litmeb/RAW-RAG/blob/95639191e9547219b426710e50fe1a36235e26fc/LICENSE);
the nested [EverCore package metadata](https://github.com/Litmeb/RAW-RAG/blob/95639191e9547219b426710e50fe1a36235e26fc/methods/EverCore/pyproject.toml)
separately declares Apache-2.0. Third-party data and service terms are separate.

## Zero-request runtime check

`scripts/paper1/check_rawrag_runtime.py` is a separate, more invasive diagnostic
than the retrieval CLI's default `--check`. It imports dependencies and constructs
the upstream class but does not perform retrieval. Its temporary configuration
uses fixed non-secret dummy keys and only `http://127.0.0.1:1` endpoints, including
the unused reader client. It leaves the baseline configuration file unchanged.

During runtime imports and construction, a Python audit guard rejects network
connections/DNS, outgoing UDP, HTTP request events, child processes and `.env`
access. A temporary environment view hides credential variables without reading
their values, while forwarding proxy settings unchanged. In-memory guards also
reject upstream `add/search/answer` calls. The real upstream constructor, real
SDK client classes and real tokenizer are used. No local HTTP server or model
stub is involved.

This installed `openai==3.60.0` uses `httpx2==2.16.2`. The check verifies that the
actual client's request/response hook lists accept the P1 hooks, SDK retries can
be set to zero, redirects are disabled, and the rerank transport wrapper is
installed. **It does not exercise those hooks over HTTP or authenticate a provider.**

The executed invocation has the following form, with machine-local paths replaced by explicit placeholders:

```bash
cd /absolute/path/to/memex
/absolute/path/to/p1-rag-env/bin/python -B \
  scripts/paper1/check_rawrag_runtime.py \
  --upstream /absolute/path/to/RAW-RAG \
  --output /absolute/path/to/new-runtime-report.json \
  --requirements-output /absolute/path/to/new-package-inventory.txt
```

It exited 0. Use new output filenames to repeat the check: existing reports and
requirements files are never overwritten. Any runtime failure exits 2, records
a sanitized error, and does not fall back to another tokenizer or model.

The tokenizer cache must already contain the public `cl100k_base` vocabulary.
The check does not download it. It verifies these identities before loading:

| Property | Value |
| --- | --- |
| Public data | `https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken` |
| Cache filename (SHA1 of URL) | `9b5ad71b2ce5302211f9c61530b329a4922fc6a4` |
| Data SHA256 | `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7` |
| Encoding vocabulary size | 100277 |
| Known local encoding check | `hello world` → `[15339, 1917]` |

It respects `TIKTOKEN_CACHE_DIR`, then `DATA_GYM_CACHE_DIR`, then the tokenizer's
default temporary `data-gym-cache` directory. For a fresh environment, obtain
that public vocabulary file through the normal configured network path, verify
the SHA256, and place it under the exact cache filename before running this
offline check. A missing/mismatched cache fails closed.

## Reproducing the isolated environment

Use Python 3.12 and a new virtual environment. Save the following complete
installed-package inventory as a requirements file; it includes the package
installer version. Installing public packages or preparing the tokenizer cache
is a separate setup step, not part of the zero-network runtime diagnostic.

```text
annotated-types==0.8.0
anyio==4.16.0
certifi==2026.11.20
charset-normalizer==3.5.3
h11==0.16.0
httpcore2==2.16.2
httpx2==2.16.2
idna==3.20
jiter==0.19.0
markdown-it-py==4.3.0
mdurl==0.1.2
openai==3.60.0
pip==25.0.1
pydantic==2.14.4
pydantic_core==2.50.5
Pygments==2.21.0
PyYAML==6.0.4
regex==2026.11.25
requests==2.34.2
rich==15.0.0
sniffio==1.3.1
socksio==1.0.0
tiktoken==0.14.0
tqdm==4.70.1
truststore==0.10.5
typing-inspection==0.4.5
typing_extensions==4.16.0
urllib3==2.8.0
```

Example setup commands, using new destination paths:

```bash
python3.12 -m venv /absolute/path/to/new-p1-rag-env
/absolute/path/to/new-p1-rag-env/bin/python -m pip install \
  -r /absolute/path/to/rawrag-runtime-requirements.txt
/absolute/path/to/new-p1-rag-env/bin/python -m pip check
git clone https://github.com/Litmeb/RAW-RAG.git /absolute/path/to/new-RAW-RAG
git -C /absolute/path/to/new-RAW-RAG checkout --detach \
  95639191e9547219b426710e50fe1a36235e26fc
```

`pip check` reported no broken requirements in the checked environment. These
packages cover the direct local-storage retrieval adapter and this diagnostic;
they are not a claim that the entire official benchmark runner, PostgreSQL
backend, every data loader or every alternate model profile is installed.

## Formal retrieval remains a distinct step

The metadata-only preflight command performs no tokenizer/client construction:

```bash
/absolute/path/to/p1-rag-env/bin/python -B scripts/paper1/rawrag_adapter.py \
  --check --upstream /absolute/path/to/RAW-RAG
```

It remains blocked without `VECTORIZE_API_KEY` and `RERANK_API_KEY`. The CLI does
not load `.env`. Its availability fields do not establish provider access.

The following is the future real-retrieval command, **not executed in this batch**:

```bash
/absolute/path/to/p1-rag-env/bin/python -B scripts/paper1/rawrag_adapter.py \
  --run --upstream /absolute/path/to/RAW-RAG \
  --archive /absolute/path/to/public-archive.json \
  --request /absolute/path/to/original-request.txt \
  --output /absolute/path/to/new-retrieval-output \
  --display faithful
```

The archive contains `schema`, `taskId`, `snapshot:{cutoff,watermark,complete}`
and `sources`. Each source carries its original text and shared public transport
metadata. The same fields must reach all comparison arms, including `actor`,
`action`, `effectiveAt`, `expiresAt`, `testCount`, `skippedCount`, `todoCount`
and `parserVersion` when present. Gold, proposed claims, expected-source labels
and answer annotations are rejected. Source observations after the snapshot
cutoff are rejected before indexing. These public metadata semantics remain
ingestion assumptions, not an unrestricted natural-log parser.

`faithful` preserves complete turn-expanded text and fails if the safety output
cap is exceeded. `budget-matched` applies the frozen 5000-token prefix rule
**after the same full turn expansion**, with an explicit truncation marker and
hashes for both expanded and delivered text. It never silently disables
expansion. Runtime changes from the paper runner are declared: one conversation
and query, concurrency one, no SDK retries/redirects, bounded requests/session,
and no upstream reader call. Upstream application retries remain enabled.

Default limits include one session, 16 observed HTTP dispatch attempts, 180
session seconds, 30 seconds per request, 65000 raw input reference tokens and
300000 processed input reference tokens. File, event, source-text and output
caps also apply. The cost ledger separates transport observations, upstream log
events and returned provider usage. Unknown full HTTP totals and provider cost
are `null`; log rows are never treated as a complete HTTP census.

## Local regression verification

```bash
python -B -m unittest discover -s test -p 'test_paper1_rawrag*.py'
```

All **38** tests passed: 34 retrieval/input/budget contracts and four new runtime
safety tests. The new tests first failed before the diagnostic existed, then
passed; they verify that credentials are not read, proxy values pass through,
network and `.env` access are blocked, and a missing tokenizer cache cannot
trigger a download. Cross-arm tests exercise the actual Node normalizer, real
L2 archive and both verification modes before passing the same public source to
the Raw-RAG validator. These are implementation checks, not model-quality or
paper-effect measurements.
