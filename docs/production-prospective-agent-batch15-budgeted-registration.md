---
title: Budgeted post-hoc blinded re-review of batch 15
---

# Budgeted post-hoc blinded re-review of batch 15

**Registered after the original results and before these additional calls.** The earlier [post-hoc registration](production-prospective-agent-batch15-posthoc-registration.md) was not run. Subsequent batch 16 reviews showed reasoning models can consume the whole 700-token output allowance and return no final rating; two separate synthetic probes returned parseable ratings at 2,048 tokens. The new [manifest](assets/benchmarks/production-prospective-agent-batch15-posthoc-budgeted/manifest.json) (SHA-256 `9430517916f1cd26d9787254d1f5ba605950b450169f68179cd78e52998434f4`) replaces that unrun plan before any of its calls. It binds the original results, source files, rubric, schedule, and the following limits.

All three reviewable candidates are freshly blinded and reviewed again by DeepSeek and Qwen. Qwen and the Gemini adjudicator each receive at most 2,048 output tokens; DeepSeek retains 700. At most six logical reviews and three disagreement adjudications will be launched, with only explicit HTTP 503 eligible for at most two logged retries. No timeout is retried. Stop the stage on provider failure or missing usage. The fourth original attempt remains unreviewable.

This is a post-hoc, model- and budget-adjusted analysis, not a replacement for the originally registered outcomes. Original invalid ratings and failed calls stay visible. AI model provenance through the common proxy is unverified; shared models, short public issue histories, partial checks, adaptive issue selection, and potentially exposed solutions limit inference. No conclusion about production effectiveness or savings follows from this assessment alone.
