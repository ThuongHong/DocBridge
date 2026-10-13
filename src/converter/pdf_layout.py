"""Geometry and typography shared by PDF extraction and reconstruction."""
from __future__ import annotations

import re
from collections import Counter

from .models import Block, Document


def column_bands(blocks: list[Block], doc: Document, page_width: float) -> list[Block]:
    """Represent unambiguous two-column bands without changing stored reading order."""
    midpoint = page_width / 2
    lookup = doc.by_id()
    result, band = [], []

    def flush():
        if not band:
            return
        left = [b for b in band if b.meta["bbox"][2] < midpoint - 10]
        right = [b for b in band if b.meta["bbox"][0] > midpoint + 10]

        def bounds(items):
            boxes = [b.meta["bbox"] for b in items]
            return [min(b[0] for b in boxes), min(b[1] for b in boxes),
                    max(b[2] for b in boxes), max(b[3] for b in boxes)]

        def lines(items):
            return sum(max(1, sum(len(lookup[sid].anchor.get("line_bboxes", [0]))
                                  for sid in b.segments)) for b in items)

        if left and right and len(left) + len(right) == len(band):
            a, b = bounds(left), bounds(right)
            if (lines(left) >= 2 and lines(right) >= 2 and b[0] - a[2] >= 18
                    and min(a[3], b[3]) > max(a[1], b[1])):
                result.append(Block("columns", children=[
                    Block("column", children=left, meta={"bbox": a}),
                    Block("column", children=right, meta={"bbox": b}),
                ], meta={"bbox": bounds(band)}))
                band.clear()
                return
        result.extend(band)
        band.clear()

    for block in blocks:
        bbox = block.meta.get("bbox")
        if (not bbox or block.kind not in {"paragraph", "heading", "image"}
                or bbox[0] <= midpoint <= bbox[2]):
            flush()
            result.append(block)
        else:
            band.append(block)
    flush()
    return result


def word_style(words: list[dict]) -> dict:
    if not words:
        return {}
    fonts = Counter()
    sizes = Counter()
    for word in words:
        weight = max(1, len(word["text"]))
        fonts[re.sub(r"^[A-Z]{6}\+", "", word.get("fontname", ""))] += weight
        sizes[round(float(word.get("size", 12)), 1)] += weight
    font = fonts.most_common(1)[0][0]
    style = {
        "font": font,
        "font_size": sizes.most_common(1)[0][0],
        "b": bool(re.search(r"bold|black|heavy", font, re.I)),
        "i": bool(re.search(r"italic|oblique", font, re.I)),
    }
    color = words[0].get("non_stroking_color")
    if isinstance(color, (list, tuple)) and len(color) == 3:
        style["color"] = "".join(f"{round(min(1, max(0, value)) * 255):02X}" for value in color)
    elif isinstance(color, (int, float)):
        gray = round(min(1, max(0, color)) * 255)
        style["color"] = f"{gray:02X}" * 3
    return style


def join_wrapped_lines(left: str, right: str) -> str:
    """Remove a physical line break without inserting spaces inside Chinese prose."""
    if not left or not right:
        return left + right
    cjk = r"[\u3400-\u9fff\uf900-\ufaff，。；：！？、（）《》“”‘’]"
    separator = "" if re.match(cjk, left[-1]) or re.match(cjk, right[0]) else " "
    return left.rstrip() + separator + right.lstrip()


def merge_paragraph_lines(items: list, doc: Document, page_width: float) -> list:
    """Merge only aligned, tightly spaced wraps within the same reading-order band."""
    lookup = doc.by_id()
    midpoint = page_width / 2
    paragraphs = [block.meta["bbox"] for _, _, block in items
                  if block.kind == "paragraph" and block.meta.get("bbox")]
    two_columns = (
        sum(bbox[2] < midpoint - 10 for bbox in paragraphs) >= 2
        and sum(bbox[0] > midpoint + 10 for bbox in paragraphs) >= 2
    )

    def column(bbox):
        if not two_columns:
            return "wide"
        return "right" if bbox[0] > midpoint + 10 else "left" if bbox[2] < midpoint - 10 else "wide"

    right_edges = {}
    for _, _, block in items:
        bbox = block.meta.get("bbox")
        if block.kind == "paragraph" and bbox:
            key = column(bbox)
            right_edges[key] = max(right_edges.get(key, 0), bbox[2])
    result, removed = [], set()
    for top, left, block in items:
        bbox = block.meta.get("bbox")
        previous = result[-1][2] if result else None
        if not (
            previous and previous.kind == block.kind == "paragraph"
            and len(previous.segments) == len(block.segments) == 1
            and bbox and previous.meta.get("bbox")
        ):
            result.append((top, left, block))
            continue
        first, second = lookup[previous.segments[0]], lookup[block.segments[0]]
        prev_bbox = previous.meta["bbox"]
        last_bbox = first.anchor.get("line_bboxes", [prev_bbox])[-1]
        size = float(first.style.get("font_size", 12))
        gap = bbox[1] - last_bbox[3]
        same_ocr_paragraph = (
            first.anchor.get("ocr_paragraph") == second.anchor.get("ocr_paragraph")
            if "ocr_paragraph" in first.anchor or "ocr_paragraph" in second.anchor else True
        )
        if (
            not same_ocr_paragraph or column(last_bbox) != column(bbox)
            or first.style != second.style
            or not (-1 <= gap <= size * 0.7)
            or not (-size * 2.2 <= bbox[0] - prev_bbox[0] <= size * 0.8)
            or last_bbox[2] < right_edges[column(last_bbox)] - size * 2
            or re.match(r"^(?:[•●◦▪]|\d+[.)]\s|[（(]\d+[)）])", second.source)
        ):
            result.append((top, left, block))
            continue
        first.source = join_wrapped_lines(first.source, second.source)
        first.context = first.source
        first.warning = "\n".join(dict.fromkeys(filter(None, [first.warning, second.warning])))
        first.anchor.setdefault("line_bboxes", [last_bbox]).append(bbox)
        union = [min(prev_bbox[0], bbox[0]), min(prev_bbox[1], bbox[1]),
                 max(prev_bbox[2], bbox[2]), max(prev_bbox[3], bbox[3])]
        first.anchor["bbox"] = union
        previous.meta["bbox"] = union
        previous.meta.setdefault("line_spacing", bbox[1] - last_bbox[1])
        removed.add(second.id)
    doc.segments = [segment for segment in doc.segments if segment.id not in removed]
    return result


def add_page_context(blocks: list, doc: Document):
    lookup = doc.by_id()

    def texts(block):
        return [lookup[sid].source for sid in block.segments] + [
            text for child in block.children for text in texts(child)
        ]

    for index, block in enumerate(blocks):
        own = texts(block)
        nearby = [text for neighbor in blocks[max(0, index - 1):index + 2] for text in texts(neighbor)]
        context = "\n".join(dict.fromkeys(own + nearby))[:2000]

        def assign(item, context=context):
            for sid in item.segments:
                lookup[sid].context = context
            for child in item.children:
                assign(child)

        assign(block)
