# Building the P1 manuscript

Updated: **2026-11-28 (Asia/Shanghai)**.

## Artifact status

This is an expanded **methods and protocol working draft**, not a submission-ready paper or an eight-page conference manuscript. The proposed study has no new paired method-effect or confirmatory result in these files. Engineering regression checks, retained host-integration attempts, candidate acquisition, and two real-repository environment checks are described separately from the earlier synthetic development observations and from the unrun H1/H2 study.

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
env TEXMF="{/usr/share/texlive/texmf-dist,/usr/share/texmf,/etc/texmf}" \
  xetex -ini -interaction=nonstopmode -halt-on-error \
  -jobname=p1-xelatex -etex -output-directory="$p1_build_dir" xelatex.ini
env TEXMF="{/usr/share/texlive/texmf-dist,/usr/share/texmf,/etc/texmf}" \
  xelatex -fmt="$p1_build_dir/p1-xelatex.fmt" \
  -interaction=nonstopmode -halt-on-error -file-line-error \
  -output-directory="$p1_build_dir" manuscript.tex
env TEXMF="{/usr/share/texlive/texmf-dist,/usr/share/texmf,/etc/texmf}" \
  xelatex -fmt="$p1_build_dir/p1-xelatex.fmt" \
  -interaction=nonstopmode -halt-on-error -file-line-error \
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

The delivered PDF has **24 pages**: title, abstract, and main text on pages 1–19; references on page 20; appendices on pages 21–24. It is an expanded working document, not an eight-page submission layout.

The final XeLaTeX build completed successfully after integrating the retained host and extraction receipts. Its log contains no undefined citations, missing-character messages, overfull boxes, or outstanding rerun requests. Six nonfatal underfull-box spacing warnings remain. All 24 pages were rendered with Poppler at 110 dpi. Page-by-page text comparison with the previous 21-page revision identified changes on pages 1, 5, 6, and 8–24; the changed layouts were visually checked, including the new implementation and source-qualification text, the result templates, bibliography, and appendix tables. The final receipt revision was also compared with the intermediate engineering build, and its changed pages were re-rendered and inspected. Full-page checks covered the title/status, integration and data-preparation text, results tables, and source-record appendix. Caption-space guards keep table headings with the start of their tables. No clipped text, overlapping content, broken mathematical notation, or missing glyphs were observed.

Text extraction also found no unresolved Pandoc citation syntax, replacement characters, or text outside the page bounds. All 56 result placeholders remain `PENDING`. These checks verify the document build and presentation, not the scientific hypotheses or the completeness of the proposed implementation.

Final PDF SHA-256: `b49157afe45dee02aa9d1a4a469f205466ecace8442febb2a798e39a3134aa2e`.

## Earlier implementation-boundary review correction

The earlier 28 November 2026 review revision explicitly labeled Section 4 as the full proposed deployment protocol. At that revision, Section 5.3 recorded the narrower implemented interface: a global session-catalog watermark; trusted snapshot-head count and content commitment; a limited Node/TAP normalizer with captured before/after artifact hashes; and an observable-input claim-extraction boundary. General lifecycle projection, automatic live binding, and natural-task extraction accuracy were not described as completed. Native-compaction smoke checks were not promoted to paper results. That revision had 21 rendered and inspected pages. The subsequent live-state component now supports the narrower current-workspace test binding described below; it does not complete the full protocol.

## Earlier query-interface consistency correction

That correction made Section 4.1 state that C, D, and claim-driven ablations share the extractor, while the primary faithful Raw-RAG arm B retains the original user request as its query. An optional claim-expanded Raw-RAG condition is a separately named, frozen, and budgeted adaptation, not an already implemented baseline. After that correction was regenerated and recompiled, the PDF remained 21 pages. Page-by-page text comparison found only page 6 changed; that page was rendered at 110 dpi and visually checked. Citation validation found 16 references and 56 `PENDING` markers. No overfull, missing-character, undefined-citation, or outstanding rerun warnings appeared; six underfull spacing warnings remained.

## Engineering and source-qualification update

Section 5.3 now records the implemented live-state observer and wrapper for explicitly current-workspace `test_result` claims, including actual bounded file/environment observations, before/after execution binding, new-head provenance checks through real archive I/O, and invalidation after observed workspace changes. Its 15 passing local tests are engineering evidence, not a study denominator. The description retains the trusted-controller, declared-dependency, non-atomic observation, and retrieval limitations. General natural-language lifecycle construction and other object-state bindings remain incomplete.

The experiment controller is described by its local freeze → first-attempt dispatch → evaluator join and component-ledger contracts. Review-driven code corrections remain separate from the paper's result claims; no controller test count is used as a study outcome. The online development attempt is recorded as approval-blocked after successful workspace inspection, with no test execution, compaction, extraction, or verification decision. Two separate extraction-only generations on one synthetic development input are also retained: the first passed schema validation but missed the test obligation; after a general prompt revision, one retest produced that candidate and passed the narrow component check while leaving coverage unestablished. The manuscript does not report extraction accuracy from these attempts. Across this batch, three generation turns started and zero test executions, compactions, verification decisions, or formal tasks occurred. Costs remain unmeasured (`null`). Previous native smoke logs are not counted as those missing stages. The record is located in `artifacts/live-native/` and is cited in Appendix C.

Section 5.4 and Appendix C record 16 real source candidates across eight projects, zero accepted/frozen P1 workflows, and two fixed-patch source/environment reproductions comprising four pytest invocations. The manuscript preserves the observed Flask and Requests outcomes, skipped tests, the 11/16 non-first-parent ancestry issue, official parser-label caveats, and the boundary between evaluator clones and future public task inputs. These records are not arm comparisons or pilot outcomes. The existing 16 references and all 56 `PENDING` markers are unchanged.
