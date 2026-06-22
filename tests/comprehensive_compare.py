#!/usr/bin/env python3
"""Comprehensive comparison: flashpdf vs PyMuPDF.

Measures both performance (timing, throughput) and accuracy
(word/char overlap, structural counts, image counts, FFFD).

Usage:
    python tests/comprehensive_compare.py
"""
import re
import statistics
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

import fitz
import flashpdf

PDFS = [
    ("dbnet_plus", "/Users/xiongzhaolong/Downloads/claude-pro/202604-job/pdf_pro/dbnet_plus.pdf"),
    ("arxiv_2604", str(Path(__file__).parent.parent / "test_data" / "2604.11578v1.pdf")),
]
ITERS = 5


# ─── flashpdf extraction ───

def flashpdf_extract_text(pdf_path):
    """Returns text-only result (include_images=False)."""
    return flashpdf.extract(pdf_path, include_images=False)


def flashpdf_extract_full(pdf_path):
    """Returns (blocks, images) with images."""
    return flashpdf.extract(pdf_path, include_images=True)


# ─── PyMuPDF extraction ───

def pymupdf_extract_text(pdf_path):
    """Returns dict {pages: [{blocks, images}]} for parity with flashpdf."""
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        pages.append({"blocks": blocks, "images": []})
    doc.close()
    return {"pages": pages}


def pymupdf_extract_full(pdf_path):
    """Returns dict including extracted images."""
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        images = []
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                extracted = doc.extract_image(xref)
                images.append({
                    "width": img[2],
                    "height": img[3],
                    "ext": extracted.get("ext", ""),
                    "image": extracted.get("image", b""),
                })
            except Exception:
                images.append({"width": img[2], "height": img[3], "ext": "", "image": None})
        pages.append({"blocks": blocks, "images": images})
    doc.close()
    return {"pages": pages}


# ─── Timing harness ───

def bench(label, fn, *args, iters=ITERS):
    times = []
    result = None
    for _ in range(iters):
        t0 = time.perf_counter()
        result = fn(*args)
        times.append(time.perf_counter() - t0)
    avg = statistics.mean(times)
    std = statistics.stdev(times) if len(times) > 1 else 0
    return avg, std, result


def fmt_ms(avg_ms, std_ms):
    return f"{avg_ms:>8.2f}ms (±{std_ms:.2f})"


# ─── Accuracy helpers ───

WORD_RE = re.compile(r"\w+")


def text_from_flashpdf(blocks):
    """Join text spans in reading order."""
    return "".join(
        span["text"]
        for block in blocks
        for line in block.get("lines", [])
        for span in line["spans"]
    )


def text_from_pymupdf(pages):
    out = []
    for page in pages:
        for block in page["blocks"]:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line.get("spans", []):
                    out.append(span.get("text", ""))
    return "".join(out)


def count_struct_flashpdf(blocks):
    nb = nl = ns = nc = 0
    for block in blocks:
        nb += 1
        for line in block.get("lines", []):
            nl += 1
            for span in line["spans"]:
                ns += 1
                nc += len(span["text"])
    return {"blocks": nb, "lines": nl, "spans": ns, "chars": nc}


def count_struct_pymupdf(pages):
    nb = nl = ns = nc = 0
    for page in pages:
        for block in page["blocks"]:
            if "lines" not in block:
                continue
            nb += 1
            for line in block["lines"]:
                nl += 1
                for span in line.get("spans", []):
                    ns += 1
                    nc += len(span.get("text", ""))
    return {"blocks": nb, "lines": nl, "spans": ns, "chars": nc}


def word_metrics(text_a, text_b):
    """Compute precision/recall/Jaccard on word sets."""
    words_a = set(WORD_RE.findall(text_a.lower()))
    words_b = set(WORD_RE.findall(text_b.lower()))
    if not words_a and not words_b:
        return {"a_count": 0, "b_count": 0, "common": 0, "jaccard": 0, "precision": 0, "recall": 0}
    common = words_a & words_b
    union = words_a | words_b
    return {
        "a_count": len(words_a),
        "b_count": len(words_b),
        "common": len(common),
        "jaccard": len(common) / len(union) if union else 0,
        "precision": len(common) / len(words_a) if words_a else 0,
        "recall": len(common) / len(words_b) if words_b else 0,
    }


def fffd_count(text):
    return text.count("\ufffd")


def char_similarity(text_a, text_b):
    """Char-level similarity via SequenceMatcher ratio.
    Sensitive to reading order — different orders will score low."""
    return SequenceMatcher(None, text_a, text_b, autojunk=False).ratio()


def set_jaccard(text_a, text_b):
    """Order-insensitive char trigram Jaccard similarity.
    A better proxy for content overlap when reading order differs."""
    def trigrams(t):
        return {t[i:i + 3] for i in range(len(t) - 2)} if len(t) >= 3 else {t}

    a = trigrams(text_a)
    b = trigrams(text_b)
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


# ─── Main ───

