"""Convert a PDF to GitHub-flavored Markdown.

Heuristics, in priority order:
  * Font size delta picks out headings (largest spans on a page → # / ##).
  * Spans on the same y-row get joined; rows are joined with newlines.
  * Block boundaries become blank lines.

Not a pixel-perfect renderer — designed for prose-heavy PDFs (papers,
reports, manuals). Scanned PDFs (is_scanned=True) will yield almost nothing;
see ocr_bridge.py for that case.

Usage:
    python markdown_export.py input.pdf > output.md
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict

import flashpdf


def page_to_markdown(page) -> str:
    d = page.get_text("dict")
    lines_out = []
    body_size = None
    sizes = defaultdict(int)
    for block in d["blocks"]:
        if block.get("type") != 0:
            continue  # skip image blocks
        for line in block.get("lines", []):
            for span in line["spans"]:
                sizes[round(span["size"])] += len(span["text"])
    if sizes:
        body_size = max(sizes, key=lambda s: sizes[s])

    for block in d["blocks"]:
        if block.get("type") != 0:
            continue
        buf = []
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s["text"] for s in spans).rstrip()
            if not text:
                continue
            avg_size = sum(s["size"] for s in spans) / len(spans)
            if body_size and avg_size > body_size + 1.5:
                text = f"## {text}"
            elif body_size and avg_size > body_size + 0.5:
                text = f"### {text}"
            buf.append(text)
        if buf:
            lines_out.append("\n".join(buf))
            lines_out.append("")  # blank line between blocks
    return "\n".join(lines_out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf")
    args = ap.parse_args()

    doc = flashpdf.open(args.pdf)
    for i in range(len(doc)):
        page = doc[i]
        if page.is_scanned:
            sys.stdout.write(f"\n[page {i + 1}: scanned — no text layer]\n\n")
            continue
        sys.stdout.write(page_to_markdown(page))
        sys.stdout.write(f"\n\n--- page {i + 1} ---\n\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
