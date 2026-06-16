"""
Comprehensive benchmark: fastpdf vs ritz vs GoMuPDF vs PyMuPDF
Tests: text extraction, image extraction, combined
"""
import time
import sys
import statistics
import subprocess
import json

sys.path.insert(0, "/Users/xiongzhaolong/Downloads/claude-pro/202604-job/pdf_pro/ritz/python")
sys.path.insert(0, "/Users/xiongzhaolong/Downloads/claude_pro/fastpdf/python")

PDF_PATH = "/Users/xiongzhaolong/Downloads/claude_pro/fastpdf/test_data/2604.11578v1.pdf"
GOMUPDF_BIN = "/tmp/bench_gomupdf"
ITERS = 10
WARMUP = 2


def run_bench(func, *args, iters=ITERS, warmup=WARMUP):
    for _ in range(warmup):
        func(*args)
    times = []
    for _ in range(iters):
        start = time.perf_counter()
        func(*args)
        times.append(time.perf_counter() - start)
    avg = statistics.mean(times)
    std = statistics.stdev(times) if len(times) > 1 else 0
    return avg, std


def print_header(title):
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


def print_row(name, avg_ms, std_ms, base_ms):
    speedup = base_ms / avg_ms if avg_ms > 0 else 0
    bar = "█" * min(int(speedup), 50)
    print(f"  {name:<12} {avg_ms:>8.2f}ms  {speedup:>6.2f}x  {bar}")


# ============ PyMuPDF ============

def bench_pymupdf_text(pdf_path):
    import fitz
    doc = fitz.open(pdf_path)
    for page in doc:
        page.get_text("dict")
    doc.close()

def bench_pymupdf_images(pdf_path):
    import fitz
    doc = fitz.open(pdf_path)
    for page in doc:
        for img in page.get_images(full=True):
            doc.extract_image(img[0])
    doc.close()

def bench_pymupdf_combined(pdf_path):
    import fitz
    doc = fitz.open(pdf_path)
    for page in doc:
        page.get_text("dict")
        for img in page.get_images(full=True):
            doc.extract_image(img[0])
    doc.close()


# ============ ritz ============

def bench_ritz_text(pdf_path):
    import ritz
    doc = ritz.open(pdf_path)
    for i in range(doc.page_count):
        page = doc.load_page(i)
        page.get_text("dict")
    del doc

def bench_ritz_images(pdf_path):
    import ritz
    doc = ritz.open(pdf_path)
    for i in range(doc.page_count):
        page = doc.load_page(i)
        page.get_images(include_data=True)
    del doc

def bench_ritz_combined(pdf_path):
    import ritz
    doc = ritz.open(pdf_path)
    for i in range(doc.page_count):
        page = doc.load_page(i)
        page.get_text("dict")
        page.get_images(include_data=True)
    del doc


# ============ fastpdf ============

def bench_fastpdf_text(pdf_path):
    import fastpdf
    fastpdf.extract(pdf_path, include_images=False)

def bench_fastpdf_images(pdf_path):
    import fastpdf
    fastpdf.extract(pdf_path, include_images=True)

def bench_fastpdf_combined(pdf_path):
    import fastpdf
    fastpdf.extract(pdf_path, include_images=True)


# ============ GoMuPDF ============

def bench_gomupdf_text(pdf_path):
    result = subprocess.run(
        [GOMUPDF_BIN, pdf_path, "--text-only"],
        capture_output=True, text=True, timeout=30
    )

def bench_gomupdf_images(pdf_path):
    result = subprocess.run(
        [GOMUPDF_BIN, pdf_path, "--images-only"],
        capture_output=True, text=True, timeout=30
    )

def bench_gomupdf_combined(pdf_path):
    result = subprocess.run(
        [GOMUPDF_BIN, pdf_path, "--combined"],
        capture_output=True, text=True, timeout=30
    )


