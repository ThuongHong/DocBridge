from __future__ import annotations

import os
import re
import shutil
from itertools import pairwise
from pathlib import Path
from statistics import median

from .config import resource_root
from .models import Block, Document, file_hash


def configure_tesseract():
    import pytesseract

    bundled = resource_root() / "assets/tesseract"
    explicit = os.environ.get("CONVERTER_TESSERACT")
    executable = Path(explicit) if explicit else bundled / "tesseract.exe"
    if executable.exists():
        pytesseract.pytesseract.tesseract_cmd = str(executable)
    elif shutil.which("tesseract"):
        pytesseract.pytesseract.tesseract_cmd = shutil.which("tesseract")
    else:
        raise ValueError("Không tìm thấy Tesseract. Cần bộ OCR đi kèm để đọc PDF scan.")
    tessdata = bundled / "tessdata"
    return f'--tessdata-dir "{tessdata}"' if tessdata.exists() else ""


def render_page(source: Path, page_index: int, scale: float = 2.0):
    import pypdfium2 as pdfium

    with pdfium.PdfDocument(source) as pdf:
        page = pdf[page_index]
        try:
            bitmap = page.render(scale=scale)
            try:
                return bitmap.to_pil().copy()
            finally:
                bitmap.close()
        finally:
            page.close()


def ocr_image(image, language: str, config: str) -> list[dict]:
    import pytesseract

    installed = set(pytesseract.get_languages(config=config))
    missing = set(language.split("+")) - installed
    if missing:
        raise ValueError("Thiếu OCR language packs: " + ", ".join(sorted(missing)))
    data = pytesseract.image_to_data(
        image, lang=language, config=config + " --psm 3", output_type=pytesseract.Output.DICT
    )
    grouped = {}
    for index, text in enumerate(data["text"]):
        if not text.strip():
            continue
        key = tuple(data[name][index] for name in ["block_num", "par_num", "line_num"])
        grouped.setdefault(key, []).append(index)
    result = []
    for indices in grouped.values():
        left = min(data["left"][i] for i in indices)
        top = min(data["top"][i] for i in indices)
        right = max(data["left"][i] + data["width"][i] for i in indices)
        bottom = max(data["top"][i] + data["height"][i] for i in indices)
        result.append(
            {
                "text": join_words([data["text"][i] for i in indices]),
                "bbox": [left, top, right, bottom],
                "confidence": sum(float(data["conf"][i]) for i in indices) / len(indices),
            }
        )
    return result


def join_words(words: list[str]) -> str:
    result = ""
    han = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
    for word in words:
        if result and word and not (han.fullmatch(result[-1]) and han.fullmatch(word[0])):
            result += " "
        result += word
    return result


