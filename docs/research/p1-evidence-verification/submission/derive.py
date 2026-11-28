#!/usr/bin/env python3
"""Derive a NOT READY TMLR review draft without editing the canonical manuscript.

This controller-side script is deliberately excluded from the anonymous source
ZIP: its provenance records identify the non-anonymous source revision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
PACKAGE = HERE / "tmlr-review"
LEGACY_REVISION = "49e772bbf60532682771874b7ec96958f4a179e3"
TITLE = "When to Reopen the Source: Evidence Verification after Native Agent Compaction"
AI_DISCLOSURE = (
    "AI-use disclosure: ChatGPT/Codex systems assisted with literature and source "
    "inspection, method and protocol formulation, English drafting, code "
    "implementation and review, testing, source acquisition, and document "
    "preparation. This assistance was not limited to language polishing. Human "
    "intellectual contributions and independent verification are not yet "
    "documented sufficiently to establish TMLR's stated human-sourced expectation. "
    "That condition remains unresolved; no AI system is an author. This is a "
    "NOT READY working draft."
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, value: str) -> None:
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def convert(path: Path, output: Path) -> None:
    subprocess.run([
        "pandoc", str(path), "--from=markdown+raw_tex+tex_math_single_backslash",
        "--to=latex", "--natbib", "--no-highlight", "--output", str(output),
    ], check=True)
    # A source filename exceeds its official-width table cell unless a legal
    # line break is allowed. Keep the font size and all style dimensions intact.
    text = output.read_text()
    text = text.replace(r"\texttt{counterfactual-freshness.json}", r"\path{counterfactual-freshness.json}")
    # Keep a heading with the start of its content. This inserts content-level
    # page-break guards; it changes no official font, margin, or style file.
    text = re.sub(r"(?m)^(?=\\(?:sub)*section\{)",
                  lambda match: "\\Needspace{5\\baselineskip}\n", text)
    output.write_text(text)


def clean_headings(text: str) -> str:
    return re.sub(r"^(#{1,6})\s+\d+(?:\.\d+)*\.\s+", r"\1 ", text, flags=re.M)


def anonymize(text: str) -> str:
    return text.replace(LEGACY_REVISION, "revision withheld in review draft")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=HERE.parent / "manuscript.md")
    parser.add_argument("--bibliography", type=Path, default=HERE.parent / "references.bib")
    args = parser.parse_args()
    source = args.source.resolve()
    bibliography = args.bibliography.resolve()
    source_bytes, bibliography_bytes = source.read_bytes(), bibliography.read_bytes()
    canonical = source_bytes.decode("utf-8")
    if not canonical.startswith("---\n"):
        raise SystemExit("Expected canonical Markdown front matter.")
    content = canonical.split("\n---\n", 1)[1].strip()
    abstract_marker = "# Abstract\n\n"
    intro_marker = "# 1. Introduction\n"
    reference_marker = "# References {#references}\n"
    appendix_marker = "# Appendices\n"
    for marker in (abstract_marker, intro_marker, reference_marker, appendix_marker):
        if content.count(marker) != 1:
            raise SystemExit(f"Canonical section marker missing or ambiguous: {marker!r}")
    status, rest = content.split(abstract_marker, 1)
    abstract, rest = rest.split(intro_marker, 1)
    abstract = abstract.replace("\\clearpage", "").strip()
    main_body, tail = (intro_marker + rest).split(reference_marker, 1)
    main_body = main_body.rstrip().removesuffix("\\clearpage").rstrip()
    appendices = tail.split(appendix_marker, 1)[1].strip()
    appendices = re.sub(r"^# Appendix [A-Z]\. ", "# ", appendices, flags=re.M)
    main_body = clean_headings(anonymize(main_body))
    appendices = anonymize(appendices)

    bib = bibliography_bytes.decode("utf-8")
    matches = list(re.finditer(r"(?m)^@\w+\{memex2026pilot,", bib))
    if len(matches) != 1:
        raise SystemExit("Expected one legacy project bibliography entry.")
    start = matches[0].start()
    next_entry = re.search(r"(?m)^@", bib[matches[0].end():])
    end = matches[0].end() + next_entry.start() if next_entry else len(bib)
    anonymized_entry = """@misc{memex2026pilot,
  author = {{Project record (anonymized)}},
  title = {Development-only evidence-recovery report},
  year = {2026},
  howpublished = {Non-archival project artifact},
  note = {Identity and direct link withheld in this unsubmitted review-format draft.
          The non-anonymous provenance remains in the canonical project record.
          Synthetic development evidence, not a confirmatory study}
}
"""
    review_bib = bib[:start] + anonymized_entry + bib[end:]
    if LEGACY_REVISION in review_bib or "QiuXu-Tech" in review_bib:
        raise SystemExit("Legacy project identity remains in review bibliography.")

    PACKAGE.mkdir(exist_ok=True)
    for name, text in {"status": status, "abstract": abstract,
                       "body": main_body, "appendices": appendices}.items():
        write(PACKAGE / f"{name}.md", text)
        convert(PACKAGE / f"{name}.md", PACKAGE / f"{name}.tex")
    write(PACKAGE / "references.bib", review_bib)

    main_tex = r"""% Generated review-format working draft; NOT SUBMITTED.
