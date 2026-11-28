# Building the P1 manuscript

Updated: **2026-11-28 (Asia/Shanghai)**.

## Artifact status

This is an expanded **methods and protocol working draft**, not a submission-ready paper or an eight-page conference manuscript. The proposed study has no new model-based result in these files. Engineering regression checks are described separately from the earlier synthetic development observations and from the unrun H1/H2 study.

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

The delivered PDF has **21 pages**: title, abstract, and main text on pages 1–17; references on page 18; appendices on pages 19–21. It is an expanded working document, not an eight-page submission layout.

The final XeLaTeX build completed successfully. Its log contains no undefined citations, missing-character messages, overfull boxes, or outstanding rerun requests. Six nonfatal underfull-box spacing warnings remain; their pages were visually checked. All 21 pages were rendered with Poppler at 110 dpi and inspected, with additional full-page checks of the algorithm, mathematical estimand, bibliography, and source table. Caption-space guards keep table headings with the start of their tables. Pagination was checked again after the implementation-boundary revision. The final inspection found no clipped text, overlapping content, broken mathematical notation, or missing glyphs.

Text extraction also found no unresolved Pandoc citation syntax, replacement characters, or text outside the page bounds. All 56 result placeholders remain `PENDING`. These checks verify the document build and presentation, not the scientific hypotheses or the completeness of the proposed implementation.

## Implementation-boundary review correction

The 28 November 2026 review revision explicitly labels Section 4 as the full proposed deployment protocol. Section 5.3 records the narrower implemented interface: a global session-catalog watermark; trusted snapshot-head count and content commitment; a limited Node/TAP normalizer with captured before/after artifact hashes; and an observable-input claim-extraction boundary. General lifecycle projection, automatic live workspace or object-state binding, and natural-task extraction accuracy are not described as completed. Native-compaction smoke checks are not promoted to paper results. The revised Markdown was regenerated to TeX, compiled successfully, and all 21 PDF pages were rendered and inspected. The manuscript ends with a single newline, and `git diff --check` on the five owned manuscript files passes.

## Query-interface consistency correction

Section 4.1 now states that C, D, and claim-driven ablations share the extractor, while the primary faithful Raw-RAG arm B retains the original user request as its query. An optional claim-expanded Raw-RAG condition is a separately named, frozen, and budgeted adaptation, not an already implemented baseline. After regenerating TeX and successfully recompiling, the PDF remains 21 pages. Page-by-page text comparison found only page 6 changed; that page was rendered at 110 dpi and visually checked. Citation validation remains complete at 16 references, and all 56 `PENDING` markers remain. No overfull, missing-character, undefined-citation, or outstanding rerun warnings appeared; the same six underfull spacing warnings remain.