def print_table(title, results):
    """results: list of (name, avg, std)"""
    base = results[0][1]  # PyMuPDF as base
    print_header(title)
    print(f"  {'Engine':<12} {'Avg (ms)':>10} {'Std (ms)':>10} {'vs PyMuPDF':>12} {'vs fastpdf':>12}")
    print(f"  {'-' * 58}")
    for name, avg, std in results:
        speedup = base / avg if avg > 0 else 0
        fastpdf_ratio = results[2][1] / avg if avg > 0 and len(results) > 2 else 0
        if name == "fastpdf":
            print(f"  {name:<12} {avg*1000:>10.2f} {std*1000:>10.2f} {speedup:>10.2f}x  {'---':>12}")
        elif name == "PyMuPDF":
            print(f"  {name:<12} {avg*1000:>10.2f} {std*1000:>10.2f} {'1.00x':>12} {fastpdf_ratio:>10.2f}x")
        else:
            print(f"  {name:<12} {avg*1000:>10.2f} {std*1000:>10.2f} {speedup:>10.2f}x {fastpdf_ratio:>10.2f}x")


def main():
    pdf_path = PDF_PATH
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]

    print(f"PDF: {pdf_path}")
    print(f"Iterations: {ITERS} (warmup: {WARMUP})")

    import fitz
    import ritz
    import fastpdf

    # Count pages/images
    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    img_count = sum(len(page.get_images(full=True)) for page in doc)
    doc.close()
    print(f"Pages: {page_count}, Images: {img_count}")

    # Check GoMuPDF
    import os
    gomupdf_available = os.path.exists(GOMUPDF_BIN)

    # Text extraction
    pymupdf_avg, pymupdf_std = run_bench(bench_pymupdf_text, pdf_path)
    ritz_avg, ritz_std = run_bench(bench_ritz_text, pdf_path)
    fastpdf_avg, fastpdf_std = run_bench(bench_fastpdf_text, pdf_path)

    text_results = [
        ("PyMuPDF", pymupdf_avg, pymupdf_std),
        ("ritz", ritz_avg, ritz_std),
        ("fastpdf", fastpdf_avg, fastpdf_std),
    ]

    if gomupdf_available:
        gomupdf_avg, gomupdf_std = run_bench(bench_gomupdf_text, pdf_path, iters=5, warmup=1)
        text_results.append(("GoMuPDF", gomupdf_avg, gomupdf_std))

    print_table("Text Extraction", text_results)

    # Image extraction
    pymupdf_avg, pymupdf_std = run_bench(bench_pymupdf_images, pdf_path)
    ritz_avg, ritz_std = run_bench(bench_ritz_images, pdf_path)
    fastpdf_avg, fastpdf_std = run_bench(bench_fastpdf_images, pdf_path)

    img_results = [
        ("PyMuPDF", pymupdf_avg, pymupdf_std),
        ("ritz", ritz_avg, ritz_std),
        ("fastpdf", fastpdf_avg, fastpdf_std),
    ]

    if gomupdf_available:
        gomupdf_avg, gomupdf_std = run_bench(bench_gomupdf_images, pdf_path, iters=5, warmup=1)
        img_results.append(("GoMuPDF", gomupdf_avg, gomupdf_std))

    print_table("Image Extraction", img_results)

    # Combined
    pymupdf_avg, pymupdf_std = run_bench(bench_pymupdf_combined, pdf_path)
    ritz_avg, ritz_std = run_bench(bench_ritz_combined, pdf_path)
    fastpdf_avg, fastpdf_std = run_bench(bench_fastpdf_combined, pdf_path)

    combined_results = [
        ("PyMuPDF", pymupdf_avg, pymupdf_std),
        ("ritz", ritz_avg, ritz_std),
        ("fastpdf", fastpdf_avg, fastpdf_std),
    ]

    if gomupdf_available:
        gomupdf_avg, gomupdf_std = run_bench(bench_gomupdf_combined, pdf_path, iters=5, warmup=1)
        combined_results.append(("GoMuPDF", gomupdf_avg, gomupdf_std))

    print_table("Text + Image Combined", combined_results)

    # Summary
    print_header("SUMMARY")
    print(f"""
  fastpdf: {fastpdf_avg*1000:.2f}ms (text+images)
  ritz:    {ritz_avg*1000:.2f}ms
  PyMuPDF: {pymupdf_avg*1000:.2f}ms
  GoMuPDF: {gomupdf_avg*1000:.2f}ms (if available)

  fastpdf vs PyMuPDF: {pymupdf_avg/fastpdf_avg:.1f}x
  fastpdf vs ritz:    {ritz_avg/fastpdf_avg:.1f}x
  fastpdf vs GoMuPDF: {gomupdf_avg/fastpdf_avg:.1f}x (if available)
""")


if __name__ == "__main__":
    main()