def read_pdf(
    source: Path, assets_dir: Path, language="chi_sim+chi_tra+eng", progress=None, control=None
) -> Document:
    import pdfplumber

    doc = Document(str(source), file_hash(source), "pdf")
    assets_dir.mkdir(parents=True, exist_ok=True)
    doc.warnings.append("PDF → DOCX dựng lại nội dung; bố cục/font/số trang có thể khác bản gốc.")
    config = None
    with pdfplumber.open(source) as pdf:
        if getattr(pdf.doc, "encryption", None):
            raise ValueError("Chưa hỗ trợ PDF được mã hóa.")
        for number, page in enumerate(pdf.pages):
            if control:
                control()
            if progress:
                progress(f"Đọc PDF: trang {number + 1}/{len(pdf.pages)}")
            section = Block("section", meta={"title": f"Page {number + 1}", "page": number})
            words = page.extract_words(extra_attrs=["size", "fontname"])
            baseline = (
                median([float(char.get("size", 12)) for char in page.chars]) if page.chars else 12
            )
            ordered: list[tuple[float, float, Block]] = []
            tables = page.find_tables() if words else []
            for table in tables:
                block = Block("table")
                for row_index, row in enumerate(table.extract()):
                    rb = Block("row")
                    for column, text in enumerate(row):
                        cell = Block("cell")
                        if text:
                            segment = doc.add_segment(
                                text,
                                {
                                    "page": number,
                                    "bbox": list(table.bbox),
                                    "row": row_index,
                                    "column": column,
                                },
                                context=text,
                            )
                            cell.segments.append(segment.id)
                        rb.children.append(cell)
                    block.children.append(rb)
                ordered.append((table.bbox[1], table.bbox[0], block))

            if words:
                # Use layout-aware lines outside table regions; avoid translating tables twice.
                normal = [
                    word
                    for word in words
                    if not any(
                        table.bbox[0] <= (word["x0"] + word["x1"]) / 2 <= table.bbox[2]
                        and table.bbox[1] <= (word["top"] + word["bottom"]) / 2 <= table.bbox[3]
                        for table in tables
                    )
                ]
                lines = []
                for word in sorted(normal, key=lambda item: (round(item["top"] / 3), item["x0"])):
                    if (
                        lines
                        and abs(lines[-1][0]["top"] - word["top"]) < 3
                        and word["x0"] - lines[-1][-1]["x1"] < 30
                    ):
                        lines[-1].append(word)
                    else:
                        lines.append([word])
                for line in lines:
                    text = join_words([word["text"] for word in line])
                    bbox = [
                        min(w["x0"] for w in line),
                        min(w["top"] for w in line),
                        max(w["x1"] for w in line),
                        max(w["bottom"] for w in line),
                    ]
                    segment = doc.add_segment(text, {"page": number, "bbox": bbox}, context=text)
                    size = max(float(word.get("size", baseline)) for word in line)
                    heading = size >= baseline * 1.2 and len(text) <= 200
                    ordered.append(
                        (
                            bbox[1],
                            bbox[0],
                            Block(
                                "heading" if heading else "paragraph",
                                [segment.id],
                                meta={"level": 1 if size >= baseline * 1.5 else 2}
                                if heading
                                else {},
                            ),
                        )
                    )
            else:
                if config is None:
                    config = configure_tesseract()
                image = render_page(source, number, scale=3)
                recognized = ocr_image(image, language, config)
                if not recognized:
                    doc.warnings.append(
                        f"Trang {number + 1}: OCR không nhận được text; cần review trang nguồn."
                    )
                for item in recognized:
                    bbox = [value / 3 for value in item["bbox"]]
                    segment = doc.add_segment(
                        item["text"], {"page": number, "bbox": bbox}, context=item["text"]
                    )
                    if item["confidence"] < 65:
                        segment.warning = (
                            f"OCR confidence {item['confidence']:.0f}%: kiểm tra text nguồn."
                        )
                    ordered.append((bbox[1], bbox[0], Block("paragraph", [segment.id])))
                doc.warnings.append(f"Trang {number + 1}: dùng OCR; bảng và thứ tự đọc cần review.")
            # Keep embedded images; do not duplicate a scanned full-page image alongside its OCR.
            bitmap = None
            for index, item in enumerate(page.images):
                area = (item["x1"] - item["x0"]) * (item["bottom"] - item["top"])
                if not words and area > page.width * page.height * 0.8:
                    continue
                if bitmap is None:
                    bitmap = render_page(source, number, scale=2)
                bounds = [
                    max(0, item["x0"]),
                    max(0, item["top"]),
                    min(page.width, item["x1"]),
                    min(page.height, item["bottom"]),
                ]
                if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                    continue
                asset = f"page-{number + 1}-image-{index}.png"
                path = assets_dir / asset
                bitmap.crop(tuple(int(value * 2) for value in bounds)).save(path)
                doc.assets[asset] = str(path)
                ordered.append((bounds[1], bounds[0], Block("image", meta={"asset": asset})))
                # Text inside a raster image on a text-bearing PDF needs its own OCR pass.
                if words and area > 400:
                    if config is None:
                        config = configure_tesseract()
                    crop = bitmap.crop(tuple(int(value * 2) for value in bounds))
                    for item in ocr_image(crop, language, config):
                        bbox = [
                            bounds[0] + item["bbox"][0] / 2,
                            bounds[1] + item["bbox"][1] / 2,
                            bounds[0] + item["bbox"][2] / 2,
                            bounds[1] + item["bbox"][3] / 2,
                        ]
                        # Some PDFs embed the same image beneath an existing OCR text layer.
                        if any(
                            bbox[0] <= (w["x0"] + w["x1"]) / 2 <= bbox[2]
                            and bbox[1] <= (w["top"] + w["bottom"]) / 2 <= bbox[3]
                            for w in words
                        ):
                            continue
                        segment = doc.add_segment(
                            item["text"], {"page": number, "bbox": bbox}, context=item["text"]
                        )
                        segment.warning = "Text từ ảnh: kiểm tra OCR; ảnh gốc vẫn giữ nguyên."
                        ordered.append((bbox[1], bbox[0], Block("paragraph", [segment.id])))
            if bitmap:
                bitmap.close()
            ordered = reading_order(ordered, doc, page.width)
            section.children = [item[2] for item in ordered]
            if len(lines if words else []) > 3 and any(
                abs(a[0]["top"] - b[0]["top"]) < 3 and b[0]["x0"] - a[-1]["x1"] >= 30
                for a, b in pairwise(lines)
            ):
                doc.warnings.append(
                    f"Trang {number + 1}: có nhiều cột; kiểm tra thứ tự đọc trong Review."
                )
            doc.blocks.append(section)
            page.close()
    doc.warnings = list(dict.fromkeys(doc.warnings))
    return doc


