# Development assurance v2 — recorded work

This directory records actual zero-service material review and explicitly identified AI-assisted design work. It does not contain new native/model executions, human reviews, author attestations, method-quality results or publication approvals.

## Files and status

| File | Actual content |
|---|---|
| [method.json](method.json) | Development-only revision, exact hashes of the preserved old documents, scope and unchanged human-v1 contract. |
| [policy-sources.json](policy-sources.json) | Official TMLR pages checked on 2026-11-28, concise findings and a clearly marked inference about annotation counts. |
| [drafts.json](drafts.json) | 37 AI-assisted obligation drafts across all 11 original taskpacks; exact public-file and byte-span hashes; no human attestation. |
| [programmatic/summary.json](programmatic/summary.json) | Actual programmatic review counts, zero new execution/human counts and implementation provenance. |
| [programmatic/reviews.json](programmatic/reviews.json) | Per-package integrity, Git blobs, prior JUnit recount, original blank packet audit and synthetic-content facts. |
| [programmatic/report.md](programmatic/report.md) | Readable material review report. |
| [oracle-plan.json](oracle-plan.json) | Executable, partial and still-unmeasured oracle components are identified individually; no overall score. |
| [oracle-drafts/test_flask_request_contract.py](oracle-drafts/test_flask_request_contract.py) | Executable request-derived evaluator test draft, not run on any method artifact. |
| [oracle-drafts/test_requests_request_contract.py](oracle-drafts/test_requests_request_contract.py) | Executable no-network proxy-auth test draft with synthetic credentials; not a complete HTTP-407 reproduction. |
| [history/ANNOTATION.md](history/ANNOTATION.md), [history/SCORING.md](history/SCORING.md), [history/TASKPACKS.md](history/TASKPACKS.md) | Exact pre-revision document bytes; historical descriptions are not current assertions. |
| [verification.json](verification.json) | The actual targeted test result, draft/schema checks and artifact bindings. |

The original 22 human review templates and 11 adjudication templates remain unfilled. Their number arose from an earlier workflow choice; it is not a TMLR task-label requirement or a prerequisite for authorized development collection. There are **11 programmatic material reviews, 37 AI-assisted obligation drafts, 0 completed human reviews and 0 newly accepted research workflows** in this artifact.

Two real source seeds remain candidates for development workflow acceptance after actual task-bound observations and independent behavioral checks. The nine synthetic branches remain synthetic. Both old and newly collected development executions must be reported as development and kept outside scientific result tables until the applicable task and measurement contracts are met.

## Recompute the material review

From the repository root, use a new output directory:

```bash
python -B scripts/paper1/taskpack_review.py \
  --catalog docs/research/p1-evidence-verification/tasks/workflows/catalog.json \
  --drafts docs/research/p1-evidence-verification/artifacts/remaining-completion-01/assisted-review-v2/drafts.json \
  --output /absolute/new-material-review
```

The separate `development_oracle.py` accepts a real experiment-frozen development plan and its original sealed execution state. It reuses the existing seal and observer calculations, emits partial typed diagnostics, and never creates a method composite score. Direct runtime outputs must not be relabeled or given a fabricated experiment ledger to fit this interface. See [ANNOTATION_V2.md](../../../ANNOTATION_V2.md) and [SCORING.md](../../../SCORING.md) for the applicable boundaries.

No new method outputs were read by this reviewer while drafting these request-derived obligations and tests. The assistant had prior access to the task designs and source-reproduction evidence; this exposure is disclosed and is not called independent human blinding.
