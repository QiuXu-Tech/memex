#!/usr/bin/env python3
"""Compile the frozen TMLR review sources; never submit or invoke a model."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["pdflatex", "xelatex"], default="pdflatex")
    parser.add_argument("--isolated-format", action="store_true",
                        help="Build a temporary format instead of changing system TeX configuration.")
    parser.add_argument("--texmf", help="Explicit TEXMF tree list for an incomplete local TeX index.")
    parser.add_argument("--font-map", type=Path, action="append", default=[],
                        help="Installed map to combine into a temporary pdftex.map; repeat as needed.")
    parser.add_argument("--keep-build", action="store_true", help="Keep temporary compiler files for inspection.")
    args = parser.parse_args()
    provenance = json.loads((ROOT / "style-provenance.json").read_text())
    for name, record in provenance["files"].items():
        if digest(ROOT / name) != record["sha256"]:
            raise SystemExit(f"Pinned official template file changed: {name}")
    source_names = ["main.tex", "abstract.tex", "status.tex", "body.tex", "appendices.tex", "references.bib"]
    sources = {name: digest(ROOT / name) for name in source_names}
    source = (ROOT / "main.tex").read_text()
    if "\\usepackage{tmlr}" not in source or re.search(r"\\usepackage\[(?:accepted|preprint)\]\{tmlr\}", source):
        raise SystemExit("The package must use the official default review option.")
    if "NOT READY" not in source or "AI-use disclosure" not in source:
        raise SystemExit("Working-draft status or AI disclosure missing.")
    environment = os.environ.copy()
    if args.texmf:
        environment["TEXMF"] = args.texmf
    environment["BIBINPUTS"] = str(ROOT) + os.pathsep + environment.get("BIBINPUTS", "")
    environment["BSTINPUTS"] = str(ROOT) + os.pathsep + environment.get("BSTINPUTS", "")
    work = Path(tempfile.mkdtemp(prefix="tmlr-review-build-"))
    font_maps = []
    if args.font_map:
        if args.engine != "pdflatex":
            raise SystemExit("Explicit pdftex font maps require --engine pdflatex.")
        mapping = []
        for path in args.font_map:
            data = path.read_bytes()
            font_maps.append({"path": str(path), "sha256": hashlib.sha256(data).hexdigest()})
            mapping.append(data.rstrip() + b"\n")
        (work / "pdftex.map").write_bytes(b"".join(mapping))
        environment["TEXFONTMAPS"] = str(work) + os.pathsep + environment.get("TEXFONTMAPS", "")
    commands, logs = [], []

    def run(argv: list[str], cwd: Path, label: str) -> None:
        result = subprocess.run(argv, cwd=cwd, env=environment, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = work / (label + ".log")
        log.write_text(result.stdout)
        commands.append({"label": label, "argv": [a.replace(str(work), "<BUILD_DIR>") for a in argv],
                         "cwd": "package" if cwd == ROOT else "<BUILD_DIR>", "exit_code": result.returncode})
        logs.append(log)
        if result.returncode:
            print(result.stdout[-6000:])
            raise RuntimeError(f"{label} failed; retained logs: {work}")

    try:
        engine = shutil.which(args.engine)
        if not engine:
            raise RuntimeError(f"Missing {args.engine}")
        base = [engine]
        if args.isolated_format:
            primitive = "pdftex" if args.engine == "pdflatex" else "xetex"
            run([primitive, "-ini", "-etex", "-no-shell-escape", "-interaction=nonstopmode",
                 "-halt-on-error", "-jobname=tmlr-format", f"-output-directory={work}",
                 args.engine + ".ini"], ROOT, "format")
            base.append(f"-fmt={work}/tmlr-format.fmt")
        latex = base + ["-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error",
                        "-file-line-error", f"-output-directory={work}", "main.tex"]
        run(latex, ROOT, "latex-1")
        run(["bibtex", "main"], work, "bibtex")
        run(latex, ROOT, "latex-2")
        run(latex, ROOT, "latex-3")
        final_log = (work / "main.log").read_text(errors="replace")
        rerun = bool(re.search(r"(?:Rerun to get|Please.*rerun|Label\(s\) may have changed)", final_log))
        if rerun:
            run(latex, ROOT, "latex-4")
            final_log = (work / "main.log").read_text(errors="replace")
        bad = {
            "undefined_citations": len(re.findall(r"Citation .* undefined|There were undefined", final_log)),
            "missing_characters": final_log.count("Missing character:"),
            "overfull_boxes": final_log.count("Overfull "),
            "underfull_boxes": final_log.count("Underfull "),
            "rerun_requests": len(re.findall(r"(?:Rerun to get|Please.*rerun|Label\(s\) may have changed)", final_log)),
        }
        if bad["undefined_citations"] or bad["missing_characters"] or bad["rerun_requests"]:
            raise RuntimeError(f"Unresolved compiler problems: {bad}; logs: {work}")
        shutil.copy2(work / "main.pdf", ROOT / "main.pdf")
        shutil.copy2(work / "main.bbl", ROOT / "main.bbl")
        report = {
            "schema": 1, "status": "BUILT_NOT_READY_NOT_SUBMITTED",
            "template_commit": provenance["commit"], "official_files_byte_identical": True,
            "engine": subprocess.check_output([args.engine, "--version"], text=True).splitlines()[0],
            "bibtex": subprocess.check_output(["bibtex", "--version"], text=True).splitlines()[0],
            "isolated_format": args.isolated_format, "texmf_override": args.texmf,
            "temporary_font_maps": font_maps,
            "sources": sources, "commands": commands, "compiler_checks": bad,
            "pdf_sha256": digest(ROOT / "main.pdf"), "pdf_bytes": (ROOT / "main.pdf").stat().st_size,
            "bbl_sha256": digest(ROOT / "main.bbl"),
            "visual_review": "REQUIRED_SEPARATELY", "submitted": False,
        }
        (ROOT / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
        if args.keep_build:
            print(f"Compiler files retained at {work}")
        else:
            shutil.rmtree(work)
    except BaseException:
        print(f"Incomplete build retained at {work}; no submission was performed.")
        raise


if __name__ == "__main__":
    main()
