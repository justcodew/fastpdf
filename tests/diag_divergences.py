#!/usr/bin/env python3
"""Find all divergence points between flashpdf and pymupdf output."""
import re
import sys
from difflib import SequenceMatcher

import fitz
import flashpdf


def get_texts(pdf):
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
    print(f"fp len: {len(fp_text)}  pm len: {len(pm_text)}")

    sm = SequenceMatcher(None, fp_text, pm_text, autojunk=False)
    print(f"char_sim: {sm.ratio()*100:.1f}%")

    # Walk through opcodes and report non-equal blocks
    print("\nDivergences (non-equal blocks):")
    opcodes = sm.get_opcodes()
    ndiv = 0
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        ndiv += 1
        if ndiv > 80:
            print(f"... ({sum(1 for t,_,_,_,_ in opcodes if t != 'equal')} total)")
            break
        fp_chunk = fp_text[i1:i2]
        pm_chunk = pm_text[j1:j2]
        # Context: 30 chars before
        ctx_i = fp_text[max(0, i1-30):i1]
        ctx_j = pm_text[max(0, j1-30):j1]
        print(f"\n[{ndiv}] {tag} at fp[{i1}:{i2}] pm[{j1}:{j2}]")
        print(f"  before: ...{ctx_i!r}")
        print(f"  fp:     {fp_chunk!r}")
        print(f"  pm:     {pm_chunk!r}")

    # Size of divergences
    total_diff = sum(i2-i1 for tag,i1,i2,j1,j2 in opcodes if tag != 'equal')
    total = len(fp_text) + len(pm_text)
    print(f"\ntotal chars in divergence regions (fp side): {total_diff}")
    print(f"% of fp chars in divergent regions: {total_diff/len(fp_text)*100:.1f}%")


if __name__ == "__main__":
    main()
