#!/usr/bin/env python3
"""Measure inter-span gaps in flashpdf output, compare against pymupdf."""
import sys
import fitz
import flashpdf

pdf = sys.argv[1] if len(sys.argv) > 1 else \
    "/Users/xiongzhaolong/Downloads/claude-pro/202604-job/pdf_pro/flashpdf/test_data/2604.11578v1.pdf"

fp_blocks, _ = flashpdf.extract(pdf, include_images=False)

# Collect all inter-span gaps within a line, with context
gaps = []  # (gap_em, prev_text_tail, curr_text_head)
for b in fp_blocks:
    for l in b.get("lines", []):
        spans = l.get("spans", [])
        if len(spans) < 2:
            continue
        for i in range(1, len(spans)):
            prev = spans[i-1]
            curr = spans[i]
            gap = curr["bbox"][0] - prev["bbox"][2]
            min_size = min(curr["size"], prev["size"])
            if min_size <= 0:
                continue
            gap_em = gap / min_size
            pt = prev["text"][-8:].replace("\n", " ")
            ct = curr["text"][:8].replace("\n", " ")
            # Track even if curr starts with space (so we see which gaps trigger)
            gaps.append((gap_em, pt, ct))

# Histogram of gaps
print(f"Total gaps: {len(gaps)}")
buckets = [0]*10
for g, _, _ in gaps:
    idx = min(int(g * 10), 9)
    if idx < 0: idx = 0
    buckets[idx] += 1
for i, c in enumerate(buckets):
    print(f"  [{i*0.1:.1f}-{(i+1)*0.1:.1f}em): {c}")

# Gaps in the 0.10-0.30 range (borderline cases)
print("\nGaps in 0.10-0.30em (borderline):")
in_band = [(g,pt,ct) for g,pt,ct in gaps if 0.10 <= g < 0.30]
print(f"  count: {len(in_band)}")
for g, pt, ct in in_band[:40]:
    print(f"  {g:.2f}em: ...{pt!r} + {ct!r}...")

# ALL gaps > 0.6em with context
print("\nGaps >= 0.6em (sample 30):")
big = [(g,pt,ct) for g,pt,ct in gaps if g >= 0.6]
for g, pt, ct in big[:30]:
    print(f"  {g:.2f}em: ...{pt!r} + {ct!r}...")
