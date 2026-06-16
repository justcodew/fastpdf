"""
Compare extraction speed: fastpdf vs ritz vs PyMuPDF (text + images)
"""
import time
import sys
import statistics

PDF_PATH = "/Users/xiongzhaolong/Downloads/claude_pro/fastpdf/test_data/2604.11578v1.pdf"
ITERS = 5
WARMUP = 1


def run_bench(name, func, pdf_path, iters):
    # Warmup
    for _ in range(WARMUP):
        func(pdf_path, 1)
    # Benchmark
    times = func(pdf_path, iters)
    avg = statistics.mean(times)
    std = statistics.stdev(times) if len(times) > 1 else 0
    return avg, std


# ============ Text Extraction ============

def bench_pymupdf_text(pdf_path, iters):
    import fitz
    times = []
    for _ in range(iters):
        start = time.perf_counter()
        doc = fitz.open(pdf_path)
        for page in doc:
            page.get_text("dict")
        doc.close()
        times.append(time.perf_counter() - start)
    return times


def bench_ritz_text(pdf_path, iters):
    sys.path.insert(0, "/Users/xiongzhaolong/Downloads/claude-pro/202604-job/pdf_pro/ritz/python")
    import ritz
    times = []
    for _ in range(iters):
        start = time.perf_counter()
        doc = ritz.open(pdf_path)
        for i in range(doc.page_count):
            page = doc.load_page(i)
            page.get_text("dict")
        del doc
        times.append(time.perf_counter() - start)
    return times


def bench_fastpdf_text(pdf_path, iters):
    sys.path.insert(0, "/Users/xiongzhaolong/Downloads/claude_pro/fastpdf/python")
    import fastpdf
    times = []
    for _ in range(iters):
        start = time.perf_counter()
        blocks, images = fastpdf.extract(pdf_path, include_images=False)
        times.append(time.perf_counter() - start)
    return times


# ============ Image Extraction ============

def bench_pymupdf_images(pdf_path, iters):
    import fitz
    times = []
    for _ in range(iters):
        start = time.perf_counter()
        doc = fitz.open(pdf_path)
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                doc.extract_image(xref)
        doc.close()
        times.append(time.perf_counter() - start)
    return times


def bench_ritz_images(pdf_path, iters):
    sys.path.insert(0, "/Users/xiongzhaolong/Downloads/claude-pro/202604-job/pdf_pro/ritz/python")
    import ritz
    times = []
    for _ in range(iters):
        start = time.perf_counter()
        doc = ritz.open(pdf_path)
        for i in range(doc.page_count):
            page = doc.load_page(i)
            page.get_images(include_data=True)
        del doc
        times.append(time.perf_counter() - start)
    return times


def bench_fastpdf_images(pdf_path, iters):
    sys.path.insert(0, "/Users/xiongzhaolong/Downloads/claude_pro/fastpdf/python")
    import fastpdf
    times = []
    for _ in range(iters):
        start = time.perf_counter()
        blocks, images = fastpdf.extract(pdf_path, include_images=True)
        times.append(time.perf_counter() - start)
    return times


# ============ Combined (text + images) ============

def bench_pymupdf_combined(pdf_path, iters):
    import fitz
    times = []
    for _ in range(iters):
        start = time.perf_counter()
        doc = fitz.open(pdf_path)
        for page in doc:
            page.get_text("dict")
            for img in page.get_images(full=True):
                doc.extract_image(img[0])
        doc.close()
        times.append(time.perf_counter() - start)
    return times


def bench_ritz_combined(pdf_path, iters):
    sys.path.insert(0, "/Users/xiongzhaolong/Downloads/claude-pro/202604-job/pdf_pro/ritz/python")
    import ritz
    times = []
    for _ in range(iters):
        start = time.perf_counter()
        doc = ritz.open(pdf_path)
        for i in range(doc.page_count):
            page = doc.load_page(i)
            page.get_text("dict")
            page.get_images(include_data=True)
        del doc
        times.append(time.perf_counter() - start)
    return times


def bench_fastpdf_combined(pdf_path, iters):
    sys.path.insert(0, "/Users/xiongzhaolong/Downloads/claude_pro/fastpdf/python")
    import fastpdf
    times = []
    for _ in range(iters):
        start = time.perf_counter()
        blocks, images = fastpdf.extract(pdf_path, include_images=True)
        times.append(time.perf_counter() - start)
    return times


def print_table(title, results):
    """results: list of (name, avg, std)"""
    base = results[0][1]  # PyMuPDF as base
    print(f"\n{'=' * 55}")
    print(f"{title}")
    print(f"{'=' * 55}")
    print(f"{'Engine':<12} {'Avg (ms)':>10} {'Std (ms)':>10} {'Speedup':>10}")
    print("-" * 45)
    for name, avg, std in results:
        speedup = base / avg if avg > 0 else 0
        print(f"{name:<12} {avg*1000:>10.2f} {std*1000:>10.2f} {speedup:>9.2f}x")
    # fastpdf vs ritz
    if len(results) >= 3:
        ritz_avg = results[1][1]
        fastpdf_avg = results[2][1]
        if fastpdf_avg > 0:
            print(f"\n{'fastpdf vs ritz:':<20} {ritz_avg/fastpdf_avg:.2f}x")


def main():
    pdf_path = PDF_PATH
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]

    print(f"PDF: {pdf_path}")
    print(f"Iterations: {ITERS} (warmup: {WARMUP})")

    # Text extraction
    pymupdf_avg, pymupdf_std = run_bench("PyMuPDF text", bench_pymupdf_text, pdf_path, ITERS)
    ritz_avg, ritz_std = run_bench("ritz text", bench_ritz_text, pdf_path, ITERS)
    fastpdf_avg, fastpdf_std = run_bench("fastpdf text", bench_fastpdf_text, pdf_path, ITERS)
    print_table("Text Extraction", [
        ("PyMuPDF", pymupdf_avg, pymupdf_std),
        ("ritz", ritz_avg, ritz_std),
        ("fastpdf", fastpdf_avg, fastpdf_std),
    ])

    # Image extraction
    pymupdf_avg, pymupdf_std = run_bench("PyMuPDF images", bench_pymupdf_images, pdf_path, ITERS)
    ritz_avg, ritz_std = run_bench("ritz images", bench_ritz_images, pdf_path, ITERS)
    fastpdf_avg, fastpdf_std = run_bench("fastpdf images", bench_fastpdf_images, pdf_path, ITERS)
    print_table("Image Extraction", [
        ("PyMuPDF", pymupdf_avg, pymupdf_std),
        ("ritz", ritz_avg, ritz_std),
        ("fastpdf", fastpdf_avg, fastpdf_std),
    ])

    # Combined
    pymupdf_avg, pymupdf_std = run_bench("PyMuPDF combined", bench_pymupdf_combined, pdf_path, ITERS)
    ritz_avg, ritz_std = run_bench("ritz combined", bench_ritz_combined, pdf_path, ITERS)
    fastpdf_avg, fastpdf_std = run_bench("fastpdf combined", bench_fastpdf_combined, pdf_path, ITERS)
    print_table("Text + Image Combined", [
        ("PyMuPDF", pymupdf_avg, pymupdf_std),
        ("ritz", ritz_avg, ritz_std),
        ("fastpdf", fastpdf_avg, fastpdf_std),
    ])


if __name__ == "__main__":
    main()
