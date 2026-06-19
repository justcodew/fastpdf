# flashpdf API 文档

## Python API

### `flashpdf.extract(path, page_parallel=True, include_images=True, gpu=False, batch_size=50)`

从单个 PDF 文件提取文本块和图像。

**参数：**

- `path` (str): PDF 文件路径
- `page_parallel` (bool): 启用页级并行处理。多页 PDF 在多核 CPU 上可获得 2-4x 加速。默认 `True`
- `include_images` (bool): 是否提取图像的原始字节。关闭可显著降低内存占用。默认 `True`
- `gpu` (bool): 启用 GPU 加速图像处理（需要 NVIDIA GPU + CUDA）。默认 `False`
- `batch_size` (int): 大文档分批处理的页数。超过此数量的 PDF 将分批处理以控制内存。设为 0 禁用分批。默认 `50`

**返回：** `tuple(blocks, images)`

**示例：**

```python
import flashpdf

# 基本用法
blocks, images = flashpdf.extract("report.pdf")

# 仅提取文本（更快，更省内存）
blocks, _ = flashpdf.extract("report.pdf", include_images=False)

# 大文档优化
blocks, images = flashpdf.extract("huge.pdf", batch_size=100)
```

---

### `flashpdf.extract_many(paths, file_parallel=True, page_parallel=False, include_images=False, gpu=False, batch_size=50)`

批量提取多个 PDF 文件。支持文件级并行和异步预读。

**参数：**

- `paths` (list[str]): PDF 文件路径列表
- `file_parallel` (bool): 文件级并行处理。多个文件同时解析。默认 `True`
- `page_parallel` (bool): 页级并行。与 file_parallel 同时启用时可能过度并行，建议二选一。默认 `False`
- `include_images` (bool): 是否提取图像。批量场景建议关闭。默认 `False`
- `gpu` (bool): GPU 加速。默认 `False`
- `batch_size` (int): 分批大小。默认 `50`

**返回：** `list[tuple(path, blocks, images)]`

**示例：**

```python
import flashpdf
import glob

paths = glob.glob("pdfs/*.pdf")

# 文件级并行，仅提取文本
for path, blocks, images in flashpdf.extract_many(paths, include_images=False):
    text = " ".join(
        span["text"]
        for b in blocks
        for l in b["lines"]
        for span in l["spans"]
    )
    print(f"{path}: {len(text)} chars")
```

---

## 输出格式

### Block (文本块)

```python
{
    "type": 0,                          # 块类型 (0=文本)
    "bbox": (x0, y0, x1, y1),          # 页面坐标系下的边界框
    "lines": [...]                      # 行列表
}
```

### Line (文本行)

```python
{
    "bbox": (x0, y0, x1, y1),          # 行边界框
    "spans": [...]                      # Span 列表
}
```

### Span (文本段)

同一字体/字号/颜色的连续字符。

```python
{
    "bbox": (x0, y0, x1, y1),          # 段边界框
    "text": "Hello World",              # 文本内容
    "font": "Helvetica",                # 字体名称
    "size": 12.0,                       # 字号 (pt)
    "color": 0,                         # 颜色 (RGB packed)
}
```

### Image (图像)

```python
{
    "bbox": (x0, y0, x1, y1),          # 页面中的位置
    "width": 1920,                      # 像素宽度
    "height": 1080,                     # 像素高度
    "bpc": 8,                           # 每通道位数
    "colorspace": "DeviceRGB",          # 色彩空间
    "xref": 42,                         # PDF 对象编号
    "ext": "jpeg",                      # 格式: jpeg / png / jpx
    "image": b"\xff\xd8\xff...",         # 原始字节 (None 如果 include_images=False)
}
```

---

## Rust API

### `flashpdf_core::extract(path, options) -> Result<ExtractResult>`

```rust
use flashpdf_core::{extract, ExtractOptions};

let options = ExtractOptions::default();
let result = extract("document.pdf", &options)?;

for page in &result.pages {
    for block in &page.blocks {
        println!("Block: {:?}", block.bbox);
        for line in &block.lines {
            for span in &line.spans {
                println!("  [{} {:.0}pt] {}", span.font, span.size, span.text);
            }
        }
    }
    for img in &page.images {
        println!("Image: {}x{} {}", img.width, img.height, img.ext);
    }
}
```

