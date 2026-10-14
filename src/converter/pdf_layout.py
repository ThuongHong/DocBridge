"""Geometry and typography shared by PDF extraction and reconstruction."""
from __future__ import annotations

import re
from collections import Counter

from .models import Block, Document


def column_divider(blocks: list[Block], page_width: float) -> float | None:
    """Find a gutter supported by overlapping text on multiple physical rows."""
    boxes = sorted(
        (b.meta["bbox"] for b in blocks
         if b.kind in {"paragraph", "heading", "table"} and b.meta.get("bbox")
         and b.meta["bbox"][2] - b.meta["bbox"][0] >= page_width * .1),
        key=lambda box: box[1],
    )
    candidates = []
    for index, first in enumerate(boxes):
        for second in boxes[index + 1:]:
            if second[1] >= first[3]:
                break
            left, right = sorted((first, second), key=lambda box: box[0])
            gap = right[0] - left[2]
            center = (right[0] + left[2]) / 2
            overlap = min(left[3], right[3]) - max(left[1], right[1])
            if (8 <= gap <= page_width * .4
                    and page_width * .35 <= center <= page_width * .65
                    and overlap >= 3):
                candidates.append((left[2], right[0], max(left[1], right[1])))
                # Merged paragraphs can represent several physical rows.
                if overlap >= 24:
                    candidates.append((left[2], right[0], max(left[1], right[1]) + 12))
    if len({round(top / 3) for _, _, top in candidates}) < 2:
        return None
    # Indented text makes gap midpoints drift. Choose whitespace supported by
    # the most rows, rather than averaging into an actual text column.
    edges = sorted({edge for left, right, _ in candidates for edge in (left, right)})
    points = [(left + right) / 2 for left, right in zip(edges[:-1], edges[1:], strict=True)]
    points.append(page_width / 2)

    def support(point):
        return len({round(top / 3) for left, right, top in candidates if left < point < right})

    divider = max(points, key=lambda point: (support(point), -abs(point - page_width / 2)))
    return divider if support(divider) >= 2 else None


def column_bands(blocks: list[Block], doc: Document, page_width: float) -> list[Block]:
    """Represent unambiguous two-column bands without changing stored reading order."""
    midpoint = column_divider(blocks, page_width)
    if midpoint is None:
        return blocks
    lookup = doc.by_id()
    result, band = [], []

    def flush():
        if not band:
            return
        left = [b for b in band if b.meta["bbox"][2] < midpoint]
        right = [b for b in band if b.meta["bbox"][0] > midpoint]

        def bounds(items):
            boxes = [b.meta["bbox"] for b in items]
            return [min(b[0] for b in boxes), min(b[1] for b in boxes),
                    max(b[2] for b in boxes), max(b[3] for b in boxes)]

        def lines(items):
            return sum(max(1, sum(len(lookup[sid].anchor.get("line_bboxes", [0]))
                                  for sid in b.segments)) for b in items)

        if left and right and len(left) + len(right) == len(band):
            a, b = bounds(left), bounds(right)
            if (lines(left) >= 2 and lines(right) >= 2 and b[0] - a[2] >= 8
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
    midpoint = column_divider([block for _, _, block in items], page_width)
    two_columns = midpoint is not None

    def column(bbox):
        if not two_columns:
            return "wide"
        return "right" if bbox[0] > midpoint else "left" if bbox[2] < midpoint else "wide"

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
        hanging_list = bool(re.match(r"^(?:\d+[.)]\s|[（(]\d+[)）])", first.source))
        same_ocr_paragraph = (
            first.anchor.get("ocr_paragraph") == second.anchor.get("ocr_paragraph")
            if "ocr_paragraph" in first.anchor or "ocr_paragraph" in second.anchor else True
        )
        if (
            not same_ocr_paragraph or column(last_bbox) != column(bbox)
            or first.style != second.style
            or not (-1 <= gap <= size * 0.7)
            or not (-size * 2.2 <= bbox[0] - prev_bbox[0] <= size * (2.2 if hanging_list else .8))
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
        if block.meta.get("role") in {"page_header", "page_footer"}:
            return []
        return [lookup[sid].source for sid in block.segments] + [
            text for child in block.children for text in texts(child)
        ]

    for index, block in enumerate(blocks):
        own = texts(block)
        nearby = [text for neighbor in blocks[max(0, index - 1):index + 2]
                  if neighbor.meta.get("role") != "image_text" for text in texts(neighbor)]
        context = "\n".join(dict.fromkeys(own + nearby))[:2000]

        def assign(item, context=context):
            for sid in item.segments:
                lookup[sid].context = context
            for child in item.children:
                assign(child)

        assign(block)


def mark_page_furniture(doc: Document):
    """Label repeated margin text, retaining its segments and source anchors."""
    lookup = doc.by_id()
    repeated = {}
    for page_index, page in enumerate(doc.blocks):
        height = page.meta.get("height", 0)
        if not height:
            continue
        for block in page.children:
            bbox = block.meta.get("bbox")
            if not bbox or block.kind not in {"paragraph", "heading"}:
                continue
            role = ("page_header" if bbox[3] <= height * .05 else
                    "page_footer" if bbox[1] >= height * .91 else None)
            if role is None:
                continue
            text = "".join(lookup[sid].source for sid in block.segments)
            counter = re.compile(r"\bpage\s+\d+(?:\s*(?:of|/)\s*\d+)?|第\s*\d+\s*页", re.I)
            bare_number = bool(re.fullmatch(r"\s*\d{1,4}\s*", text))
            publisher = bool(re.search(r"copyright|©|版权所有|有限公司|\d{4}-\d{2}-\d{2}", text, re.I))
            if role == "page_footer" and not (counter.search(text) or bare_number or publisher):
                continue
            # Never collapse changing electrical ratings, IDs or dates into
            # one key. Only explicit pagination is allowed to vary.
            normalized = re.sub(r"\s+", "", counter.sub("Page#", text))
            if bare_number:
                normalized = "Page#"
            if normalized:
                repeated.setdefault((role, normalized), []).append((page_index, block))
    for (role, _), entries in repeated.items():
        if len({index for index, _ in entries}) >= 2:
            for _, block in entries:
                block.meta["role"] = role
    for page in doc.blocks:
        add_page_context(page.children, doc)
