from __future__ import annotations

import posixpath
import re
import zipfile
from copy import deepcopy
from pathlib import Path, PurePosixPath

from lxml import etree

from .models import Block, Document, file_hash

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
PARSER = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False)
MAX_PACKAGE_BYTES = 512 * 1024 * 1024


def xml(data: bytes):
    return etree.fromstring(data, PARSER)


def q(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


def rels(archive: zipfile.ZipFile, part: str) -> dict:
    directory, basename = posixpath.split(part)
    name = posixpath.join(directory, "_rels", basename + ".rels")
    if name not in archive.namelist():
        return {}
    result = {}
    for item in xml(archive.read(name)):
        if item.get("TargetMode") == "External":
            result[item.get("Id")] = (item.get("Target"), item.get("Type"), True)
        else:
            target = item.get("Target", "")
            resolved = (
                target.lstrip("/")
                if target.startswith("/")
                else posixpath.normpath(posixpath.join(directory, target))
            )
            result[item.get("Id")] = (resolved, item.get("Type"), False)
    return result


class OfficeReader:
    def __init__(self, source: Path, assets_dir: Path):
        self.source = source
        self.assets_dir = assets_dir
        self.doc = Document(str(source), file_hash(source), source.suffix.lower().lstrip("."))
        self.archive = zipfile.ZipFile(source)
        if sum(info.file_size for info in self.archive.infolist()) > MAX_PACKAGE_BYTES:
            raise ValueError("Office package quá lớn sau giải nén (giới hạn 512 MB).")
        if any(name.startswith("_xmlsignatures/") for name in self.archive.namelist()):
            raise ValueError("Chưa hỗ trợ dịch file Office có chữ ký số.")
        if any(name.endswith("vbaProject.bin") for name in self.archive.namelist()):
            raise ValueError("Chưa hỗ trợ file Office có macro.")
        if len(self.archive.namelist()) != len(set(self.archive.namelist())):
            raise ValueError("Office package chứa entries trùng tên.")

    def close(self):
        self.archive.close()

    def asset(self, name: str) -> str | None:
        if name not in self.archive.namelist():
            return None
        suffix = PurePosixPath(name).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".svg", ".webp"}:
            self.doc.warnings.append(
                f"Ảnh {PurePosixPath(name).name} cần chuyển định dạng để preview."
            )
            return None
        key = f"image-{len(self.doc.assets):04d}{suffix}"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        path = self.assets_dir / key
        path.write_bytes(self.archive.read(name))
        self.doc.assets[key] = str(path)
        return key

    def pictures(self, node, relationships: dict) -> list[Block]:
        result = []
        for image in node.findall(".//a:blip", NS):
            rid = image.get(q("r", "embed"))
            relationship = relationships.get(rid)
            if relationship and not relationship[2]:
                key = self.asset(relationship[0])
                if key:
                    result.append(Block("image", meta={"asset": key}))
        return result

    def paragraph(self, node, part: str, prefix: str, context: str = "") -> Block:
        tree = node.getroottree()
        candidates = []
        for text in node.findall(f".//{prefix}:t", NS):
            # Text boxes have nested paragraphs; keep each text node in exactly one segment.
            nearest = next((a for a in text.iterancestors() if a.tag == q(prefix, "p")), None)
            if nearest is node:
                candidates.append(text)
        full_text = "".join(item.text or "" for item in candidates)
        block = Block("paragraph")
        if prefix == "w":
            style = node.find("w:pPr/w:pStyle", NS)
            if style is not None:
                name = style.get(q("w", "val"), "")
                match = re.search(r"(?:heading|标题)\s*([1-6])", name, re.I)
                if match:
                    block.kind = "heading"
                    block.meta["level"] = int(match[1])
            if node.find("w:pPr/w:numPr", NS) is not None:
                block.kind = "list"

        groups: list[tuple[tuple, list]] = []
        for text_index, text in enumerate(candidates):
            run = text.getparent()
            props = run.find(f"{prefix}:rPr", NS)
            style_key = etree.tostring(props) if props is not None else b""
            hyperlink = next(
                (
                    ancestor
                    for ancestor in text.iterancestors()
                    if ancestor.tag == q("w", "hyperlink")
                ),
                None,
            )
            # Never merge across tabs, breaks, fields, hyperlinks or nested text frames.
            prev = text.getprevious()
            barrier = prev is not None and prev.tag not in {q(prefix, "rPr"), q(prefix, "t")}
            if run.getprevious() is not None and run.getprevious().tag != q(prefix, "r"):
                barrier = True
            if text_index:
                previous_run = candidates[text_index - 1].getparent()
                if previous_run is not run:
                    if len(previous_run) and previous_run[-1].tag != q(prefix, "t"):
                        barrier = True
                    if run.getprevious() is not previous_run:
                        barrier = True
            key = (style_key, tree.getpath(hyperlink) if hyperlink is not None else "", barrier)
            if groups and groups[-1][0][:2] == key[:2] and not barrier:
                groups[-1][1].append(text)
            else:
                groups.append((key, [text]))

        for _, nodes in groups:
            source = "".join(item.text or "" for item in nodes)
            if not source:
                continue
            props = nodes[0].getparent().find(f"{prefix}:rPr", NS)
            inline = {}
            link_node = next(
                (
                    ancestor
                    for ancestor in nodes[0].iterancestors()
                    if ancestor.tag == q("w", "hyperlink")
                ),
                None,
            )
            if props is not None:
                if prefix == "w":
                    for attr in ["b", "i", "strike"]:
                        value = props.find(f"w:{attr}", NS)
                        inline[attr] = value is not None and value.get(q("w", "val"), "1") not in {
                            "0",
                            "false",
                            "off",
                        }
                else:
                    inline = {attr: props.get(attr) == "1" for attr in ["b", "i", "strike"]}
            if link_node is not None:
                relationship = rels(self.archive, part).get(link_node.get(q("r", "id")))
                if (
                    relationship
                    and relationship[2]
                    and relationship[0].startswith(("https://", "http://", "mailto:"))
                ):
                    inline["link"] = relationship[0]
            segment = self.doc.add_segment(
                source,
                {"part": part, "paths": [tree.getpath(item) for item in nodes]},
                context=context or full_text,
                style=inline,
            )
            # Pure whitespace doesn't need translation, but belongs to the same model.
            if not source.strip():
                segment.target = source
            block.segments.append(segment.id)
        return block

    def word_container(self, node, part: str, relationships: dict) -> list[Block]:
        result = []
        for child in node:
            if child.tag == q("w", "p"):
                paragraph = self.paragraph(child, part, "w")
                if paragraph.segments:
                    result.append(paragraph)
                result.extend(self.pictures(child, relationships))
                for textbox in child.findall(".//w:txbxContent", NS):
                    result.extend(self.word_container(textbox, part, relationships))
            elif child.tag == q("w", "tbl"):
                table = Block("table")
                for row in child.findall("w:tr", NS):
                    row_block = Block("row")
                    for cell in row.findall("w:tc", NS):
                        span = cell.find("w:tcPr/w:gridSpan", NS)
                        merge = cell.find("w:tcPr/w:vMerge", NS)
                        if span is not None or merge is not None:
                            self.doc.warnings.append(
                                "Bảng Word có ô gộp: Markdown biểu diễn dưới dạng bảng đơn giản."
                            )
                        row_block.children.append(
                            Block("cell", children=self.word_container(cell, part, relationships))
                        )
                    table.children.append(row_block)
                result.append(table)
            elif child.tag == q("w", "del"):
                self.doc.warnings.append(
                    "Tracked deletion giữ nguyên trong Office và bỏ khỏi Markdown."
                )
            elif child.tag in {
                q("w", "sdt"),
                q("w", "sdtContent"),
                q("w", "ins"),
                q("w", "customXml"),
            }:
                result.extend(self.word_container(child, part, relationships))
        return result

    def word(self):
        names = self.archive.namelist()
        part_names = ["word/document.xml"] + sorted(
            name
            for name in names
            if re.fullmatch(r"word/(?:header\d+|footer\d+|footnotes|endnotes|comments)\.xml", name)
        )
        for part in part_names:
            root = xml(self.archive.read(part))
            relationships = rels(self.archive, part)
            if part == "word/document.xml":
                body = root.find("w:body", NS)
                self.doc.blocks.extend(self.word_container(body, part, relationships))
            else:
                section = Block("section", meta={"title": PurePosixPath(part).stem})
                if part.endswith(("footnotes.xml", "endnotes.xml", "comments.xml")):
                    for note in root:
                        if note.get(q("w", "type")) in {"separator", "continuationSeparator"}:
                            continue
                        section.children.extend(self.word_container(note, part, relationships))
                else:
                    section.children = self.word_container(root, part, relationships)
                if section.children:
                    self.doc.blocks.append(section)
        self.coverage_warnings()

    def powerpoint(self):
        slide_parts = sorted(
            [
                name
                for name in self.archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ],
            key=lambda name: int(re.search(r"slide(\d+)", name)[1]),
        )
        presentation = xml(self.archive.read("ppt/presentation.xml"))
        presentation_rels = rels(self.archive, "ppt/presentation.xml")
        slide_ids = presentation.findall("p:sldIdLst/p:sldId", NS)
        if slide_ids:
            slide_parts = [presentation_rels[item.get(q("r", "id"))][0] for item in slide_ids]
        for number, part in enumerate(slide_parts, 1):
            section = Block("section", meta={"title": f"Slide {number}"})
            root = xml(self.archive.read(part))
            relationships = rels(self.archive, part)
            for child in root.findall(".//p:spTree/*", NS):
                section.children.extend(self.slide_shape(child, part, relationships))
            for target, kind, external in relationships.values():
                if kind and kind.endswith("/notesSlide") and not external:
                    notes = xml(self.archive.read(target))
                    note_section = Block("section", meta={"title": "Speaker notes"})
                    for shape in notes.findall(".//p:sp", NS):
                        placeholder = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
                        if placeholder is not None and placeholder.get("type") in {
                            "sldImg",
                            "sldNum",
                            "hdr",
                            "ftr",
                            "dt",
                        }:
                            continue
                        for paragraph in shape.findall(".//a:p", NS):
                            block = self.paragraph(paragraph, target, "a")
                            if block.segments:
                                note_section.children.append(block)
                    if note_section.children:
                        section.children.append(note_section)
            self.doc.blocks.append(section)
        self.coverage_warnings()

    def slide_shape(self, node, part: str, relationships: dict) -> list[Block]:
        if node.tag == q("p", "grpSp"):
            return [
                block for child in node for block in self.slide_shape(child, part, relationships)
            ]
        if node.tag == q("p", "pic"):
            return self.pictures(node, relationships)
        result = []
        table = node.find(".//a:tbl", NS)
        if table is not None:
            block = Block("table")
            for row in table.findall("a:tr", NS):
                rb = Block("row")
                for cell in row.findall("a:tc", NS):
                    cb = Block("cell")
                    for para in cell.findall("a:txBody/a:p", NS):
                        cb.children.append(self.paragraph(para, part, "a"))
                    rb.children.append(cb)
                block.children.append(rb)
            result.append(block)
        else:
            for paragraph in node.findall(".//a:p", NS):
                block = self.paragraph(paragraph, part, "a")
                if block.segments:
                    result.append(block)
        return result

    def excel(self):
        shared_part = "xl/sharedStrings.xml"
        shared = (
            xml(self.archive.read(shared_part)) if shared_part in self.archive.namelist() else None
        )
        shared_items = list(shared) if shared is not None else []
        workbook = xml(self.archive.read("xl/workbook.xml"))
        relationships = rels(self.archive, "xl/workbook.xml")
        for sheet in workbook.findall("s:sheets/s:sheet", NS):
            part = relationships[sheet.get(q("r", "id"))][0]
            root = xml(self.archive.read(part))
            section = Block("section", meta={"title": sheet.get("name", "Sheet")})
            table = Block("table")
            rows = root.findall("s:sheetData/s:row", NS)
            max_column = 0
            for row in rows:
                for cell in row.findall("s:c", NS):
                    max_column = max(max_column, column_index(cell.get("r", "A1")))
            # Preserve sparse cell addresses without allocating a full 16k-column table.
            if max_column > 100:
                self.doc.warnings.append(
                    f"Sheet {sheet.get('name')}: quá 100 cột, Markdown xuất theo cell address."
                )
            for row in rows:
                cells = {}
                for cell in row.findall("s:c", NS):
                    address = cell.get("r", "A1")
                    block = Block("cell", meta={"address": address})
                    value = cell.find("s:v", NS)
                    formula = cell.find("s:f", NS)
                    if formula is not None:
                        block.meta["literal"] = "=" + (formula.text or "")
                    elif cell.get("t") in {"s", "inlineStr"}:
                        content = (
                            shared_items[int(value.text)]
                            if cell.get("t") == "s" and value is not None
                            else cell.find("s:is", NS)
                        )
                        if content is not None:
                            full = "".join(content.itertext())
                            for index, text in enumerate(content.findall(".//s:t", NS)):
                                style = {}
                                props = text.getparent().find("s:rPr", NS)
                                if props is not None:
                                    style = {
                                        attr: props.find(f"s:{attr}", NS) is not None
                                        for attr in ["b", "i", "strike"]
                                    }
                                anchor = {
                                    "part": part,
                                    "cell": address,
                                    "text_index": index,
                                    "shared": cell.get("t") == "s",
                                }
                                segment = self.doc.add_segment(
                                    text.text or "", anchor, context=full, style=style
                                )
                                if not segment.source.strip():
                                    segment.target = segment.source
                                block.segments.append(segment.id)
                    else:
                        block.meta["literal"] = value.text if value is not None else ""
                    cells[column_index(address)] = block
                if max_column <= 100:
                    table.children.append(
                        Block(
                            "row",
                            children=[
                                cells.get(i, Block("cell")) for i in range(1, max_column + 1)
                            ],
                        )
                    )
                else:
                    for block in cells.values():
                        table.children.append(
                            Block(
                                "row",
                                children=[
                                    Block("cell", meta={"literal": block.meta["address"]}),
                                    block,
                                ],
                            )
                        )
            section.children.append(table)
            if root.find("s:mergeCells", NS) is not None:
                self.doc.warnings.append(
                    f"Sheet {sheet.get('name')}: merged cells giữ trong XLSX; Markdown dùng bảng đơn giản."
                )
            # Drawings stay untouched in Office; linked pictures can also be exported to MD.
            for target, kind, external in rels(self.archive, part).values():
                if not external and kind and kind.endswith("/drawing"):
                    section.children.extend(
                        self.pictures(xml(self.archive.read(target)), rels(self.archive, target))
                    )
            self.doc.blocks.append(section)
        self.coverage_warnings()

    def coverage_warnings(self):
        names = self.archive.namelist()
        if any("/charts/" in name and name.endswith(".xml") for name in names):
            self.doc.warnings.append(
                "Charts giữ nguyên trong Office; text trong chart chưa dịch, chart chưa xuất vào Markdown."
            )
        if any("/diagrams/" in name and name.endswith(".xml") for name in names):
            self.doc.warnings.append(
                "SmartArt giữ nguyên trong Office; text SmartArt chưa dịch hoặc xuất Markdown."
            )
        if self.doc.format == "pptx":
            self.doc.warnings.append(
                "PPTX giữ font/khung gốc; cần review nguy cơ tràn chữ sau dịch."
            )
        if self.doc.format == "docx":
            self.doc.warnings.append(
                "Word giữ format gốc; số trang có thể thay đổi khi chữ tiếng Anh dài hơn."
            )
        self.doc.warnings = list(dict.fromkeys(self.doc.warnings))


