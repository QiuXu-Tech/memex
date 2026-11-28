# Building the P1 manuscript

Updated: **2026-11-28**.

## Artifact status

This is an expanded **methods and protocol working draft**, not a submission-ready paper or an eight-page conference manuscript. The proposed study has no new paired method-effect or confirmatory result in these files. Engineering regression checks, retained host-integration attempts, candidate acquisition, and real-repository source/environment qualification are described separately from the earlier synthetic development observations and from the unrun H1/H2 study.

The editable source of record is `manuscript.md`; references are maintained in `references.bib`. Pandoc with citeproc generates the self-contained, editable `manuscript.tex`. The rendered bibliography is embedded in that TeX file, so editing and recompiling the TeX alone does not require BibTeX. When editing the bibliography, regenerate the TeX from Markdown.

The PDF uses a conventional single-column A4 article layout, 11-point Latin Modern body text, visible working-draft running headers, page numbers, and separate references and appendices. No generated illustrations are included. The broad results table is divided into decision and resource panels to keep its headings legible.

## Standard build

Run from this directory with Pandoc and a complete XeLaTeX installation:

```bash
p1_build_dir="$(mktemp -d)"
pandoc manuscript.md --standalone --citeproc \
  --from=markdown+raw_tex+tex_math_single_backslash \
  --to=latex --no-highlight --output=manuscript.tex
xelatex -interaction=nonstopmode -halt-on-error -file-line-error \
  -output-directory="$p1_build_dir" manuscript.tex
xelatex -interaction=nonstopmode -halt-on-error -file-line-error \
  -output-directory="$p1_build_dir" manuscript.tex
cp "$p1_build_dir/manuscript.pdf" manuscript.pdf
```

The `tex_math_single_backslash` extension is required: the source uses LaTeX inline and display math delimiters. Two successful XeLaTeX passes resolve citation links and page labels. A source change that affects table widths can require a further pass; inspect the log rather than assuming a fixed number is sufficient.

Required fonts are Latin Modern Roman, Latin Modern Sans, and DejaVu Sans Mono. The generated preamble uses standard TeX packages including `fontspec`, `unicode-math`, `geometry`, `longtable`, `booktabs`, `fancyhdr`, `fvextra`, `microtype`, `needspace`, `hyperref`, and `babel`.

## Local container build used for this artifact

The available container had the TeX package files but lacked usable package-index and prebuilt-format state. A default Tectonic attempt could not retrieve its bundle (HTTP 403). The successful route uses the installed XeTeX engine and package trees, with an isolated temporary format. It does not install packages or modify the system TeX configuration.

```bash
p1_build_dir="$(mktemp -d)"
pandoc manuscript.md --standalone --citeproc \
  --from=markdown+raw_tex+tex_math_single_backslash \
  --to=latex --no-highlight --output=manuscript.tex
env TEXMF="{/usr/share/texlive/texmf-dist,/usr/share/texmf,/etc/texmf,/var/lib/texmf}" \
  xetex -ini -no-shell-escape -interaction=nonstopmode -halt-on-error \
  -jobname=p1-xelatex -etex -output-directory="$p1_build_dir" xelatex.ini
env TEXMF="{/usr/share/texlive/texmf-dist,/usr/share/texmf,/etc/texmf,/var/lib/texmf}" \
  xelatex -fmt="$p1_build_dir/p1-xelatex.fmt" \
  -no-shell-escape -interaction=nonstopmode -halt-on-error -file-line-error \
  -output-directory="$p1_build_dir" manuscript.tex
env TEXMF="{/usr/share/texlive/texmf-dist,/usr/share/texmf,/etc/texmf,/var/lib/texmf}" \
  xelatex -fmt="$p1_build_dir/p1-xelatex.fmt" \
  -no-shell-escape -interaction=nonstopmode -halt-on-error -file-line-error \
  -output-directory="$p1_build_dir" manuscript.tex
cp "$p1_build_dir/manuscript.pdf" manuscript.pdf
```

Versions used: Pandoc **3.1.11.1**; XeTeX **0.999996**, TeX Live 2025/dev/Debian; LaTeX2e **2024-11-01 patch level 2**. The document date and access-date annotations use the user's local date, 28 November 2026; original publication dates and the legacy November 26 experiment date remain source dates.

## Verification

