"""Dump a PDF's table of contents to YAML.

Usage:
    python toc_to_yaml.py input.pdf > toc.yaml
"""
from __future__ import annotations

import argparse
import sys

import flashpdf


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf")
    args = ap.parse_args()

    doc = flashpdf.open(args.pdf)
    toc = doc.get_toc()  # list of [level, title, page]

    # Emit YAML by hand — no external deps.
    sys.stdout.write("toc:\n")
    for entry in toc:
        level, title, page = entry[0], entry[1], entry[2]
        indent = "  " * level
        title_escaped = title.replace('"', '\\"')
        sys.stdout.write(f'{indent}- title: "{title_escaped}"\n')
        sys.stdout.write(f'{indent}  page: {page}\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
