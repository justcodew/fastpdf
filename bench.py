"""Benchmark: fastpdf vs PyMuPDF on a real PDF."""
import time
import sys

PDF_PATH = "D:/data_2025/code/claude_pro/test_data/2604.11578v1.pdf"
RUNS = 10

# ─── PyMuPDF benchmark ───

def bench_pymupdf():
    import fitz  # PyMuPDF

    # Warm up
    doc = fitz.open(PDF_PATH)
    for page in doc:
        _ = page.get_text("dict")
    doc.close()

    times = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        doc = fitz.open(PDF_PATH)
        total_chars = 0
        total_blocks = 0
        total_lines = 0
        total_spans = 0
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            for b in blocks:
                if b.get("type") == 0:
                    total_blocks += 1
                    for line in b["lines"]:
                        total_lines += 1
                        for span in line["spans"]:
                            total_spans += 1
                            total_chars += len(span["text"])
        doc.close()
        times.append(time.perf_counter() - t0)

    avg = sum(times) / len(times)
    pages = 14
    return {
        "name": "PyMuPDF",
        "pages": pages,
        "chars": total_chars,
        "blocks": total_blocks,
        "lines": total_lines,
        "spans": total_spans,
        "avg_ms": avg * 1000,
        "pages_sec": pages / avg,
        "runs": RUNS,
    }

# ─── fastpdf benchmark ───

def bench_fastpdf():
    import fastpdf

    # Warm up
    blocks, images = fastpdf.extract(PDF_PATH, page_parallel=False, include_images=False)

    times = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        blocks, images = fastpdf.extract(PDF_PATH, page_parallel=False, include_images=False)
        times.append(time.perf_counter() - t0)

    total_chars = 0
    total_blocks = 0
    total_lines = 0
    total_spans = 0
    for b in blocks:
        total_blocks += 1
        for line in b["lines"]:
            total_lines += 1
            for span in line["spans"]:
                total_spans += 1
                total_chars += len(span["text"])

    avg = sum(times) / len(times)
    pages = 14
    return {
        "name": "fastpdf (seq)",
        "pages": pages,
        "chars": total_chars,
        "blocks": total_blocks,
        "lines": total_lines,
        "spans": total_spans,
        "avg_ms": avg * 1000,
        "pages_sec": pages / avg,
        "runs": RUNS,
    }

def bench_fastpdf_parallel():
    import fastpdf

    # Warm up
    blocks, images = fastpdf.extract(PDF_PATH, page_parallel=True, include_images=False)

    times = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        blocks, images = fastpdf.extract(PDF_PATH, page_parallel=True, include_images=False)
        times.append(time.perf_counter() - t0)

    total_chars = 0
    total_blocks = 0
    total_lines = 0
    total_spans = 0
    for b in blocks:
        total_blocks += 1
        for line in b["lines"]:
            total_lines += 1
            for span in line["spans"]:
                total_spans += 1
                total_chars += len(span["text"])

    avg = sum(times) / len(times)
    pages = 14
    return {
        "name": "fastpdf (par)",
        "pages": pages,
        "chars": total_chars,
        "blocks": total_blocks,
        "lines": total_lines,
        "spans": total_spans,
        "avg_ms": avg * 1000,
        "pages_sec": pages / avg,
        "runs": RUNS,
    }

# ─── Main ───

if __name__ == "__main__":
    print(f"PDF: {PDF_PATH}")
    print(f"Runs: {RUNS}")
    print()

    pymupdf_result = bench_pymupdf()
    fastpdf_result = bench_fastpdf()
    fastpdf_par_result = bench_fastpdf_parallel()

    # Print comparison table
    header = f"{'Engine':<18} {'Pages':>5} {'Chars':>7} {'Blocks':>7} {'Lines':>6} {'Spans':>7} {'Avg(ms)':>9} {'Pages/s':>9}"
    print(header)
    print("-" * len(header))
    for r in [pymupdf_result, fastpdf_result, fastpdf_par_result]:
        print(f"{r['name']:<18} {r['pages']:>5} {r['chars']:>7} {r['blocks']:>7} {r['lines']:>6} {r['spans']:>7} {r['avg_ms']:>9.1f} {r['pages_sec']:>9.0f}")

    # Speedup
    if pymupdf_result['avg_ms'] > 0:
        seq_speedup = pymupdf_result['avg_ms'] / fastpdf_result['avg_ms']
        par_speedup = pymupdf_result['avg_ms'] / fastpdf_par_result['avg_ms']
        print()
        print(f"Speedup (sequential): {seq_speedup:.2f}x")
        print(f"Speedup (parallel):   {par_speedup:.2f}x")
