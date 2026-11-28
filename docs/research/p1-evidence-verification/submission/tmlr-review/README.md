# TMLR official-template working draft

**NOT READY — NOT SUBMITTED.** This package demonstrates the official review format. The template prints fixed review labels; they do not report an actual submission. The scientific content remains an expanded methods/protocol draft with unmeasured result cells. The human-origin condition and verified human authorship remain unresolved.

## Build

With Python 3.9 or newer, a complete TeX distribution, and BibTeX:

```bash
python3 build.py
```

The builder compiles the included editable TeX sources, runs BibTeX with the official `tmlr.bst`, verifies the pinned template files, and writes `main.pdf` plus `build-report.json`. It does not call models or a submission service. `main.bbl` is also retained. Pandoc is not needed to compile these frozen TeX sources.

For the preparation container, whose installed TeX package trees lack a usable prebuilt format/index, the actual command is:

```bash
python3 build.py --isolated-format \
  --texmf '{/usr/share/texlive/texmf-dist,/usr/share/texmf,/etc/texmf,/var/lib/texmf}' \
  --font-map /usr/share/texmf/fonts/map/dvips/lm/lm.map \
  --font-map /usr/share/texlive/texmf-dist/fonts/map/dvips/amsfonts/cm.map \
  --font-map /usr/share/texlive/texmf-dist/fonts/map/dvips/amsfonts/symbols.map \
  --keep-build
```

These explicit paths describe installed TeX dependencies in that environment, not required project paths. The command builds a temporary format and font map without changing system TeX configuration. Build failures retain their temporary logs; successful builds can retain logs with `--keep-build`. A different complete TeX installation should use the ordinary command above. PDF creation timestamps and engine versions can change the output bytes; the build report records the actual source and output hashes rather than promising identical bytes across environments.

The Markdown fragments are editable derivation snapshots. Editing them alone does not update the TeX. Regeneration from the canonical project Markdown is a separate controller-side operation; the anonymous source package intentionally excludes that controller's identifying provenance.

## Official style and third-party files

The official repository is [JmlrOrg/tmlr-style-file](https://github.com/JmlrOrg/tmlr-style-file), pinned to commit `7bf90efe3a0debbba703c05c43f3ff7e4d4a2992`. `tmlr.sty`, `tmlr.bst`, and the bundled `fancyhdr.sty` are unmodified. `style-provenance.json` records original blob identifiers and SHA-256 values. The upstream sample and license are preserved in `upstream/`; sample author names belong to the upstream template and are not this draft's authors.

The repository-level upstream license is preserved as `upstream/LICENSE` (Apache License 2.0). The bundled `fancyhdr.sty` also carries its own LaTeX Project Public License 1.3-or-later notice, retained verbatim. These notices do not assign a blanket license to third-party papers, issue text, data, or this manuscript.

The default review option is used, with no `accepted` or `preprint` option. No custom margins, text dimensions, font sizes, or headers are imported from the canonical working document. Content-support packages handle math, tables, links, and line-wrapped code; they do not change the official style file.

## Known incompleteness

- The first-page AI-use footnote describes substantive AI assistance and the unresolved human-origin condition. It does not claim completed human verification.
- Human names, affiliations, contributions, funding, and acknowledgments are not invented.
- The identifying legacy project citation is replaced by an explicitly anonymized project record; its original provenance is retained outside this review package. A complete review-safe evidence release is still required.
- Direct project-owner links and machine-private paths are screened mechanically. Human anonymity and rights review remain outstanding; a string scan cannot prove anonymity.
- The source ZIP is a document-source artifact, not a complete experiment reproduction package. No result is inferred from successful compilation.