def main():
    print("=" * 70)
    print(f"flashpdf {flashpdf.__version__}  vs  PyMuPDF {fitz.__version__}")
    print(f"Iters per benchmark: {ITERS}")
    print("=" * 70)

    all_results = []

    for name, path in PDFS:
        print(f"\n## PDF: {name} ({path})")
        try:
            with open(path, "rb"):
                pass
        except FileNotFoundError:
            print(f"  SKIP (file not found)")
            continue

        # Warmup
        flashpdf.extract(path, include_images=False)
        fitz.open(path).close()

        n_pages = len(fitz.open(path))
        print(f"  Pages: {n_pages}")

        # ── Performance: text only ──
        fp_text_avg, fp_text_std, _ = bench("flashpdf-text", flashpdf_extract_text, path)
        pm_text_avg, pm_text_std, _ = bench("pymupdf-text", pymupdf_extract_text, path)
        text_speedup = pm_text_avg / fp_text_avg if fp_text_avg > 0 else 0

        # ── Performance: text + images ──
        fp_full_avg, fp_full_std, (fp_blocks, fp_images) = bench(
            "flashpdf-full", flashpdf_extract_full, path
        )
        pm_full_avg, pm_full_std, pm_result = bench(
            "pymupdf-full", pymupdf_extract_full, path
        )
        full_speedup = pm_full_avg / fp_full_avg if fp_full_avg > 0 else 0

        # ── Accuracy ──
        fp_text = text_from_flashpdf(fp_blocks)
        pm_text = text_from_pymupdf(pm_result["pages"])
        metrics = word_metrics(fp_text, pm_text)
        char_sim = char_similarity(fp_text, pm_text)
        trigram_jac = set_jaccard(fp_text, pm_text)
        fp_struct = count_struct_flashpdf(fp_blocks)
        pm_struct = count_struct_pymupdf(pm_result["pages"])
        fp_fffd = fffd_count(fp_text)

        # Print summary
        print("\n  -- Performance --")
        print(f"  text only       flashpdf: {fmt_ms(fp_text_avg*1000, fp_text_std*1000)}")
        print(f"                   pymupdf: {fmt_ms(pm_text_avg*1000, pm_text_std*1000)}")
        print(f"                   speedup: {text_speedup:.2f}x")
        print(f"  text + images   flashpdf: {fmt_ms(fp_full_avg*1000, fp_full_std*1000)}")
        print(f"                   pymupdf: {fmt_ms(pm_full_avg*1000, pm_full_std*1000)}")
        print(f"                   speedup: {full_speedup:.2f}x")
        print(f"  throughput      flashpdf: {n_pages/fp_text_avg:>7.1f} pages/sec")
        print(f"                   pymupdf: {n_pages/pm_text_avg:>7.1f} pages/sec")

        print("\n  -- Accuracy (flashpdf vs pymupdf) --")
        print(f"  word overlap    jaccard:  {metrics['jaccard']*100:.1f}%")
        print(f"                  recall:   {metrics['recall']*100:.1f}% (flashpdf covering pymupdf)")
        print(f"                  precision:{metrics['precision']*100:.1f}% (flashpdf not over-extracting)")
        print(f"  char similarity (ordered): {char_sim*100:.1f}%")
        print(f"  trigram jaccard (unordered): {trigram_jac*100:.1f}%")
        print(f"  unique words    flashpdf: {metrics['a_count']}")
        print(f"                   pymupdf: {metrics['b_count']}")
        print(f"  shared words:   {metrics['common']}")

        print("\n  -- Structure --")
        print(f"  {'metric':<10} {'flashpdf':>10} {'pymupdf':>10}")
        print(f"  {'blocks':<10} {fp_struct['blocks']:>10} {pm_struct['blocks']:>10}")
        print(f"  {'lines':<10} {fp_struct['lines']:>10} {pm_struct['lines']:>10}")
        print(f"  {'spans':<10} {fp_struct['spans']:>10} {pm_struct['spans']:>10}")
        print(f"  {'chars':<10} {fp_struct['chars']:>10} {pm_struct['chars']:>10}")
        print(f"  {'images':<10} {len(fp_images):>10} {len(pm_result['pages'][0]['images']) if pm_result['pages'] else 0:>10}  (page 0 only for pymupdf)")
        print(f"  FFFD chars:     {fp_fffd}  (flashpdf)")

        all_results.append({
            "name": name,
            "pages": n_pages,
            "text_speedup": text_speedup,
            "full_speedup": full_speedup,
            "fp_text_ms": fp_text_avg * 1000,
            "pm_text_ms": pm_text_avg * 1000,
            "jaccard": metrics["jaccard"],
            "recall": metrics["recall"],
            "precision": metrics["precision"],
            "char_sim": char_sim,
            "trigram_jac": trigram_jac,
            "fp_words": metrics["a_count"],
            "pm_words": metrics["b_count"],
            "common": metrics["common"],
            "fp_fffd": fp_fffd,
        })

    # ── Summary across PDFs ──
    if all_results:
        print("\n" + "=" * 70)
        print("Summary across all PDFs")
        print("=" * 70)
        print(f"{'PDF':<14} {'pages':>6} {'text↑':>8} {'full↑':>8} {'char_sim':>9} {'trigram':>9} {'jaccard':>9} {'FFFD':>6}")
        for r in all_results:
            print(f"{r['name']:<14} {r['pages']:>6} "
                  f"{r['text_speedup']:>7.2f}x {r['full_speedup']:>7.2f}x "
                  f"{r['char_sim']*100:>8.1f}% {r['trigram_jac']*100:>8.1f}% "
                  f"{r['jaccard']*100:>8.1f}% {r['fp_fffd']:>6}")


if __name__ == "__main__":
    main()