Citation-key checks found 16 references, no missing entries, no duplicate keys, and no unused entries. The generated TeX contains resolved citeproc bibliography records rather than literal Pandoc citation syntax. Machine-private source paths were removed from the manuscript.

After a successful build, render every page and inspect the results:

```bash
pdfinfo manuscript.pdf
pdftoppm -r 110 -png manuscript.pdf "$p1_build_dir/page"
```

Verify the first-page status and date, formulas, tables, source links, bibliography, page boundaries, and appendix transition. Check the final compiler log for undefined citations, missing characters, and overfull boxes. Rendering and text extraction are complementary: extracted text alone does not demonstrate correct layout.

The delivered canonical PDF has **26 pages**: title, abstract, and main text on pages 1–21; references on page 22; appendices on pages 23–26. It is an expanded working document, not an eight-page submission layout.

The final XeLaTeX build additionally records the two authorized native development attempts and the separate clean public-base test captures. Its log contains no undefined citations, missing-character messages, overfull boxes, or outstanding rerun requests. Eight nonfatal underfull-box spacing warnings remain. All 26 pages were rendered with Poppler at 110 dpi and inspected in contact sheets. Text comparison with the previously inspected 25-page draft identified changes on pages 10–26. Full-page checks covered pages 1, 11, 13, 25 and 26, including the new observations, source paths and table transitions. No clipped text, overlapping content, broken mathematical notation, or missing glyphs were observed. The abstract, formal result section, limitations and conclusion remain unchanged; `submission/batch1-manuscript-sync.json` records the comparison and evidence hashes.

Previously established content-level formatting helpers remain: a local `sloppypar` wrapper allows the limitation paragraph to wrap, and `\path` permits long evidence-directory names to break at punctuation. These helpers change no scientific word or value. No font or margin was reduced to accommodate the new development record. The canonical source remains the source of truth for both document formats.

Text extraction found no unresolved Pandoc citation syntax, replacement characters, or text outside the page bounds. All 16 references and all 56 `PENDING` result placeholders remain. These checks verify the document build and presentation, not the scientific hypotheses or the completeness of the proposed implementation. Machine and visual records are in `submission/canonical-build-report.json`, `submission/canonical-qa-report.json`, and the retained `submission/build-logs/canonical-final.txt`.

Final canonical PDF SHA-256: `0f9a5b0807f50939025a9b2e73c9e4ba4f4c6ec629ef4aa272e0e82efd1e2c95`.

## Separate official TMLR format draft

`submission/tmlr-review/main.pdf` is a separate **27-page** derivative using the unmodified official TMLR default review style pinned at commit `7bf90efe3a0debbba703c05c43f3ff7e4d4a2992`. Its main text ends on page 20, references occupy pages 21–22, and appendices occupy pages 23–27. The fixed template review labels do not represent an actual submission: the first page explicitly says **NOT READY — NOT SUBMITTED** and includes a disclosure of substantive AI assistance and the unresolved human-origin condition.

The official derivative uses native natbib/BibTeX and official typography, rather than importing the canonical A4/11-point layout. Its final log has no undefined citations, missing characters, overfull or underfull boxes, or outstanding rerun requests. All 27 pages were rendered and visually inspected in contact sheets, with full-page checks of pages 1, 5, 8, 11, 12, 15, 25, 26 and 27. The final page retains one complete Eywa table row and its repeated header; its substantial white space is recorded in QA. No content or qualification was removed to force a shorter layout. The official source files are hash-verified against the pin. Direct-identifier screening is a bounded mechanical check, not a completed human anonymity review.

See [SUBMISSION_PACKAGE.md](SUBMISSION_PACKAGE.md) for exact build, QA, and archive commands, [CONTRIBUTIONS.md](CONTRIBUTIONS.md) for factual human-contribution gaps, and `submission/qa-report.json` for the rendered-document checks. The document-source ZIP is separate from the unfinished scientific artifact. It does not execute models or establish empirical findings.

Official-format PDF SHA-256: `1cedfed3e276e8993ef46745c1af03626610c04ac5fa95a717b80e63f3084db8`.

## Earlier implementation-boundary review correction

