# Performance tuning guide

This guide covers where flashpdf is fast, where it's slow, and how to
pick the right API for your workload.

## TL;DR — pick the right API

| Workload | Use |
| --- | --- |
| One PDF, plain text | `doc = open(path); doc[0].get_text("text")` |
| One PDF, structured blocks | `doc[i].get_text("dict")` |
| 1–10 PDFs | `extract(path)` in a loop |
| 10–10,000 PDFs | `extract_many(paths)` (parallel) |
| You already have bytes / mmap | `extract_doc(&doc, opts)` (Rust only) |
| Tiny PDFs (< 10 KB) | `open()` or `extract()` — both ~0.01ms |

## Latency by file size

Measured on Apple M2, release build, single-threaded. Numbers are
end-to-end including file open + mmap + parse + extract:

| File size | Pages | p50 | p90 |
| --- | --- | --- | --- |
| 1 KB (1-page stub) | 1 | 0.012 ms | 0.018 ms |
| 100 KB (typical Word export) | 2–5 | 0.5 ms | 0.8 ms |
| 1 MB (academic paper) | 14 | 5 ms | 8 ms |
| 10 MB (corporate report) | 100 | 60 ms | 90 ms |
| 100 MB (scanned book) | 500 | 800 ms | 1.2 s |

For comparison, PyMuPDF is typically 3–10x slower on text-heavy PDFs.

## Why flashpdf is fast

1. **mmap + zero-copy parsing** — file bytes are never copied; the parser
   borrows directly from the mmap region. Per-object lifetimes are tied
   to the mmap via `Box::leak` for cached objects.
2. **Parallel page extraction** — within a single PDF, pages are
   processed via rayon (page-parallel). This is on by default.
3. **Parallel file extraction** — `extract_many()` parallelizes across
   files (file-parallel) once the file count ≥ 8.
4. **Lazy font parsing** — fonts are parsed on first reference, not
   eagerly at open. Many PDFs only use 2–3 of their declared fonts.
5. **No rendering** — flashpdf extracts text/image metadata only, never
   rasterizes. This is the single largest gap vs fitz (which does
   rendering) and the largest perf win.

## Tuning knobs

### `ExtractOptions`

| Option | Default | When to change |
| --- | --- | --- |
| `include_images` | `True` | Set `False` for text-only pipelines (2–3x faster) |
| `page_parallel` | `True` | Set `False` only for tiny PDFs (saves rayon overhead) |
| `file_parallel` | `True` | Set `False` if you're already in a parallel outer loop |
| `batch_size` | `50` | Lower for memory-constrained envs; raise for max throughput |
| `gpu` | `False` | Reserved for future GPU image decode |
| `include_rotated` | `False` | Set `True` if you need vertical/sideways text |

### Decision tree: `extract()` vs `extract_many()` vs `open()`

```
How many PDFs?
├── 1        → open()  (eager extraction, fitz-style API)
├── 2–7      → extract()  in a loop (sequential is fine)
├── 8–10k    → extract_many()  (file-parallel via rayon)
└── 10k+     → extract_many() in chunks of 1k–5k (avoid rayon oversubscription)
```

### `get_text()` mode

```
What do you need?
├── Plain prose           → get_text("text")   ~5x cheaper than "dict"
├── Layout-aware blocks   → get_text("dict")
├── Tuple-of-text-blocks  → get_text("blocks") (same cost as "dict")
└── Image bytes           → page.get_images()  (only if you need bytes)
```

## Profiling

### Tracing

flashpdf exposes Rust-side tracing spans. From Python:

```python
import flashpdf
flashpdf.set_log_level("debug")  # or "trace", "info", "warn", "error", "off"
doc = flashpdf.open("paper.pdf")  # prints tracing spans
flashpdf.set_log_level("off")
```

Or via env var (equivalent):

```
RUST_LOG=flashpdf_core=debug python your_script.py
```

### Flamegraph

For deeper profiling, build with perf symbols and run cargo flamegraph:

```bash
cargo install flamegraph
cargo flamegraph --release --bench extraction -- --bench
```

The dominant hot spots in a typical run are:

1. `flate2::CrcReader::read` (decompression checksum) — unavoidable
2. `font::build_font_map` — first-page cost; cached for subsequent pages
3. `layout::cluster_chars` — proportional to char count

## When flashpdf is slow

- **Encrypted PDFs** — RC4/AES decryption adds ~30% over plaintext.
- **Many small objects** — Word exports with 1000+ ObjStm entries pay
  extra xref-walk cost.
- **Broken xref tables** — recovery scan reads the whole file linearly.
  Use `RUST_LOG=flashpdf_core::recovery=debug` to detect this.
- **Image-heavy PDFs with `include_images=True`** — PNG encoding
  dominates. Set `include_images=False` if you only need text.

## Memory

flashpdf holds the mmap for the duration of `open()` and releases it
when `Document` is dropped. Peak RSS for a 100 MB PDF is roughly
`100 MB (mmap) + 2–10 MB (parsed object cache + decoded streams)`.
For comparison, fitz typically uses 200–400 MB for the same file.

If you're processing thousands of PDFs in sequence, `extract()`
automatically releases the mmap between files. For `extract_many()`,
each worker thread holds one mmap at a time.

## Benchmarks

The benchmark suite lives in `crates/flashpdf-core/benches/extraction.rs`.
Run with:

```bash
cargo bench -p flashpdf-core
```

Results are written to `target/criterion/extraction/`. CI runs this on
every PR; regressions of > 10% on any sub-bucket block the merge.
