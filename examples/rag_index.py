"""Build a minimal search index over a folder of PDFs.

Output: one JSON record per PDF, containing per-page plain text plus basic
metadata (title, author, page count). Feed the resulting NDJSON into your
embedding pipeline (OpenAI, sentence-transformers, etc.).

Usage:
    python rag_index.py /path/to/pdfs > index.ndjson
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import flashpdf


def index_pdf(path: Path) -> dict:
    doc = flashpdf.open(str(path))
    pages = []
    for i in range(len(doc)):
        # "text" mode is ~5x cheaper than "dict" when you only need prose.
        text = doc[i].get_text("text")
        pages.append({"page": i + 1, "text": text})
    meta = doc.metadata
    return {
        "file": str(path),
        "page_count": len(doc),
        "is_encrypted": doc.is_encrypted,
        "is_linearized": doc.is_linearized,
        "title": meta.get("title"),
        "author": meta.get("author"),
        "pages": pages,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dir", help="directory containing *.pdf files (recursive)")
    args = ap.parse_args()

    root = Path(args.dir)
    pdfs = [root] if root.is_file() else sorted(root.rglob("*.pdf"))
    for pdf in pdfs:
        try:
            record = index_pdf(pdf)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"skip {pdf}: {exc}\n")
            continue
        sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
