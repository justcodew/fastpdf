#!/usr/bin/env python3
"""Quantify sources of accuracy gap on page 1.

Decomposes the gap into:
- Missing words (recall loss)
- Extra words (precision loss)
- Missing spaces (concatenation issues)
- Order mismatches (block sequencing)

Outputs a prioritized fix list with concrete counts.
"""
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import fitz
import flashpdf

WORD_RE = re.compile(r"\w+")


def get_texts(pdf):
    """Return (flashpdf_text, pymupdf_text) joined in span order, doc-level."""
    fp_blocks, _ = flashpdf.extract(pdf, include_images=False)
    fp_spans = []
    for b in fp_blocks:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                fp_spans.append(s["text"])
    fp_text = "".join(fp_spans)

    doc = fitz.open(pdf)
    pm_spans = []
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            if "lines" not in b:
                continue
            for l in b["lines"]:
                for s in l.get("spans", []):
                    pm_spans.append(s.get("text", ""))
    doc.close()
    pm_text = "".join(pm_spans)
    return fp_text, pm_text


def main():
    pdf = sys.argv[1] if len(sys.argv) > 1 else \
        "/Users/xiongzhaolong/Downloads/claude-pro/202604-job/pdf_pro/flashpdf/test_data/2604.11578v1.pdf"

    fp_text, pm_text = get_texts(pdf)

    print(f"flashpdf chars: {len(fp_text)}  spaces: {fp_text.count(' ')}")
    print(f"pymupdf  chars: {len(pm_text)}  spaces: {pm_text.count(' ')}")
    print(f"space diff: {fp_text.count(' ') - pm_text.count(' ')}")

    # Word set diff
    fp_words = set(WORD_RE.findall(fp_text.lower()))
    pm_words = set(WORD_RE.findall(pm_text.lower()))
    only_fp = fp_words - pm_words
    only_pm = pm_words - fp_words
    print(f"\nunique words: fp={len(fp_words)} pm={len(pm_words)} shared={len(fp_words & pm_words)}")
    print(f"only in fp: {len(only_fp)}")
    print(f"only in pm: {len(only_pm)}")

    # Categorize "only in fp" — likely concatenated words
    concat_count = 0
    for w in only_fp:
        # Heuristic: word that contains a subword from pm_words glued to another
        for i in range(2, len(w) - 1):
            if w[:i] in pm_words and w[i:] in pm_words:
                concat_count += 1
                break
    print(f"  ~{concat_count} of only-fp words look like concatenations (missing space)")

    # Categorize "only in pm" — likely hyphenation merges (we merge, they don't)
    hyphen_count = 0
    for w in only_pm:
        # If this fragment + something makes a fp word
        for fw in fp_words:
            if fw.startswith(w) or fw.endswith(w):
                hyphen_count += 1
                break
    print(f"  ~{hyphen_count} of only-pm words are fragments (likely our hyphen merges)")

    # char_sim breakdown
    sm = SequenceMatcher(None, fp_text, pm_text, autojunk=False)
    print(f"\nchar_sim: {sm.ratio()*100:.1f}%")
    # Show longest matching blocks to spot where order diverges
    mb = sm.get_matching_blocks()
    print(f"matching blocks: {len(mb)}")
    # Find first divergence point
    if len(mb) > 1:
        first = mb[0]
        if first.size > 0:
            print(f"first match: fp[{first.a}:{first.a+first.size}] pm[{first.b}:{first.b+first.size}]")
            if first.a + first.size < len(fp_text):
                print(f"  fp diverges to: {fp_text[first.a+first.size:first.a+first.size+80]!r}")
            if first.b + first.size < len(pm_text):
                print(f"  pm diverges to: {pm_text[first.b+first.size:first.b+first.size+80]!r}")

    # First 1000 chars side by side (truncated for terminal)
    print(f"\n--- fp first 500 ---\n{fp_text[:500]!r}")
    print(f"\n--- pm first 500 ---\n{pm_text[:500]!r}")


if __name__ == "__main__":
    main()