% Official TMLR style files are pinned and unmodified. No accepted/preprint option.
\documentclass[10pt]{article}
\usepackage{tmlr}
\usepackage{amsmath,amssymb}
\usepackage{longtable,booktabs,array,calc}
\usepackage{fvextra}
\usepackage{needspace}
\usepackage{hyperref}
\usepackage{url}
\providecommand{\tightlist}{}
\RecustomVerbatimEnvironment{verbatim}{Verbatim}{breaklines=true,breakanywhere=true}
\hypersetup{pdftitle={__TITLE__},pdfauthor={Anonymous},
  pdfsubject={NOT READY; unsubmitted methods and protocol working draft},
  hidelinks}
\title{__TITLE__}
% Human author identities and affiliations remain unverified and are not invented.
\author{}
\begin{document}
\maketitle
\textbf{NOT READY --- NOT SUBMITTED.} Unsubmitted methods/protocol working draft,
28 November 2026.\footnote{__AI_DISCLOSURE__}
The review-mode labels above come from the unmodified official template;
this PDF is a format-validation draft and has not entered review.
\begin{abstract}
\input{abstract.tex}
\end{abstract}
\input{status.tex}
\input{body.tex}
\clearpage
\bibliography{references}
\bibliographystyle{tmlr}
\clearpage
\section*{Appendices}
\appendix
\input{appendices.tex}
\end{document}
""".replace("__TITLE__", TITLE).replace("__AI_DISCLOSURE__", AI_DISCLOSURE)
    write(PACKAGE / "main.tex", main_tex)

    key_pattern = r"(?m)^@\w+\s*\{([^,]+),"
    keys = re.findall(key_pattern, review_bib)
    cited = set(re.findall(r"@([A-Za-z][A-Za-z0-9_:-]+)", canonical))
    if len(set(keys)) != len(keys) or cited != set(keys):
        raise SystemExit("Bibliography key mismatch after derivation.")
    derived_pending = sum(text.count("PENDING") for text in (status, abstract, main_body, appendices))
    if derived_pending != canonical.count("PENDING"):
        raise SystemExit("Derivation changed the number of PENDING markers.")
    provenance = {
        "schema": 1, "status": "NOT_READY_NOT_SUBMITTED",
        "canonical_source": "../manuscript.md",
        "canonical_source_sha256": sha(source_bytes),
        "canonical_bibliography": "../references.bib",
        "canonical_bibliography_sha256": sha(bibliography_bytes),
        "canonical_files_modified": False,
        "template_commit": "7bf90efe3a0debbba703c05c43f3ff7e4d4a2992",
        "source_revision_when_initialized": "19497ff",
        "pending_markers_preserved": derived_pending,
        "reference_count": len(keys),
        "scientific_text_policy": "Preserve the canonical working draft; no new results, author facts, or claims of readiness.",
        "transformations": [
            "Remove canonical A4/11pt/custom-margin/font/header metadata; use official default 10pt review style.",
            "Separate abstract, body, and appendices; use automatic section numbering and natbib/BibTeX.",
            "Allow a source filename to break at path punctuation without shrinking its font or changing a style dimension.",
            "Keep generated section headings with following content using local page-break guards.",
            "Add visible NOT READY/NOT SUBMITTED text and a first-page AI-use disclosure.",
            "Replace the identifying project bibliography entry with an explicitly anonymized project record.",
            "Withhold the exact legacy project commit in review prose; retain canonical provenance unchanged.",
            "Do not add human names, affiliations, author contributions, acknowledgments, or funding claims.",
        ],
        "human_origin_condition": "UNRESOLVED",
        "human_anonymity_review": "NOT_RECORDED",
        "generated": {p.name: sha(p.read_bytes()) for p in sorted(PACKAGE.iterdir())
                      if p.suffix in {".md", ".tex", ".bib"} and p.name != "README.md"},
    }
    write(HERE / "derivation.json", json.dumps(provenance, indent=2))
    print(json.dumps({"status": provenance["status"], "references": len(keys),
                      "pending": derived_pending, "package": str(PACKAGE)}))


if __name__ == "__main__":
    main()