def column_index(address: str) -> int:
    result = 0
    for char in re.match(r"[A-Za-z]+", address)[0].upper():
        result = result * 26 + ord(char) - 64
    return result


def read_office(source: Path, assets_dir: Path) -> Document:
    if not zipfile.is_zipfile(source):
        raise ValueError("File Office không phải OOXML hợp lệ hoặc đang được mã hóa.")
    reader = OfficeReader(source, assets_dir)
    try:
        {".docx": reader.word, ".pptx": reader.powerpoint, ".xlsx": reader.excel}[
            source.suffix.lower()
        ]()
        return reader.doc
    finally:
        reader.close()


def set_text(node, text: str):
    node.text = text
    if text and (text[0].isspace() or text[-1].isspace()):
        node.set(XML_SPACE, "preserve")


def write_office(doc: Document, target: Path):
    """Patch only text-bearing parts; copy all other uncompressed entries verbatim."""
    if file_hash(Path(doc.source_path)) != doc.source_hash:
        raise ValueError("File nguồn đã thay đổi; không thể dùng mapping của bản dịch này.")
    if not doc.complete():
        raise ValueError("Còn đoạn chưa dịch; hãy hoàn thành hoặc review trước khi xuất Office.")
    with zipfile.ZipFile(doc.source_path) as archive:
        roots = {}
        shared_root = None
        if doc.format == "xlsx" and "xl/sharedStrings.xml" in archive.namelist():
            shared_root = xml(archive.read("xl/sharedStrings.xml"))
        cell_groups = {}
        for segment in doc.segments:
            if segment.target == segment.source:
                continue
            anchor = segment.anchor
            if "part" not in anchor:
                continue
            part = anchor["part"]
            if part not in roots:
                roots[part] = xml(archive.read(part))
            root = roots[part]
            if "cell" in anchor:
                cell_groups.setdefault((part, anchor["cell"]), []).append(segment)
            else:
                for i, path in enumerate(anchor["paths"]):
                    nodes = root.xpath(
                        path, namespaces={**NS, **{k: v for k, v in root.nsmap.items() if k}}
                    )
                    if len(nodes) != 1:
                        raise ValueError(
                            "Mapping Office không còn hợp lệ; vui lòng phân tích lại file."
                        )
                    set_text(nodes[0], segment.text if i == 0 else "")
        shared_changed = False
        for (part, address), segments in cell_groups.items():
            cell = roots[part].find(f".//s:c[@r='{address}']", NS)
            if cell is None or cell.find("s:f", NS) is not None:
                raise ValueError("Mapping cell không hợp lệ.")
            if cell.get("t") == "s":
                # Clone per cell: equal source strings can have different reviewed translations.
                old_index = int(cell.find("s:v", NS).text)
                content = deepcopy(shared_root[old_index])
                for segment in segments:
                    texts = content.findall(".//s:t", NS)
                    set_text(texts[segment.anchor["text_index"]], segment.text)
                new_index = len(shared_root)
                shared_root.append(content)
                cell.find("s:v", NS).text = str(new_index)
                shared_changed = True
            else:
                content = cell.find("s:is", NS)
                for segment in segments:
                    texts = content.findall(".//s:t", NS)
                    set_text(texts[segment.anchor["text_index"]], segment.text)
        if shared_changed:
            shared_root.set("uniqueCount", str(len(shared_root)))
            roots["xl/sharedStrings.xml"] = shared_root
        with zipfile.ZipFile(target, "w") as output:
            for entry in archive.infolist():
                data = archive.read(entry.filename)
                if entry.filename in roots:
                    data = etree.tostring(
                        roots[entry.filename], xml_declaration=True, encoding="UTF-8"
                    )
                output.writestr(entry, data)
            output.comment = archive.comment
