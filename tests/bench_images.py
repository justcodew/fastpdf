"""
Benchmark: image extraction and multi-file throughput.
Tests the 3 untested performance goals from README.
"""
import time
import os
import statistics

PDF_PATH = "test_data/2604.11578v1.pdf"
ITERATIONS = 10
WARMUP = 2


def bench_image_metadata():
    """图像元数据 (仅记录偏移): fastpdf vs PyMuPDF"""
    import fastpdf
    import fitz

    print("=" * 60)
    print("1. 图像元数据提取 (仅记录偏移)")
    print("=" * 60)

    # Warmup
    for _ in range(WARMUP):
        fastpdf.extract(PDF_PATH, include_images=False)
        doc = fitz.open(PDF_PATH)
        for page in doc:
            page.get_images(full=True)
        doc.close()

    # PyMuPDF: image metadata only
    pymupdf_times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        doc = fitz.open(PDF_PATH)
        for page in doc:
            images = page.get_images(full=True)
        doc.close()
        pymupdf_times.append(time.perf_counter() - start)

    # fastpdf: image metadata only (include_images=False skips byte extraction)
    fastpdf_times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        blocks, images = fastpdf.extract(PDF_PATH, include_images=False)
        fastpdf_times.append(time.perf_counter() - start)

    pm_avg = statistics.mean(pymupdf_times)
    fp_avg = statistics.mean(fastpdf_times)
    speedup = pm_avg / fp_avg if fp_avg > 0 else float('inf')

    print(f"  PyMuPDF:  {pm_avg*1000:.2f}ms")
    print(f"  fastpdf:  {fp_avg*1000:.2f}ms")
    print(f"  加速比:   {speedup:.1f}x")
    print(f"  目标:     ≥ 50x")
    print(f"  结果:     {'✅ 达标' if speedup >= 50 else '❌ 未达标'}")
    return speedup


def bench_image_bytes():
    """图像字节提取 (含解码): fastpdf vs PyMuPDF"""
    import fastpdf
    import fitz

    print("\n" + "=" * 60)
    print("2. 图像字节提取 (含解码)")
    print("=" * 60)

    # Warmup
    for _ in range(WARMUP):
        fastpdf.extract(PDF_PATH, include_images=True)
        doc = fitz.open(PDF_PATH)
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                pix = None
        doc.close()

    # PyMuPDF: extract image bytes
    pymupdf_times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        doc = fitz.open(PDF_PATH)
        img_count = 0
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                    _ = pix.tobytes()
                    pix = None
                except:
                    pass
                img_count += 1
        doc.close()
        pymupdf_times.append(time.perf_counter() - start)

    # fastpdf: extract image bytes
    fastpdf_times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        blocks, images = fastpdf.extract(PDF_PATH, include_images=True)
        fastpdf_times.append(time.perf_counter() - start)

    pm_avg = statistics.mean(pymupdf_times)
    fp_avg = statistics.mean(fastpdf_times)
    speedup = pm_avg / fp_avg if fp_avg > 0 else float('inf')

    print(f"  PyMuPDF:  {pm_avg*1000:.2f}ms  ({img_count} images)")
    print(f"  fastpdf:  {fp_avg*1000:.2f}ms  ({len(images)} images)")
    print(f"  加速比:   {speedup:.1f}x")
    print(f"  目标:     ≥ 5x")
    print(f"  结果:     {'✅ 达标' if speedup >= 5 else '❌ 未达标'}")
    return speedup


def bench_multi_file():
    """多文件吞吐量: 单文件 vs 多文件并行"""
    import fastpdf
    import fitz

    print("\n" + "=" * 60)
    print("3. 多文件吞吐量")
    print("=" * 60)

    # Check how many test PDFs we have
    test_dir = "test_data"
    pdf_files = [os.path.join(test_dir, f) for f in os.listdir(test_dir) if f.endswith(".pdf")]

    if len(pdf_files) < 2:
        print(f"  只有 {len(pdf_files)} 个 PDF 文件，跳过多文件测试")
        return None

    print(f"  测试文件数: {len(pdf_files)}")

    # Warmup
    for _ in range(WARMUP):
        for pdf in pdf_files:
            fastpdf.extract(pdf, include_images=False)

    # Sequential: one by one
    seq_times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        for pdf in pdf_files:
            fastpdf.extract(pdf, include_images=False)
        seq_times.append(time.perf_counter() - start)

    # Parallel: extract_many with file_parallel=True
    par_times = []
    for _ in range(ITERATIONS):
        start = time.perf_counter()
        results = list(fastpdf.extract_many(pdf_files, file_parallel=True, include_images=False))
        par_times.append(time.perf_counter() - start)

    seq_avg = statistics.mean(seq_times)
    par_avg = statistics.mean(par_times)
    speedup = seq_avg / par_avg if par_avg > 0 else float('inf')

    cpu_count = os.cpu_count() or 1

    print(f"  串行:     {seq_avg*1000:.2f}ms")
    print(f"  并行:     {par_avg*1000:.2f}ms")
    print(f"  加速比:   {speedup:.1f}x")
    print(f"  CPU 核心: {cpu_count}")
    print(f"  目标:     近核心数线性增长")
    print(f"  结果:     {'✅ 达标' if speedup >= cpu_count * 0.5 else '⚠️  部分达标'}")
    return speedup


if __name__ == "__main__":
    print("fastpdf 性能基准测试")
    print(f"测试文件: {PDF_PATH}")
    print(f"迭代次数: {ITERATIONS} (warmup {WARMUP})")
    print()

    s1 = bench_image_metadata()
    s2 = bench_image_bytes()
    s3 = bench_multi_file()

    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)
    if s1: print(f"  图像元数据: {s1:.1f}x (目标 ≥50x)")
    if s2: print(f"  图像字节:   {s2:.1f}x (目标 ≥5x)")
    if s3: print(f"  多文件并行: {s3:.1f}x (目标近核心数)")
