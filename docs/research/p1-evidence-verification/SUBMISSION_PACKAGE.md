# P1 official-format submission preparation package

**NOT READY — NOT SUBMITTED.** Document-format preparation is complete for the recorded working-paper version. It does not establish scientific readiness, human authorship, or compliance with the unresolved human-origin condition. No OpenReview submission, editor message, cover-letter delivery, or author declaration has been made. Status narrative updated **2026-11-29 (Asia/Shanghai)**; the manuscript, PDFs and document-source ZIP were not rebuilt or modified in this update.

The canonical research document remains [manuscript.md](manuscript.md). The new TMLR derivative is separate and is regenerated only when the canonical record is deliberately updated. The earlier [submission plan](SUBMISSION.md) remains the broader readiness assessment.

**All four authorized supplemental native attempts have ended, without a valid task-bound checkpoint.** Two stopped before any provider dispatch; the two Requests preparations each completed five DeepSeek calls and seven read-only public-tool calls before the sixth request was rejected locally by the cumulative reference-input budget. Their five generation starts were also exhausted. No files were written, no tests or reviews were run in those preparations, and none of the sixteen method units was dispatched or scored. All backends are closed; attempts are neither refunded nor automatically replenished. The final [execution record](artifacts/native-supplement-01/observations.json) and [status summary](REMAINING_WORK.md) retain the failures, known token counters and unknown actual spending.

The fixed Raw-RAG Git checkout and its isolated private runtime binding are verified. [Development-assurance v2](ANNOTATION_V2.md) has completed 11 package reviews with 37 explicitly AI-assisted obligation drafts. The 22 blank human-v1 forms are not a prerequisite for development. Neither the new draft labels nor a successful engineering check establishes formal gold, an accepted research task, or a measured method effect. This completed round of execution does not establish successful native preparation or permission for another attempt.

The [execution evidence index](artifacts/native-supplement-01/README.md) records deployment, accounting and original-versus-redacted export boundaries. The [next-step design diagnosis](NATIVE_NEXT_STEP.md) records the joint preparation constraints without changing a configuration, budget or grant.

The [reference-source qualification](artifacts/remaining-completion-01/oracle-qualification-01/README.md) has now actually tested two bounded behavioral oracles: five pytest cases for Flask and five for the explicit-URL Requests v2. It retains 15 observer executions, five real isolation probes and an independently checked 282-record export. The original six-case Requests draft still has its observed fixed-source failure; the v2 revision and reduced scope are explicit. These tests qualify reference behavior and rejection controls, not the final artifacts of a method arm or a complete scientific endpoint.

## 1. Files and their purpose

| File or directory | Purpose | Submission status |
|---|---|---|
| `submission/tmlr-review/main.pdf` | Actual PDF compiled with the pinned official default review style. | NOT READY; not submitted. |
| `submission/tmlr-review/main.tex`, body fragments, and `references.bib` | Editable, buildable review-format sources; the project-specific legacy citation is explicitly anonymized. | Document source, not a complete study artifact. |
| `submission/tmlr-review/tmlr.sty`, `tmlr.bst`, `fancyhdr.sty`, `upstream/` | Unmodified official files and retained upstream notices/sample. | Third-party template files; not author identities for this paper. |
| `submission/tmlr-review/style-provenance.json` | Official repository commit, blob identities, and original SHA-256 values. | Provenance for format reproduction. |
| `submission/tmlr-review/build.py` and `build-report.json` | Compilation, pinned-file verification, and recorded compiler checks. | Engineering validation only. |
| `submission/derive.py` and `derivation.json` | Controller-side mapping from the canonical manuscript to the review derivative. | Excluded from the anonymous source ZIP because the mapping identifies the original project. |
| `submission/review-source.zip` | Frozen document-source archive with a manifest and retained licenses. | Candidate supplement; NOT READY, not uploaded. |
| `submission/supplementary-manifest.json` | Included files plus explicitly excluded or unfinished study-material categories. | Does not claim a complete supplementary research package. |
| `submission/qa-report.json` | PDF dimensions, citations/placeholders, metadata/link screening, rendering, and visual-review record. | Document QA, not venue acceptance. |
| `submission/batch1-manuscript-sync.json` | Binds the added development observations to retained records and verifies unchanged formal sections. | Development provenance; no new paired effect result. |
| `submission/zip-rebuild-report.json` | Actual extraction and recompilation outside the project directory, with page/text/pixel comparison. | Document reproduction only; no research outcome reproduced. |
| `submission/policy-provenance.json` | Five official policy-page retrieval records with dates and hashes. | Rules were checked; account/form eligibility was not. |
| `submission/COVER_LETTER.md` | Substantive cover-letter draft with honest missing-evidence fields. | NOT SENT; whether a letter field is required remains unverified. |
| [CONTRIBUTIONS.md](CONTRIBUTIONS.md) | Human-origin, authorship, contribution, and AI-use worksheet. | Unfilled factual declarations; excluded from anonymous sources. |

