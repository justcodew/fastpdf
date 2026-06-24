"""Generate docs/demo.html: side-by-side visual of original PDF page
versus flashpdf's extracted text output.

Uses fitz ONLY to render the PDF page to a PNG (for the left panel).
The right panel is 100% flashpdf output.
"""
import base64
import html
from pathlib import Path

import fitz
import flashpdf

ROOT = Path(__file__).parent.parent
PDF = ROOT / "test_data" / "2604.11578v1.pdf"
OUT = ROOT / "docs" / "demo.html"
PAGE_IDX = 0  # first page: title + abstract + two-column body
DPI = 150


def page_to_png_b64(pdf_path: Path, page_idx: int, dpi: int = DPI) -> str:
    doc = fitz.open(str(pdf_path))
    page = doc[page_idx]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return base64.b64encode(pix.tobytes("png")).decode("ascii")


def render_right_panel(page: "flashpdf.Page") -> str:
    """Format flashpdf's get_text('dict') output as HTML.

    Color-codes blocks visually to match what the user would see in the PDF.
    """
    d = page.get_text("dict")
    parts = [
        "<div class='fp-output'>",
        f"<div class='fp-meta'>page {page.number} · "
        f"rect={[round(x, 1) for x in page.rect]} · "
        f"is_scanned={page.is_scanned} · "
        f"{len(d['blocks'])} blocks</div>",
    ]
    palette = ["#e8f4f8", "#fff4e6", "#f0f8e8", "#fae8f4", "#e8e8ff", "#fff8e0"]
    for i, block in enumerate(d["blocks"]):
        bg = palette[i % len(palette)]
        bbox = [round(x, 1) for x in block["bbox"]]
        if block.get("type") == 1:
            # image block
            parts.append(
                f"<div class='fp-block fp-img' style='background:{bg}'>"
                f"<span class='fp-label'>IMAGE BLOCK #{i} · bbox={bbox} · "
                f"{block.get('width','?')}×{block.get('height','?')}</span>"
                "</div>"
            )
            continue
        # text block
        parts.append(
            f"<div class='fp-block' style='background:{bg}'>"
            f"<span class='fp-label'>TEXT BLOCK #{i} · bbox={bbox}</span>"
        )
        for line in block.get("lines", []):
            line_text = "".join(s["text"] for s in line.get("spans", []))
            if not line_text.strip():
                continue
            font_sizes = [round(s["size"], 1) for s in line.get("spans", [])]
            parts.append(
                f"<div class='fp-line'>"
                f"<span class='fp-line-meta'>{font_sizes}</span>"
                f"<span class='fp-line-text'>{html.escape(line_text)}</span>"
                "</div>"
            )
        parts.append("</div>")
    parts.append("</div>")
    return "".join(parts)


CSS = """
* { box-sizing: border-box; }
body {
  margin: 0; padding: 24px; font-family: -apple-system, "Helvetica Neue", sans-serif;
  background: #fafafa; color: #222;
}
h1 { font-size: 20px; margin: 0 0 4px 0; }
.subtitle { color: #666; font-size: 13px; margin-bottom: 20px; }
.split {
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
  align-items: start;
}
.panel {
  background: white; border: 1px solid #ddd; border-radius: 6px;
  padding: 12px; overflow: auto; max-height: 90vh;
}
.panel h2 {
  font-size: 13px; margin: 0 0 10px 0; color: #888;
  text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;
}
.panel img { width: 100%; height: auto; display: block; border: 1px solid #eee; }
.fp-meta {
  font-size: 11px; color: #888; padding: 4px 8px; margin-bottom: 8px;
  background: #f4f4f4; border-radius: 3px;
}
.fp-block {
  padding: 6px 8px; margin-bottom: 6px; border-radius: 3px;
  border-left: 3px solid #999;
}
.fp-img { font-style: italic; color: #555; }
.fp-label {
  font-size: 10px; color: #777; display: block; margin-bottom: 4px;
  font-family: monospace;
}
.fp-line {
  font-size: 12px; line-height: 1.5; padding: 1px 0;
  display: flex; align-items: baseline;
}
.fp-line-meta {
  font-size: 9px; color: #aaa; font-family: monospace;
  min-width: 60px; flex-shrink: 0; margin-right: 8px;
}
.fp-line-text { flex: 1; }
.footer {
  margin-top: 20px; padding-top: 16px; border-top: 1px solid #eee;
  font-size: 11px; color: #888;
}
code { background: #eee; padding: 1px 5px; border-radius: 2px; font-size: 12px; }
"""


def main():
    print(f"Rendering page {PAGE_IDX} of {PDF.name} at {DPI} DPI...")
    img_b64 = page_to_png_b64(PDF, PAGE_IDX, DPI)
    print(f"  image: {len(img_b64) // 1024} KB base64")

    doc = flashpdf.open(str(PDF), include_images=True)
    page = doc[PAGE_IDX]
    right_html = render_right_panel(page)
    print(f"  flashpdf: {len(page.get_text('dict')['blocks'])} blocks extracted")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>flashpdf 提取效果演示</title>
<style>{CSS}</style>
</head>
<body>
<h1>flashpdf 提取效果演示</h1>
<div class="subtitle">
  样例：<code>{PDF.name}</code> 第 {PAGE_IDX + 1} 页 ·
  左侧 = fitz 渲染的原始 PDF · 右侧 = flashpdf 输出（block/line 结构）
</div>
<div class="split">
  <div class="panel">
    <h2>原始 PDF 渲染（参考）</h2>
    <img src="data:image/png;base64,{img_b64}" alt="PDF page {PAGE_IDX}" />
  </div>
  <div class="panel">
    <h2>flashpdf 输出（get_text "dict"）</h2>
    {right_html}
  </div>
</div>
<div class="footer">
  生成脚本：<code>tests/gen_demo.py</code> ·
  左图仅用 fitz 渲染 PDF 像素；右侧文本 100% 来自 flashpdf 提取。
</div>
</body>
</html>
"""
    OUT.write_text(html_doc, encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
