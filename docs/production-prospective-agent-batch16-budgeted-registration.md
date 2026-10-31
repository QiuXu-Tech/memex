---
title: Budgeted post-hoc completion of batch 16 blinded review
---

# Budgeted post-hoc completion of batch 16 blinded review

**Registered after original batch 16 outcomes and before these additional calls.** Three of the ten original Qwen ratings were empty or truncated, and all four Gemini adjudications of disagreements were truncated. Original results and calls remain unchanged. The [manifest](assets/benchmarks/production-prospective-agent-batch16-posthoc-budgeted/manifest.json) (SHA-256 `78400b1df37ba56685326e05821a63d12f6a0c2d1920c1ecbfa38e842cb20873`) binds copied original input, candidate, rating and call-log hashes, the selection, the blinded mapping hash and the runner.

The ten reviewable candidates receive new blind labels. Re-review only the three originally truncated Qwen ratings using at most 2,048 output tokens. Retain all originally format-valid DeepSeek and Qwen ratings; no replacement is counted where the new rating is invalid or absent. A new Gemini adjudication at up to 2,048 output tokens is attempted for each pair of valid, different ratings, including the four originally truncated adjudications. There are at most three logical review and seven logical adjudication calls. As in the original registration, retry only explicit HTTP 503, at most twice with logging; do not retry timeouts. Stop launching calls within the stage after a provider failure or missing usage.

These are **post-hoc** results chosen after seeing the failures; they must not replace or erase original planned outcomes. The models share a proxy and model provenance is unverified. Two synthetic format probes succeeded with the larger budget but do not guarantee valid real evaluations. Public issue exposure, common project dependencies, partial checks, short seeded context and adaptive issue selection limit inference; this does not establish production effects, cost savings or autonomous memory management.
