"""Text and workbook bindings for native OOXML charts and drawings."""
from __future__ import annotations

import io
import re
import zipfile
from collections import defaultdict
from pathlib import PurePosixPath

from docx.opc.constants import CONTENT_TYPE

from .models import Block
from .office import NS, column_index, q, rels, validate_archive, xml


def referenced_cell(formula: str, index: int):
    if index < 0:
        return None
    match = re.fullmatch(r"(.+)!\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?", formula)
    if not match:
        return None
    sheet, col, row, end_col, end_row = match.groups()
    sheet = sheet[1:-1].replace("''", "'") if sheet.startswith("'") and sheet.endswith("'") else sheet
    if end_col and end_row:
        if col == end_col:
            row = int(row) + index
            if row > int(end_row):
                return None
        elif row == end_row:
            number = column_index(col + row) + index
            if number > column_index(end_col + end_row):
                return None
            col = ""
            while number:
                number, digit = divmod(number - 1, 26)
                col = chr(65 + digit) + col
        else:
            return None
    elif index:
        return None
    return sheet, f"{col}{row}"


def read_drawing_text(reader):
    archive, doc = reader.archive, reader.doc
    names = archive.namelist()
    types = {}
    if "[Content_Types].xml" in names:
        types = {node.get("PartName", "").lstrip("/"): node.get("ContentType", "")
                 for node in xml(archive.read("[Content_Types].xml")) if node.get("PartName")}
    charts = sorted(name for name in names if types.get(name) == CONTENT_TYPE.DML_CHART
                    or re.fullmatch(r"(?:word|ppt|xl)/charts/chart\d+\.xml", name))
    workbooks, loaded = {}, set()
    for part in charts:
        node = xml(archive.read(part)).find("c:externalData", NS)
        relationship = rels(archive, part).get(node.get(q("r", "id"))) if node is not None else None
        if relationship and not relationship[2] and relationship[0].endswith(".xlsx"):
            target = relationship[0]
            if target not in names:
                continue
            workbooks[part] = target
            if target in loaded:
                continue
            loaded.add(target)
            with zipfile.ZipFile(io.BytesIO(archive.read(target))) as embedded:
                validate_archive(embedded)
                first_segment, first_block = len(doc.segments), len(doc.blocks)
                reader.archive = embedded
                try:
                    reader.excel()
                finally:
                    reader.archive = archive
                for segment in doc.segments[first_segment:]:
                    segment.anchor["embedded"] = target
                for block in doc.blocks[first_block:]:
                    block.meta["title"] = "Chart data: " + block.meta.get("title", "Sheet")
    cell_ids = defaultdict(list)
    for segment in doc.segments:
        anchor = segment.anchor
        if "cell" in anchor:
            cell_ids[(anchor.get("embedded"), anchor.get("sheet"), anchor["cell"])].append(segment.id)
    lookup = doc.by_id()
    for part in charts:
        root = xml(archive.read(part))
        section = Block("section", meta={"title": "Chart: " + PurePosixPath(part).stem})
        for paragraph in root.findall(".//c:rich/a:p", NS):
            block = reader.paragraph(paragraph, part, "a")
            if block.segments:
                section.children.append(block)
        for text in root.xpath(".//c:strCache/c:pt/c:v | .//c:strLit/c:pt/c:v | .//c:tx/c:v | .//c:multiLvlStrCache/c:lvl/c:pt/c:v", namespaces=NS):
            if not text.text:
                continue
            ref = next((parent for parent in text.iterancestors()
                        if parent.tag in {q("c", "strRef"), q("c", "multiLvlStrRef")}), None)
            formula = ref.find("c:f", NS) if ref is not None else None
            point = text.getparent()
            cell = referenced_cell(formula.text or "", int(point.get("idx", "0"))) if formula is not None else None
            local = part in workbooks or (doc.format == "xlsx" and root.find("c:externalData", NS) is None)
            linked = cell_ids.get((workbooks.get(part), *cell), []) if cell and local else []
            if linked and "".join(lookup[sid].source for sid in linked) == text.text:
                lookup[linked[0]].anchor.setdefault("mirrors", []).append({
                    "part": part, "path": root.getroottree().getpath(text), "ids": list(linked),
                })
                section.children.append(Block("paragraph", list(linked)))
            else:
                segment = doc.add_segment(text.text, {"part": part, "paths": [root.getroottree().getpath(text)]}, context=text.text)
                section.children.append(Block("paragraph", [segment.id]))
                if formula is not None:
                    doc.warnings.append("Chart: tham chiếu text không hỗ trợ/ngoài file; cache dịch có thể đổi khi refresh.")
        if section.children:
            doc.blocks.append(section)

    # SmartArt data and cached drawings can contain the same paragraph. Reuse
    # exact text groups so both representations follow a single reviewed target.
    drawings = sorted(name for name in names if types.get(name) in {
        CONTENT_TYPE.DML_DIAGRAM_DATA, CONTENT_TYPE.DML_CHARTSHAPES, CONTENT_TYPE.OFC_DRAWING,
    } or types.get(name, "").endswith("diagramDrawing+xml") or re.fullmatch(
        r"(?:word|ppt|xl)/(?:diagrams/(?:data|drawing)[^/]*|drawings/drawing\d+)\.xml", name))
    known = {}
    removed = set()
    for part in drawings:
        root = xml(archive.read(part))
        section = Block("section", meta={"title": "Drawing text: " + PurePosixPath(part).stem})
        for paragraph in root.findall(".//a:p", NS):
            first = len(doc.segments)
            block = reader.paragraph(paragraph, part, "a")
            full = doc.segments[first].context if first < len(doc.segments) else ""
            reused = []
            remapped = {}
            for segment in doc.segments[first:]:
                key = full, segment.source
                prior = known.get(key)
                if prior:
                    prior.anchor.setdefault("mirrors", []).append({
                        "part": part, "paths": segment.anchor["paths"], "ids": [prior.id],
                    })
                    removed.add(segment.id)
                    reused.append(prior.id)
                else:
                    known[key] = segment
                    reused.append(segment.id)
                remapped[segment.id] = reused[-1]
            block.segments = reused
            for entry in block.meta.get("inline", []):
                if "segment" in entry:
                    entry["segment"] = remapped[entry["segment"]]
            if reused:
                section.children.append(block)
        if section.children:
            doc.blocks.append(section)
    doc.segments = [segment for segment in doc.segments if segment.id not in removed]
