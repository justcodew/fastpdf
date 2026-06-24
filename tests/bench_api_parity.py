"""API parity benchmark: flashpdf extract() vs open() vs fitz.

Verifies:
1. flashpdf's new open() API produces identical char counts to the old extract()
   (regression check — should be exactly equal since both go through the same core)
2. Speed hasn't regressed in the new API path
3. Accuracy vs fitz is unchanged from the historical 95%+ char_sim
"""
import statistics
import time

import fitz
import flashpdf

PDFS = [
    ("/Users/xiongzhaolong/Downloads/claude-pro/202604-job/pdf_pro/dbnet_plus.pdf", "dbnet_plus"),
    ("/Users/xiongzhaolong/Downloads/claude-pro/202604-job/pdf_pro/flashpdf/test_data/2604.11578v1.pdf", "arxiv_2604"),
]

ITERS = 20


def pctile(values, p):
    s = sorted(values)
    return s[int(round((p / 100.0) * (len(s) - 1)))]


def time_it(fn):
    t0 = time.perf_counter()
    out = fn()
    return (time.perf_counter() - t0) * 1000, out


def run(fn, iters=ITERS):
    fn()  # 1 warm-up
    samples = []
    result = None
    for _ in range(iters):
        ms, result = time_it(fn)
        samples.append(ms)
    return statistics.mean(samples), pctile(samples, 99), result


# --- adapters ----------------------------------------------------------

def fp_extract_chars(path):
    def go():
        blocks, _ = flashpdf.extract(path, include_images=False, page_parallel=True)
        return sum(len(s["text"]) for b in blocks for l in b["lines"] for s in l["spans"])
    return go


def fp_open_chars(path):
    def go():
        doc = flashpdf.open(path)
        n = 0
        for i in range(len(doc)):
            d = doc[i].get_text("dict")
            for b in d["blocks"]:
                if b["type"] == 0:
                    for l in b["lines"]:
                        for s in l["spans"]:
                            n += len(s["text"])
        return n
    return go


def fp_open_no_images_chars(path):
    """Apples-to-apples vs extract(include_images=False)."""
    def go():
        doc = flashpdf.open(path, include_images=False)
        n = 0
        for i in range(len(doc)):
            d = doc[i].get_text("dict")
            for b in d["blocks"]:
                if b["type"] == 0:
                    for l in b["lines"]:
                        for s in l["spans"]:
                            n += len(s["text"])
        return n
    return go


def fp_open_paged_chars(path):
    # Iterate via doc[i] like a fitz user would
    def go():
        doc = flashpdf.open(path)
        n = 0
        for page in iter_pages(doc):
            d = page.get_text("dict")
            for b in d["blocks"]:
                if b["type"] == 0:
                    for l in b["lines"]:
                        for s in l["spans"]:
                            n += len(s["text"])
        return n
    return go


def iter_pages(doc):
    for i in range(len(doc)):
        yield doc[i]


def fitz_open_chars(path):
    def go():
        doc = fitz.open(path)
        n = 0
        for page in doc:
            d = page.get_text("dict")
            for b in d["blocks"]:
                if b["type"] == 0:
                    for l in b["lines"]:
                        for s in l["spans"]:
                            n += len(s["text"])
        return n
    return go


# --- SequenceMatcher char_sim (order-sensitive) -----------------------

def fp_extract_text(path):
    """Concatenated text in reading order, extract() API."""
    def go():
        blocks, _ = flashpdf.extract(path, include_images=False, page_parallel=True)
        out = []
        for b in blocks:
            for l in b["lines"]:
                for s in l["spans"]:
                    out.append(s["text"])
            out.append("\n")
        return "".join(out)
    return go


def fp_open_text(path):
    """Concatenated text, open() API."""
    def go():
        doc = flashpdf.open(path, include_images=False)
        out = []
        for i in range(len(doc)):
            d = doc[i].get_text("dict")
            for b in d["blocks"]:
                if b["type"] == 0:
                    for l in b["lines"]:
                        for s in l["spans"]:
                            out.append(s["text"])
                out.append("\n")
        return "".join(out)
    return go


def fitz_text(path):
    def go():
        doc = fitz.open(path)
        out = []
        for page in doc:
            d = page.get_text("dict")
            for b in d["blocks"]:
                if b["type"] == 0:
                    for l in b["lines"]:
                        for s in l["spans"]:
                            out.append(s["text"])
                out.append("\n")
        return "".join(out)
    return go


def char_sim(a, b):
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def main():
    print(f"Iters: {ITERS} per scenario (1 warm-up)\n")

    header = f"{'PDF':<14} {'API':<26} {'Mean':>10} {'p99':>10} {'Chars':>10} {'char_sim':>10}"
    print(header)
    print("-" * len(header))

    for path, label in PDFS:
        # Get reference text (fitz) once for char_sim baseline
        _, _, fitz_text_ref = run(fitz_text(path), iters=1)
        _, _, fitz_chars_ref = run(fitz_open_chars(path), iters=1)

        scenarios = [
            ("flashpdf extract() MT",   fp_extract_chars(path), fp_extract_text(path)),
            ("flashpdf open() no-img",  fp_open_no_images_chars(path), fp_open_text(path)),
            ("flashpdf open() +img",    fp_open_chars(path), fp_open_text(path)),
            ("fitz open()",             fitz_open_chars(path), fitz_text(path)),
        ]

        for name, char_fn, text_fn in scenarios:
            mean, p99, chars = run(char_fn)
            _, _, txt = run(text_fn, iters=1)
            sim = char_sim(txt, fitz_text_ref) if "fitz" not in name else 1.0
            print(f"{label:<14} {name:<26} {mean:>8.2f}ms {p99:>8.2f}ms {chars:>10} {sim:>9.2%}")
        print()

    # Equality assertion: extract() vs open() should produce identical chars
    print("=== Regression check: extract() vs open() char parity ===")
    for path, label in PDFS:
        _, _, c1 = run(fp_extract_chars(path), iters=1)
        _, _, c2 = run(fp_open_chars(path), iters=1)
        match = "OK" if c1 == c2 else "MISMATCH"
        print(f"  {label}: extract={c1}  open={c2}  [{match}]")


if __name__ == "__main__":
    main()