### `flashpdf_core::extract_many(paths, options) -> Vec<(String, Result<ExtractResult>)>`

```rust
use flashpdf_core::{extract_many, ExtractOptions};

let paths = vec!["a.pdf", "b.pdf", "c.pdf"];
let options = ExtractOptions {
    file_parallel: true,
    include_images: false,
    ..Default::default()
};

for (path, result) in extract_many(&paths, &options) {
    match result {
        Ok(r) => println!("{}: {} pages", path, r.pages.len()),
        Err(e) => println!("{}: error {}", path, e),
    }
}
```

### `ExtractOptions`

```rust
pub struct ExtractOptions {
    pub page_parallel: bool,    // 页级并行 (默认 true)
    pub file_parallel: bool,    // 文件级并行 (默认 true)
    pub include_images: bool,   // 提取图像 (默认 true)
    pub gpu: bool,              // GPU 加速 (默认 false)
    pub batch_size: usize,      // 分批大小 (默认 50, 0=不分批)
}
```

### `Document`

底层文档对象，支持直接操作：

```rust
use flashpdf_core::Document;

let doc = Document::open("document.pdf")?;

// 获取页数
let count = doc.page_count()?;

// 获取页面引用
let pages = doc.page_refs()?;

// 获取任意对象
let obj = doc.get_object(42)?;

// 获取根目录
let root = doc.root()?;
```

---

## 字体处理

### 解码链路

```
字符代码
  │
  ├─ 1. ToUnicode CMap 查找
  │     └─ bfchar 直接映射 / bfrange 范围映射
  │
  ├─ 2. Encoding Differences
  │     └─ /Differences 数组中的 Adobe Glyph Name
  │
  ├─ 3. 原始字节
  │     └─ ASCII (0x20-0x7E) / Latin-1 (0x80+)
  │
  └─ 4. U+FFFD (无法解码)
```

### Type0 复合字体

自动处理：
- `/DescendantFonts` → CIDFont 解析
- `/W` 数组 (范围 + 数组两种格式)
- `/DW` 默认宽度
- `/CIDToGIDMap` (CIDFontType2)
- 2 字节 CID 代码自动识别

### 支持的编码

- 标准编码：WinAnsiEncoding, MacRomanEncoding, MacExpertEncoding
- Differences 表
- ToUnicode CMap (bfchar + bfrange)
- Adobe Glyph List (200+ 常用字形)
- Unicode escape: `uniXXXX` 格式

---

## 图像提取

### 零拷贝路径

JPEG 和 JPX 图像直接返回 mmap 切片，无解码/再编码：

```
PDF mmap → 流偏移/长度 → 直接返回字节切片
```

### 惰性 PNG

FlateDecode 图像延迟编码为 PNG：

```
PDF mmap → FlateDecode 解压 → 惰性 PNG 编码
```

### 支持的格式

| Filter | 输出格式 | 处理方式 |
|--------|----------|----------|
| DCTDecode | jpeg | 零拷贝 |
| JPXDecode | jpx | 零拷贝 |
| FlateDecode | png | 解压 + PNG 编码 |
| LZWDecode | png | 解压 + PNG 编码 |
| CCITTFaxDecode | png | 解压 + PNG 编码 |

---

## 并行策略

### 页级并行 (rayon)

```
PDF → 页面列表 → rayon par_iter → 每页独立提取 → 合并结果
```

适用于多页 PDF，加速比接近核心数。

### 文件级并行

```
[a.pdf, b.pdf, c.pdf] → rayon par_iter → 每个文件独立提取
```

适用于批量处理多个文件。

### 异步预读

顺序处理时，后台线程提前 mmap 下一个文件：

```
处理文件 A → 同时 mmap 文件 B → 处理文件 B → 同时 mmap 文件 C → ...
```

### 大文档分批

页数 > batch_size 时自动分批：

```
100 页 PDF, batch_size=50 → 批次 1 (1-50 页) → 批次 2 (51-100 页)
```

每批独立并行，控制内存峰值。
