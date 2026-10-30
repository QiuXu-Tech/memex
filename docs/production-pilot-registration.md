---
title: Exploratory production-validation pilot registration
layout: default
---

# Exploratory production-validation pilot registration

This registration precedes the pilot's real-history model calls. It defines an **isolated retrospective replay**, not a live production trial; no conclusion about production efficacy, cost savings or reliable autonomy is planned from this pilot. The source repository is commit [`99a9917`](https://github.com/QiuXu-Tech/memex/commit/99a9917195ed1478f1356b36683a22c8dcbb478b). The private frozen manifest, including the randomized arm order and hashed source identities, has SHA-256 `bd87eecc435d212acab855a067336aa4e4fdeb0fcff6ad71948860ffb51350bd`. The assignment key and real conversation content are not public.

The pilot uses four actual historical user questions from two time-cutoff sessions: three from the Memex-related session and one from another session. Two of the explicitly Memex-named questions were not among the ten questions in the prior replay; neither the sessions nor the task pool are independent of development or representative of production. The corresponding real user/assistant history is capped at 40 earlier messages, with each indexed message body clipped at 1,800 characters. The last four earlier chat messages and latest available earlier compaction summary (up to 6,000 characters) are supplied to every arm. The cutoff excludes later events; The initial registration incorrectly repeated the previous report’s claim of ten malformed lines. **Correction:** the frozen manifest and the pilot’s newline-based parser found zero invalid JSONL lines in either source. The older extractor used `splitlines()`, which treated Unicode separators inside valid JSON strings as line breaks and produced ten invalid fragments; that earlier replay may have omitted affected events. Sensitive-looking credential strings are redacted before a provider call. Historical text is untrusted data.

Each task is evaluated in five isolated arms. Run order is randomized independently within each task with fixed seed `20261031`:

1. Recent tail and actual earlier summary.
2. Same baseline plus a simple independent keyword search/open over the earlier archive.
3. Same baseline plus the Memex pager's bounded automatic window, without agent tools.
4. The pager plus Memex search/open, with writes disabled.
5. An initially empty Memex store: the agent sees earlier messages in chronological batches **before it sees the question** and may decide whether to write; at question time it receives the pager and may call search, open or write.

Readonly memory arms index the same earlier chat archive directly; the write-enabled arm builds its own memory from that archive. This makes the lifecycle observable but changes initialization and cost, so the groups are **not a clean causal comparison of autonomous writing cost or completeness**. The pager uses a 1,800-token chars/4 budget and 400-token page cap. Models use Claude Haiku 4.5 via the configured gateway at temperature 0, with up to 2,500 output tokens for the answer and 1,000 for each intake call. A run has at most three intake batches, three intake tool rounds per batch, five answer tool rounds, and 12 total memory writes. Failures, empty responses, limits and rejected tool calls remain in the denominator; no silent retries.

At the user's direction, GPT-6 Astra and DeepSeek Flash will separately score each nonempty anonymous answer against time-prior evidence, using correctness, coverage and evidence support on 0/1/2 or UNKNOWN. They will not receive arm labels or competing answers. The machine reviewers see excerpts capped at 1,000 characters per archived message; they are neither independent human raters nor a substitute for full-evidence review. Disagreement, invalid responses and UNKNOWN are reported; no gold labels are inferred from either model. Tool traces separately record memory writes, search, opens, pager inputs and failures, and do not by themselves prove a faithful or necessary lifecycle.

Capture all gateway-reported usage, including cached tokens where provided, request and response bytes, per-call latency, local CPU and storage, failures and tool-call counts. Actual invoiced costs, initial historical capture costs, human labor and provider discounts remain `UNKNOWN` unless independently supplied. The gateway tool-connectivity checks use synthetic data and must be counted separately from the pilot. Full private prompts, source evidence, answers, tool traces and blinded review sheets remain local.

**Execution note:** after repeated empty DeepSeek reviewer outputs, GPT-6.1 Sol was added as a post-hoc replacement and the original calls were retained. An additional unblinded machine audit of all write-enabled traces was also added after preliminary observation; neither addition was in the original frozen manifest. Results and separate usage are in the [pilot report](production-pilot.md).
