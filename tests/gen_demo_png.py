"""Render a side-by-side PNG: left = PDF page rendered, right = flashpdf text.

Output: docs/demo.png (referenced by README).
"""
import html
import io
from pathlib import Path

import fitz
import flashpdf
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent.parent
PDF = ROOT / "test_data" / "2604.11578v1.pdf"
OUT = ROOT / "docs" / "demo.png"
PAGE_IDX = 0
DPI = 150

# Layout constants (pixels at the chosen DPI scale)
SCALE = 2  # supersample for crisp text
LEFT_W = 900
RIGHT_W = 900
PADDING = 24
HEADER_H = 60
BLOCK_PAD = 8
LINE_H = 18
META_H = 28

PALETTE = [
    (232, 244, 248),
    (255, 244, 230),
    (240, 248, 232),
    (250, 232, 244),
    (232, 232, 255),
    (255, 248, 224),
]


def find_font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/SFNSMono.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_pdf_page(pdf_path: Path, page_idx: int, dpi: int = DPI) -> Image.Image:
    doc = fitz.open(str(pdf_path))
    page = doc[page_idx]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def draw_right_panel(page: "flashpdf.Page", width: int) -> Image.Image:
    d = page.get_text("dict")
    n_blocks = len(d["blocks"])

    # First pass: measure height
    height = META_H + PADDING * 2
    block_heights = []
    for block in d["blocks"]:
        if block.get("type") == 1:
            h = 28
        else:
            lines = block.get("lines", [])
            nonempty = [l for l in lines if "".join(s["text"] for s in l.get("spans", [])).strip()]
            h = 24 + len(nonempty) * LINE_H + BLOCK_PAD * 2
        block_heights.append(h)
        height += h + 8
    height = max(height, 1000)

    img = Image.new("RGB", (width, height), (250, 250, 250))
    draw = ImageDraw.Draw(img)

    f_meta = find_font(13)
    f_label = find_font(11)
    f_line_meta = find_font(10)
    f_line = find_font(13)

    # Meta header
    meta_text = (f"page {page.number}  ·  "
                 f"rect=({page.rect[0]:.0f},{page.rect[1]:.0f},{page.rect[2]:.0f},{page.rect[3]:.0f})  ·  "
                 f"is_scanned={page.is_scanned}  ·  {n_blocks} blocks")
    draw.rectangle([0, 0, width, META_H], fill=(240, 240, 240))
    draw.text((PADDING, 8), meta_text, fill=(80, 80, 80), font=f_meta)

    y = META_H + PADDING
    for i, block in enumerate(d["blocks"]):
        bg = PALETTE[i % len(PALETTE)]
        h = block_heights[i]
        x0, y0, x1, y1 = PADDING, y, width - PADDING, y + h
        draw.rectangle([x0, y0, x1, y1], fill=bg)
        draw.line([x0, y0, x0, y1], fill=(120, 120, 120), width=3)

        bbox = [round(v, 1) for v in block["bbox"]]
        if block.get("type") == 1:
            label = (f"IMAGE BLOCK #{i}  ·  bbox={bbox}  ·  "
                     f"{block.get('width','?')}×{block.get('height','?')}")
            draw.text((x0 + BLOCK_PAD, y0 + 6), label, fill=(90, 90, 90), font=f_label)
        else:
            label = f"TEXT BLOCK #{i}  ·  bbox={bbox}"
            draw.text((x0 + BLOCK_PAD, y0 + 6), label, fill=(90, 90, 90), font=f_label)
            ly = y0 + 24 + BLOCK_PAD
            for line in block.get("lines", []):
                line_text = "".join(s["text"] for s in line.get("spans", []))
                if not line_text.strip():
                    continue
                sizes = [round(s["size"], 1) for s in line.get("spans", [])]
                # Truncate long size lists
                size_str = str(sizes[:3])
                if len(sizes) > 3:
                    size_str = size_str[:-1] + f", ... +{len(sizes)-3}]"
                draw.text((x0 + BLOCK_PAD, ly), size_str, fill=(170, 170, 170), font=f_line_meta)
                draw.text((x0 + BLOCK_PAD + 80, ly), line_text, fill=(30, 30, 30), font=f_line)
                ly += LINE_H
        y += h + 8

    return img


def main():
    print(f"Rendering page {PAGE_IDX} of {PDF.name} at {DPI} DPI...")
    left_img = render_pdf_page(PDF, PAGE_IDX, DPI)
    print(f"  left panel: {left_img.size}")

    doc = flashpdf.open(str(PDF), include_images=True)
    page = doc[PAGE_IDX]
    right_img = draw_right_panel(page, RIGHT_W)
    print(f"  right panel: {right_img.size}")

    # Resize left to match right's width
    target_w = LEFT_W
    if left_img.width != target_w:
        ratio = target_w / left_img.width
        left_img = left_img.resize((target_w, int(left_img.height * ratio)), Image.LANCZOS)

    # Compose with header
    total_h = max(left_img.height, right_img.height) + HEADER_H + PADDING * 2
    total_w = LEFT_W + RIGHT_W + PADDING * 4
    canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    f_h1 = find_font(22, bold=True)
    f_h2 = find_font(13, bold=True)

    draw.text((PADDING, 18), "flashpdf 提取效果演示", fill=(20, 20, 20), font=f_h1)
    sub = f"样例: {PDF.name} 第 {PAGE_IDX+1} 页  ·  左 = fitz 渲染的原始 PDF  ·  右 = flashpdf 输出结构"
    draw.text((PADDING, 44), sub, fill=(120, 120, 120), font=f_h2)

    # Column headers
    col_y = HEADER_H + PADDING
    draw.text((PADDING, col_y), "原始 PDF 渲染（参考）", fill=(150, 150, 150), font=f_h2)
    draw.text((LEFT_W + PADDING * 3, col_y), "flashpdf get_text('dict')", fill=(150, 150, 150), font=f_h2)

    canvas.paste(left_img, (PADDING, col_y + 20))
    canvas.paste(right_img, (LEFT_W + PADDING * 3, col_y + 20))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT, format="PNG", optimize=True)
    print(f"\nWrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
