#!/usr/bin/env python3
"""Inspect/render the derived PDF. Visual inspection remains an explicit step."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz

from package import ALLOWLIST


HERE = Path(__file__).resolve().parent
PACKAGE = HERE / "tmlr-review"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-dir", type=Path,
                        help="Directory for PNG pages; defaults to a temporary directory.")
    args = parser.parse_args()
    document = fitz.open(PACKAGE / "main.pdf")
    texts = [page.get_text() for page in document]
    text = "\n".join(texts)
    first = re.sub(r"\s+", " ", texts[0])
    outside = []
    for index, page in enumerate(document):
        for word in page.get_text("words"):
            if word[0] < 0 or word[1] < 0 or word[2] > page.rect.width + .01 or word[3] > page.rect.height + .01:
                outside.append({"page": index + 1, "text": word[4]})
    urls = [link.get("uri", "") for page in document for link in page.get_links() if link.get("uri")]
    prohibited = ["QiuXu-Tech", "/workspace/", "/Users/", "/home/agent/",
                  "49e772bbf60532682771874b7ec96958f4a179e3"]
    scanned = text + "\n" + json.dumps(document.metadata) + "\n" + "\n".join(urls)
    found = [token for token in prohibited if token in scanned]
    source_identifiers, member_hashes = [], {}
    for name in ALLOWLIST:
        path = PACKAGE / name
        member_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.suffix == ".pdf":
            continue
        included_text = path.read_text(encoding="utf-8")
        source_identifiers.extend({"path": name, "identifier": token}
                                  for token in prohibited if token in included_text)
    derivation = json.loads((HERE / "derivation.json").read_text())
    bibliography = (PACKAGE / "references.bib").read_text()
    bbl = (PACKAGE / "main.bbl").read_text()
    build = json.loads((PACKAGE / "build-report.json").read_text())
    checks = {
        "letter_pages": all(abs(p.rect.width - 612) < .01 and abs(p.rect.height - 792) < .01 for p in document),
        "first_page_not_ready": "NOT READY" in first,
        "first_page_not_submitted": "NOT SUBMITTED" in first,
        "first_page_ai_disclosure": "AI-use disclosure" in first,
        "first_page_human_origin_unresolved": "condition remains unresolved" in first,
        "pdf_author_anonymous": document.metadata.get("author") == "Anonymous",
        "pending_preserved": text.count("PENDING") == derivation["pending_markers_preserved"],
        "bibliography_entries": len(re.findall(r"(?m)^@\w+\s*\{", bibliography)) == derivation["reference_count"],
        "rendered_bibliography_entries": bbl.count("\\bibitem") == derivation["reference_count"],
        "no_direct_identifiers_found": not found,
        "no_direct_identifiers_in_source_members": not source_identifiers,
        "no_text_outside_page": not outside,
        "no_replacement_character": "\ufffd" not in text,
        "no_raw_pandoc_citation": not re.search(r"\[@[A-Za-z]", text),
        "pdf_matches_build_hash": hashlib.sha256((PACKAGE / "main.pdf").read_bytes()).hexdigest() == build["pdf_sha256"],
        "sources_match_build_hashes": all(hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
                                          for name, expected in build["sources"].items()),
    }
    fonts = subprocess.check_output(["pdffonts", str(PACKAGE / "main.pdf")], text=True) if shutil.which("pdffonts") else None
    checks["no_type3_fonts"] = fonts is not None and "Type 3" not in fonts
    render_dir = args.render_dir.resolve() if args.render_dir else Path(tempfile.mkdtemp(prefix="tmlr-review-render-"))
    render_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pdftoppm", "-r", "110", "-png", str(PACKAGE / "main.pdf"), str(render_dir / "page")], check=True)
    report = {
        "schema": 1, "status": "MACHINE_CHECKED_VISUAL_REVIEW_REQUIRED",
        "pdf": "tmlr-review/main.pdf", "pdf_sha256": build["pdf_sha256"],
        "pages": len(document), "page_size_points": [612, 792],
        "pending_markers": text.count("PENDING"), "references": derivation["reference_count"],
        "checks": checks, "outside_page_words": outside, "identifier_matches": found,
        "source_member_identifier_matches": source_identifiers,
        "source_member_sha256": member_hashes,
        "pdf_metadata": document.metadata, "font_report": fonts,
        "reference_start_pages": [i + 1 for i, t in enumerate(texts) if re.search(r"(?m)^References\s*$", t)],
        "appendix_start_pages": [i + 1 for i, t in enumerate(texts) if re.search(r"(?m)^Appendices\s*$", t)],
        "render": {"tool": "pdftoppm", "dpi": 110, "pages_rendered": len(document)},
        "visual_review": {"status": "NOT_YET_RECORDED", "pages_inspected": []},
        "anonymity_limit": "A direct-string and metadata scan is not a human anonymity review.",
        "scientific_readiness": "NOT_READY", "human_origin": "UNRESOLVED", "submitted": False,
    }
    (HERE / "qa-report.json").write_text(json.dumps(report, indent=2) + "\n")
    (render_dir / "text.txt").write_text("\f".join(texts))
    print(json.dumps({"pages": len(document), "checks": checks, "render_dir": str(render_dir)}))
    if not all(checks.values()):
        raise SystemExit("One or more PDF checks failed; inspect qa-report.json.")


if __name__ == "__main__":
    main()