def reading_order(items: list, doc: Document, page_width: float) -> list:
    """Read ordinary two-column bands left-to-right, bounded by full-width blocks."""
    items = sorted(items, key=lambda item: (item[0], item[1]))
    lookup = doc.by_id()
    midpoint = page_width / 2

    def bounds(item):
        block = item[2]
        if block.segments:
            return lookup[block.segments[0]].anchor.get("bbox", [0, item[0], page_width, item[0]])
        return [0, item[0], page_width, item[0]]

    left = [item for item in items if bounds(item)[2] < midpoint - 10]
    right = [item for item in items if bounds(item)[0] > midpoint + 10]
    if len(left) < 2 or len(right) < 2:
        return items
    result, band = [], []

    def flush():
        result.extend(sorted(band, key=lambda item: (bounds(item)[0] > midpoint, item[0])))
        band.clear()

    for item in items:
        bbox = bounds(item)
        if bbox[0] <= midpoint <= bbox[2]:
            flush()
            result.append(item)
        else:
            band.append(item)
    flush()
    return result


def write_pdf_docx(doc: Document, target: Path):
    from docx import Document as WordDocument
    from docx.shared import Inches

    if not doc.complete():
        raise ValueError("Còn đoạn chưa dịch.")
    segments = doc.by_id()
    output = WordDocument()

    def text(block):
        return "".join(segments[sid].text for sid in block.segments) or block.meta.get(
            "literal", ""
        )

    def render(block, container):
        if block.kind == "section":
            container.add_heading(block.meta.get("title", ""), level=2)
            for child in block.children:
                render(child, container)
        elif block.kind == "table":
            width = max((len(row.children) for row in block.children), default=0)
            if width:
                table = container.add_table(rows=len(block.children), cols=width)
                table.style = "Table Grid"
                for i, row in enumerate(block.children):
                    for j, cell in enumerate(row.children):
                        table.cell(i, j).text = text(cell)
        elif block.kind == "image":
            path = doc.assets.get(block.meta.get("asset"))
            if path:
                container.add_picture(path, width=Inches(6))
        elif block.kind == "heading":
            container.add_heading(text(block), level=block.meta.get("level", 1))
        else:
            container.add_paragraph(text(block))

    for block in doc.blocks:
        render(block, output)
    output.save(target)