Files that require the final build are generated by the commands below; their current hashes and completion state are recorded in the build and QA reports. No filename alone establishes that a gate has passed.

## 2. Official format and current requirements

The style is pinned to official commit [`7bf90efe3a0debbba703c05c43f3ff7e4d4a2992`](https://github.com/JmlrOrg/tmlr-style-file/tree/7bf90efe3a0debbba703c05c43f3ff7e4d4a2992), which was also the upstream checkout's HEAD when retrieved. The package uses `\documentclass[10pt]{article}` and `\usepackage{tmlr}`, with neither `accepted` nor `preprint`. The upstream default fixes US Letter, text dimensions, fonts, and review labels. We do not import the canonical document's A4 geometry, 11-point setting, font overrides, or custom header. [T1]

The default style prints “Under review” labels even in a local build. To avoid a false submission claim, the first page visibly states **NOT READY — NOT SUBMITTED** and explains the template labels. This is manuscript content; the official style file is unchanged.

Current rules relevant to this package were independently checked:

| Topic | Verified preparation implication | Source |
|---|---|---|
| Standard PDF route | Use the official LaTeX template; avoid changes to the mandated layout. | [T1][T2] |
| Length | No fixed page limit is specified. Long papers need justified length; the FAQ says main text over 12 pages can take longer to review. | [T3][T4] |
| Anonymous material | The review manuscript and supplements must be anonymous. Human OpenReview profiles and submission metadata are separate. | [T3] |
| Supplements | PDF or ZIP, at most 100 MB, directly supporting the work; appendix/supplement reading is discretionary. | [T3] |
| AI and human responsibility | Editorial policy allows assistance and excludes LLM authors. The FAQ still requires first-page disclosure and expresses the human-sourced expectation. | [T4][T5] |
| Claims and evidence | Formatting and local engineering checks do not satisfy the criterion that claims have convincing, clear support. | [T6] |
| Licensing and publication | The journal's submission license applies when a paper is submitted; it does not grant rights to every third-party artifact. This preparation has not submitted the draft. | [T3] |

The FAQ and editorial policy are reported together rather than silently treating one as a waiver of the other. The present package has not established the human origin of its ideas, claims, and results. The [contribution worksheet](CONTRIBUTIONS.md) asks for actual work records; a filled signature field or a rewritten disclosure cannot substitute for them.

The official template repository's Apache 2.0 license is preserved. The bundled `fancyhdr.sty` has a separate LPPL 1.3-or-later notice, also retained. No blanket license is assigned here to upstream issue text, research data, or dependency code. [T1]

## 3. Regenerate and compile

From the repository root, regenerate only the derivative:

```bash
python3 docs/research/p1-evidence-verification/submission/derive.py
```

This reads the canonical Markdown and bibliography, records their hashes, keeps the scientific text and all `PENDING` markers, strips the custom layout metadata, uses native section numbering, and generates natbib/BibTeX sources. It removes the direct identifying legacy-project citation/link and withholds the exact legacy commit in the review prose. The non-anonymous canonical files remain unchanged by this derivation. It also permits a long source filename to break at punctuation and adds content-level guards against isolated page-bottom headings; neither operation shrinks a font or changes an official style dimension.

With a complete TeX installation:

```bash
cd docs/research/p1-evidence-verification/submission/tmlr-review
python3 build.py
```

The preparation container has the TeX packages but lacks generated format/font-map state. Its reproducible local command is:

```bash
python3 build.py --isolated-format \
  --texmf '{/usr/share/texlive/texmf-dist,/usr/share/texmf,/etc/texmf,/var/lib/texmf}' \
  --font-map /usr/share/texmf/fonts/map/dvips/lm/lm.map \
  --font-map /usr/share/texlive/texmf-dist/fonts/map/dvips/amsfonts/cm.map \
  --font-map /usr/share/texlive/texmf-dist/fonts/map/dvips/amsfonts/symbols.map \
  --keep-build
```

The temporary format and font maps change build-environment indexing, not the official typography. No system TeX configuration is modified. The initial missing-font-map failure is preserved in `submission/build-logs/` and `build-attempts.json`. A successful compilation is not a human verification or a submission.

`build.py` runs LaTeX, BibTeX, and enough LaTeX passes to resolve the bibliography and references. It verifies original template bytes before compilation and records source/output hashes. Generated `main.bbl` permits inspection of the rendered reference records. A future canonical update requires another explicit derivation, build, QA, and source-archive freeze; an old PDF must not be silently presented as representing new outcomes.

After compilation, run the QA controller from the repository root:

```bash
python3 docs/research/p1-evidence-verification/submission/qa.py \
  --render-dir /tmp/p1-tmlr-review-pages
```

Inspect the rendered pages and record the actual observations, inspected pages, and reviewer in `submission/qa-report.json`. The script deliberately leaves visual review incomplete; it cannot substitute text extraction for viewing the pages. Only after that review is recorded as `INSPECTED`, freeze the document-source archive:

```bash
python3 docs/research/p1-evidence-verification/submission/package.py
```

The archive command refuses a changed canonical source, changed compiled sources, changed PDF, or changed package member after QA. Its output is a locally prepared ZIP, not an upload. To reproduce the package check, extract the ZIP into a new directory and run the included `build.py` there with the documented TeX command.

## 4. Supplement scope and review boundary

The current ZIP is a **document-source package**. It contains the review PDF, editable TeX/Markdown fragments, anonymous bibliography, pinned official assets/notices, compilation script, and a per-file inventory. It reproduces the format draft without needing the original project repository or controller-side derivation records. It does not execute a model, create host sessions, or recompute a study effect.

The supplementary manifest separately inventories available development/protocol materials and outstanding research categories. Original project links, controller provenance, this human worksheet, cover-letter placeholders, evaluator/gold material, source clones with future history, credentials, and complete raw third-party datasets are excluded from the review-source ZIP. Exclusion is not a claim that all other material has passed rights or anonymity review.

A completed scientific supplement still needs an immutable code/configuration snapshot, accepted workflow definitions, public/evaluator separation, a validated and frozen label/oracle contract with independent truth evidence, all scheduled first attempts and failures, actual delivered evidence, reproducible outcome analysis, usage reconciliation, and the permitted release/access mechanism. Existing developer tests, source candidates, environment qualifications, and host/component smoke records retain their own scope. The current v2 programmatic checks and AI-assisted drafts remain development material; their unmeasured semantic and hidden-behavior components cannot be relabeled as formal gold or outcomes.

## 5. QA and readiness are different

Document QA checks the official file hashes, US Letter page size, first-page status and AI footnote, preserved references and result placeholders, PDF metadata, direct identifying links, compilation warnings, and rendered layout. A mechanical string scan cannot establish anonymity or detect every identifying narrative detail. A self-contained build cannot establish the truth of a scientific claim.

The canonical manuscript is retained as the expanded research record. This official-template derivative has not yet been condensed into a final findings-led paper. No page target justifies deleting necessary evidence, hiding failures, narrowing a denominator after observing results, or altering the official typography.

### Completed checks for the unchanged PDF/ZIP revision

| Check | Observed result |
|---|---|
| Canonical expanded working PDF | 26 A4 pages; references page 22; appendices pages 23–26. |
| Official default-review PDF | 27 US Letter pages; references pages 21–22; appendices pages 23–27. |
| References and result placeholders | Both PDFs retain 16 references and all 56 `PENDING` markers. |
| Compiler diagnostics | Both have zero undefined citations, missing characters, overfull boxes, or unresolved rerun requests. Nonfatal underfull warnings: canonical 8, official 0. |
| Rendering | All 53 pages rendered at 110 dpi and inspected in contact sheets, with full-page checks of new observations, source tables, first-page status, formulas and code. The official final page has one complete table row and its repeated header; the white space is recorded in QA. |
| Official assets | All six copied official/template-notice files match the pinned SHA-256 records; their inherited whitespace is preserved. |
| Anonymous-source screening | Known direct project-owner identifiers, private path prefixes, and the legacy commit were absent from the review PDF text/metadata/links and included text source members. Human anonymity review remains unrecorded. |
| Frozen document-source ZIP | 22 members; 462,960 compressed bytes and 664,991 uncompressed bytes; member bytes and ZIP integrity verified. |
| Independent extracted build | Succeeded outside the project directory using only the ZIP and installed TeX dependencies; all 27 page texts, dimensions, and rendered pixels matched. |

The last PDF update added the earlier bounded native retry observations and separate clean public-base test captures. It retained the earlier approval rejection, recorded the observed one-call approvals truthfully, and did not promote the timed-out changed continuation to a whole-run pass. That revision's abstract, formal result section, limitations and conclusion remained unchanged. The later DeepSeek/supplemental execution records, wire repairs and v2 review materials are separate engineering artifacts; this status edit has not silently inserted them into the existing PDF or source ZIP. A later findings-led manuscript must deliberately incorporate the actual evidence and regenerate the package.

PDF byte identity is not asserted: the separately compiled PDF has different creation metadata. This is reproducibility in the same installed TeX environment, not a cross-platform typography guarantee. The full record is in `submission/zip-rebuild-report.json`; the original missing-font-map attempt and final compiler logs are retained in `submission/build-logs/`.

Official PDF SHA-256: `1cedfed3e276e8993ef46745c1af03626610c04ac5fa95a717b80e63f3084db8`.

Document-source ZIP SHA-256: `c421382e189a0e0ab3333032998e26263e1d1644f5028223fa1d48b65764288b`.

## 6. Exact remaining blockers

| Blocker | What must actually happen |
|---|---|
| Human-origin and authorship | Real humans document qualifying intellectual contributions, origin and review, agree on the complete author set, and resolve the current FAQ expectation truthfully. |
| Viable native preparation | First revise and validate the reading/paging strategy and full preparation input/generation budget design offline, using the retained real request shapes. The four supplemental attempts are consumed; raising only the input limit would not restore the exhausted generation count. Do not rerun the same configuration, rewrite the original freeze or imply a new grant. |
| Scientific result | Complete the accepted task design and the actual comparisons needed for the retained claims; no result may be inferred from `PENDING`. |
| Validated labels and scientific verification | Two bounded oracles have passed reference-source qualification; method-artifact behavior and complete semantic endpoints remain unmeasured. Independently bind evaluation to sealed method artifacts, retain the original failed draft and development revision, and complete truth evidence, coverage, errors and unresolved judgments before formal use. Programmatic checks and disclosed AI assistance can do reliable portions. If human-v1 is selected, its real-review contract still applies; 22 blank forms are not a universal development or venue requirement. |
| Fixed B provider access | Supply the designated embedding/rerank credentials privately and establish account availability, billing units and a checked CNY bound for the fixed models, including `rerank-v3.5`. The verified Git checkout, isolated private binding and launch Git priority are already prepared; neither license work nor a manual PATH change remains an author task. Any method execution also requires a genuinely available authorized parent; this round produced none. |
| Full accounting | Preserve all scheduled attempts, outcomes, failures, usage and unknown costs; support or remove cost-effectiveness claims. |
| Review-safe evidence access | Freeze the complete permitted artifact and review access, with actual rights and anonymity checks. |
| Author declarations and accounts | Supply factual author/profile/quota, funding, conflicts, overlap, and applicable ethics records. None are guessed here. |
| Final editorial pass and author responsibility | Reconcile the completed evidence with the abstract, methods, limitations, conclusion, and every table. Tools can prepare and check this material; the real authors must actually review and take responsibility for the resulting claims and approve the exact final version. No fixed extra panel of human reviewers is imposed here. |
| Day-of-submission check | Re-read current rules and inspect the real form with eligible human accounts, then obtain authorization for an actual submission. |

The cover letter and contribution worksheet are concrete preparation materials. The remaining personal facts are author identities, affiliations, actual contributions, conflicts/funding/overlap, account eligibility and final consent; they cannot be invented by an assistant or replaced with completed-looking review templates. Citation checks, code audits, source verification, analysis preparation, drafting and document QA can continue with explicit AI/programmatic provenance. This task creates no acceptance expectation and does not contact the journal.

## Official primary sources

Initially checked on 2026-11-28; those direct HTTP retrieval records and hashes remain in `submission/policy-provenance.json`. T4–T6 were reopened on 2026-11-29 (Asia/Shanghai) for the assistance, responsibility and evidence boundary. The original provenance record and style pin were not rewritten. No current invitation, login, quota, or account eligibility was tested.

- **[T1]** [Official pinned template](https://github.com/JmlrOrg/tmlr-style-file/tree/7bf90efe3a0debbba703c05c43f3ff7e4d4a2992), including `main.tex`, style, bibliography style, and license notices.
- **[T2]** [Submission instructions](https://jmlr.org/tmlr/submissions.html).
- **[T3]** [Author guide](https://jmlr.org/tmlr/author-guide.html).
- **[T4]** [FAQ](https://jmlr.org/tmlr/faq.html).
- **[T5]** [Editorial policies](https://jmlr.org/tmlr/editorial-policies.html).
- **[T6]** [Acceptance criteria](https://jmlr.org/tmlr/acceptance-criteria.html).
