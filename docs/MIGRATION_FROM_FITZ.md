# Migrating from PyMuPDF (`fitz`) to `flashpdf`

This guide covers the common deltas when porting code that uses
`import fitz` (PyMuPDF) to `import flashpdf`. flashpdf intentionally
mirrors the **shape** of the fitz API for text/image extraction, but
only implements that subset — it is not a drop-in replacement for
rendering, annotation, or form handling.

## TL;DR — when to switch

| You need… | Use |
| --- | --- |
| Plain-text extraction (`page.get_text("text")`) | flashpdf (~3–10x faster) |
| Structured blocks dict (`page.get_text("dict")`) | flashpdf |
| Image extraction (`page.get_images`) | flashpdf |
| Outline / TOC (`doc.get_toc`) | flashpdf |
| Bulk extraction over 100+ files | flashpdf (`extract_many`) |
| Render page to pixmap (`page.get_pixmap`) | stay on fitz |
| Annotations / forms / widgets | stay on fitz |
| Editing PDFs (write/merge/split) | stay on fitz |

## Import swap

```python
# Before
import fitz

# After
import flashpdf as fitz  # alias keeps most call sites unchanged
```

Or, more explicitly:

```python
import flashpdf

with flashpdf.open("paper.pdf") as doc:
    page = doc[0]
    text = page.get_text("text")
```

## API compatibility table

| fitz | flashpdf | Notes |
| --- | --- | --- |
| `fitz.open(path)` | `flashpdf.open(path)` | Same context-manager protocol |
| `len(doc)` / `doc.page_count` | `len(doc)` / `doc.page_count` | Identical |
| `doc[i]` / `doc.load_page(i)` | `doc[i]` | Negative indices supported |
| `page.get_text("dict")` | `page.get_text("dict")` | Same nested structure (see below) |
| `page.get_text("text")` | `page.get_text("text")` | Identical |
| `page.get_text("blocks")` | `page.get_text("blocks")` | Identical tuple format |
| `page.get_images()` | `page.get_images()` | Returns image bytes + bbox |
| `page.rect` / `page.bbox` | `page.rect` / `page.bbox` | Identical MediaBox tuple |
| `page.number` | `page.number` | Identical |
| `doc.get_toc()` | `doc.get_toc()` | Same `[level, title, page]` format |
| `doc.metadata` | `doc.metadata` | Same keys, missing entries are `None` |
| `doc.is_encrypted` | `doc.is_encrypted` | See encryption notes below |
| — | `doc.is_linearized` | flashpdf-only convenience |
| `doc.close()` | `doc.close()` | No-op in flashpdf (mmap released at `open()`) |
| `page.get_pixmap()` | — | **Not implemented** |
| `page.add_highlight_annot()` | — | **Not implemented** |

## `get_text("dict")` field differences

The top-level shape is identical:

```python
{"blocks": [ {type: 0, ...}, {type: 1, ...} ]}
```

Within span dicts, both libraries populate `bbox`, `text`, `font`,
`size`, `color`. Differences:

| Field | fitz | flashpdf |
| --- | --- | --- |
| `flags` | bitmask: superscript/italic/serif/monospaced | **always `0`** (stub) |
| `ascender` / `descender` | float | not present |
| `block_no`, `line_no` | sequential indices | present in `"blocks"` mode only |

If your code does `span["flags"] & 2` to detect italic, the result will
silently be `False`. If you need font-style detection today, stay on
fitz for that workflow.

## Encryption

flashpdf transparently decrypts PDFs encrypted with the **standard
security handler** using RC4 (V1/V2) or AES-128 (V4) with the **empty
user password** — this is the dominant case for "encrypted but
readable" PDFs (browser exports, scanned PDFs with permission locks,
etc.).

Unsupported cases (returned as a clear error from `open()`):

- AES-256 (V5/R6) — detected and reported, not silently failed
- Non-`/Standard` handlers (`/Azure`, `/PublicKey`, etc.)
- Non-empty user passwords

fitz supports AES-256 and password input via `doc.authenticate(password)`.
If your workflow needs those, stay on fitz.

## Bulk extraction

For pipelines that process hundreds of PDFs, prefer `extract_many`
over repeated `open()` calls — it parallelizes across files:

```python
# Before
for path in pdf_paths:
    doc = fitz.open(path)
    ...

# After — 2-4x faster on multi-core machines
for path, result in flashpdf.extract_many(pdf_paths):
    for page in result.pages:
        ...
```

## Linearized PDFs

flashpdf detects and reports linearization via `doc.is_linearized`
but does not use the linearization hints for streaming first-page
extraction — it parses the full file. For web-display use cases where
byte-range requests matter, stay on fitz.

## Performance expectations

On the PyMuPDF bug-regression corpus (~165 PDFs) and the arXiv paper
corpus, flashpdf typically matches fitz on text-extraction accuracy
(95%+ character-level agreement) and is ~3x faster on average for
text-heavy PDFs, ~10x faster on PDFs with many small objects (Word
exports, Office-generated files).

If you see extraction mismatches, please include the PDF in a bug
report — accuracy gaps are usually font-specific and easy to fix once
we can reproduce.

## Unimplemented features and workarounds

| Feature | Workaround |
| --- | --- |
| `page.get_pixmap()` | Render with fitz/pdf2image, extract text with flashpdf |
| Annotations | Use fitz or pikepdf |
| Form filling | Use pikepdf |
| Merging / splitting | Use pypdf or pikepdf |

## Cheat sheet — common one-liners

```python
# all text from a PDF
text = "\n".join(doc[i].get_text("text") for i in range(len(doc)))

# first page as structured dict
d = doc[0].get_text("dict")

# image bytes from each page
for img in page.get_images():
    with open(f"img-{img['number']}.{img['ext']}", "wb") as f:
        f.write(img["image"])

# outline
for level, title, page in doc.get_toc():
    print("  " * level, page, title)
```