The earlier 28 November 2026 review revision explicitly labeled Section 4 as the full proposed deployment protocol. At that revision, Section 5.3 recorded the narrower implemented interface: a global session-catalog watermark; trusted snapshot-head count and content commitment; a limited Node/TAP normalizer with captured before/after artifact hashes; and an observable-input claim-extraction boundary. General lifecycle projection, automatic live binding, and natural-task extraction accuracy were not described as completed. Native-compaction smoke checks were not promoted to paper results. That revision had 21 rendered and inspected pages. The subsequent live-state component now supports the narrower current-workspace test binding described below; it does not complete the full protocol.

## Earlier query-interface consistency correction

That correction made Section 4.1 state that C, D, and claim-driven ablations share the extractor, while the primary faithful Raw-RAG arm B retains the original user request as its query. An optional claim-expanded Raw-RAG condition is a separately named, frozen, and budgeted adaptation, not an already implemented baseline. After that correction was regenerated and recompiled, the PDF remained 21 pages. Page-by-page text comparison found only page 6 changed; that page was rendered at 110 dpi and visually checked. Citation validation found 16 references and 56 `PENDING` markers. No overfull, missing-character, undefined-citation, or outstanding rerun warnings appeared; six underfull spacing warnings remained.

## Engineering and source-qualification update

Section 5.3 now records the implemented live-state observer and wrapper for explicitly current-workspace `test_result` claims, including actual bounded file/environment observations, before/after execution binding, new-head provenance checks through real archive I/O, and invalidation after observed workspace changes. Its 15 passing local tests are engineering evidence, not a study denominator. The description retains the trusted-controller, declared-dependency, non-atomic observation, and retrieval limitations. General natural-language lifecycle construction and other object-state bindings remain incomplete.

The experiment controller is described by its local freeze → first-attempt dispatch → evaluator join and component-ledger contracts. Review-driven code corrections remain separate from the paper's result claims; no controller test count is used as a study outcome. The earlier online development attempt is recorded as approval-blocked after successful workspace inspection, with no test execution, compaction, extraction, or verification decision. Two separate extraction-only generations on one synthetic development input are also retained: the first passed schema validation but missed the test obligation; after a general prompt revision, one retest produced that candidate and passed the narrow component check while leaving coverage unestablished. The manuscript does not report extraction accuracy from these attempts. Across those historical checks, three generation turns started and zero test executions, compactions, verification decisions, or formal tasks occurred. Costs remain unmeasured (`null`). Previous native smoke logs are not counted as those missing stages. The record is located in `artifacts/live-native/` and is cited in Appendix C.

The later `artifacts/authorized-batch1/` records are separate. The first native attempt timed out after provider interruption; the second observed two ordinary one-call approvals, one passing broker test, one simulated stable release, two extractions and two real compactions before the changed continuation timed out. Stable receipt reuse and rejection after a version change are recorded as bounded developer observations, with whole-run checks and full costs unavailable. Two controller-only captures from clean public Python bases are also recorded separately from the earlier official-test-patch reproduction. Their 59 passed and 201 passed/11 skipped counts do not become method-arm executions or accepted workflows.

Section 5.4 and Appendix C retain 16 real source candidates across eight projects and zero accepted/frozen P1 workflows. The initial Flask and Requests checks are preserved with their actual counts and skipped tests. A bounded expansion attempted all 14 remaining candidates and qualified ten more, giving 12 qualified sources out of 16 candidates. The expansion retains 29 source/environment attempts and 34 top-level test-phase invocations, including unsuccessful environment attempts. Four candidates retain specific bounded limitations. Qualification used official expected transitions and a successful fixed-run exit; later rule correction and reruns are visible. These are environment and source checks, not model runs, independent pilot tasks, or arm scores. The 11/16 non-first-parent ancestry issue, official parser-label cautions, rights/access limits, and public/evaluator separation remain explicit.

The same section records 11 inspectable but unaccepted workflow packages and 22 unfilled independent-review packets. None is silently accepted as a P1 task, and no human annotation is claimed. Section 5.5 records one fixed archived checkpoint with five generation starts, one actual native compaction, and three forks of the same parent. A, C, and D all recommended hold. C opened two original records and D reused a certificate with zero new opens for the same test claim; their complete evidence packets were identical and both reported 15,350 input tokens. The document does not convert this source-I/O difference into a token or cost advantage. Cached-input subsets differ, compaction usage remains incompletely metered, and actual spend and standardized total cost remain null. This read-only observation does not complete the mutable-workspace workflow or the unrun Raw-RAG comparison.
