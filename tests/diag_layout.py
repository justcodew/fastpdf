#!/usr/bin/env python3
"""Dump pre/post reading_order_sort state for page 1."""
import sys
import fitz
import flashpdf

pdf = sys.argv[1] if len(sys.argv) > 1 else \
    "/Users/xiongzhaolong/Downloads/claude-pro/202604-job/pdf_pro/flashpdf/test_data/2604.11578v1.pdf"

doc = fitz.open(pdf)
page = doc[0]
print(f"pymupdf page rect: {page.rect}")
print(f"pymupdf page rotation: {page.rotation}")
doc.close()

# Get pymupdf page dict to inspect MediaBox
doc = fitz.open(pdf)
mediabox = doc[0].mediabox
print(f"pymupdf mediabox: {mediabox}")
doc.close()

print("\n=== flashpdf all pages block count ===")
fp_blocks, _ = flashpdf.extract(pdf, include_images=False)
print(f"total blocks: {len(fp_blocks)}")

# Print page 1 blocks (we know first N are page 1)
print("\nFirst 15 blocks with bbox:")
for i, b in enumerate(fp_blocks[:15]):
    bbox = b.get("bbox", [0,0,0,0])
    lines = b.get("lines", [])
    first_text = ""
    if lines and lines[0].get("spans"):
        first_text = lines[0]["spans"][0].get("text", "")[:60]
    y0 = bbox[1]
    y1 = bbox[3]
    print(f"  B{i}: bbox={[round(x,1) for x in bbox]}  y_center={(y0+y1)/2:.1f}  first={first_text!r}")
