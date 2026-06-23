#!/usr/bin/env python3
"""Print block order for first 2 pages."""
import sys
import fitz
import flashpdf

pdf = sys.argv[1] if len(sys.argv) > 1 else \
    "/Users/xiongzhaolong/Downloads/claude-pro/202604-job/pdf_pro/flashpdf/test_data/2604.11578v1.pdf"

print("=== flashpdf page 1 blocks ===")
fp_blocks, _ = flashpdf.extract(pdf, include_images=False)
for i, b in enumerate(fp_blocks[:15]):
    bbox = b.get("bbox", [0,0,0,0])
    lines = b.get("lines", [])
    first_text = ""
    if lines and lines[0].get("spans"):
        first_text = lines[0]["spans"][0].get("text", "")[:80]
    print(f"B{i}: bbox={[round(x,1) for x in bbox]} first={first_text!r}")

print("\n=== pymupdf page 1 blocks ===")
doc = fitz.open(pdf)
page = doc[0]
for i, b in enumerate(page.get_text("dict")["blocks"][:15]):
    if "lines" not in b:
        continue
    bbox = b.get("bbox", [0,0,0,0])
    first_text = ""
    if b.get("lines") and b["lines"][0].get("spans"):
        first_text = b["lines"][0]["spans"][0].get("text", "")[:80]
    print(f"B{i}: bbox={[round(x,1) for x in bbox]} first={first_text!r}")
doc.close()
