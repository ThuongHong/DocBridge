"""Inventory real XLSX sources without modifying or recalculating them.

Read OOXML independently of the converter, including hidden sheets and sparse
cells. Optionally compare ordinary Chinese cell text with converter segments.
Large files are inventoried with streaming XML; parser comparisons are bounded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U000323af]")


def relationships(archive, part):
    folder, name = posixpath.split(part)
    rel_part = posixpath.join(folder, "_rels", name + ".rels")
    if rel_part not in archive.namelist():
        return {}
    result = {}
    for item in ET.fromstring(archive.read(rel_part)):
        if item.get("TargetMode") == "External":
            continue
        target = item.get("Target", "")
        resolved = (target.lstrip("/") if target.startswith("/")
                    else posixpath.normpath(posixpath.join(folder, target)))
        result[item.get("Id")] = (resolved, item.get("Type", ""))
    return result


def string_text(content):
    if content is None:
        return ""
    # Phonetic annotations are not the displayed cell string.
    return "".join(n.text or "" for n in content.findall(S + "t")
                   + content.findall(S + "r/" + S + "t"))


def audit(path, parser_limit):
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    result = {"file": path.name, "bytes": path.stat().st_size, "sha256": digest}
    expected = {}
    chinese_strings = Counter()
    with zipfile.ZipFile(path) as archive:
        result["uncompressed_bytes"] = sum(i.file_size for i in archive.infolist())
        workbook_part = next((target for target, kind in relationships(archive, "").values()
                              if kind.endswith("/officeDocument")), "xl/workbook.xml")
        rels = relationships(archive, workbook_part)
        shared_part = next((target for target, kind in rels.values()
                            if kind.endswith("/sharedStrings")), None)
        shared, shared_rich = [], []
        if shared_part:
            for item in ET.fromstring(archive.read(shared_part)):
                shared.append(string_text(item))
                shared_rich.append(item.find(S + "r") is not None)
        workbook = ET.fromstring(archive.read(workbook_part))
        result["sheets"] = []
        for sheet in workbook.findall(S + "sheets/" + S + "sheet"):
            part = rels[sheet.get(R + "id")][0]
            info = {"name": sheet.get("name"), "state": sheet.get("state", "visible"),
                    "chinese_cells": 0, "text_cells": 0, "formula_cells": 0,
                    "cross_sheet_formula_nodes": 0, "chinese_formula_caches": 0,
                    "merged_ranges": 0, "rich_text_cells": 0,
                    "validation_rules": 0, "chinese_inline_list_options": 0,
                    "chinese_header_footer_nodes": 0,
                    "formula_examples": [], "merge_examples": []}
            stack = []
            with archive.open(part) as stream:
                for event, node in ET.iterparse(stream, events=("start", "end")):
                    if event == "start":
                        stack.append(node)
                        continue
                    if node.tag == S + "c" and len(stack) >= 3 and stack[-2].tag == S + "row":
                        formula, value = node.find(S + "f"), node.find(S + "v")
                        text = ""
                        if formula is not None:
                            info["formula_cells"] += 1
                            info["cross_sheet_formula_nodes"] += "!" in (formula.text or "")
                            info["chinese_formula_caches"] += bool(
                                node.get("t") == "str" and value is not None
                                and HAN.search(value.text or ""))
                            if formula.text and len(info["formula_examples"]) < 3:
                                info["formula_examples"].append(
                                    {"cell": node.get("r"), "formula": formula.text})
                        elif node.get("t") == "s" and value is not None:
                            text = shared[int(value.text)]
                            info["rich_text_cells"] += shared_rich[int(value.text)]
                        elif node.get("t") == "inlineStr":
                            content = node.find(S + "is")
                            text = string_text(content)
                            info["rich_text_cells"] += bool(
                                content is not None and content.find(S + "r") is not None)
                        elif node.get("t") == "str" and value is not None:
                            text = value.text or ""
                        info["text_cells"] += bool(text.strip())
                        if HAN.search(text):
                            info["chinese_cells"] += 1
                            chinese_strings[text] += 1
                            if expected is not None:
                                if len(expected) >= parser_limit:
                                    expected = None
                                else:
                                    expected[(part, node.get("r"))] = text
                        node.clear()
                        stack[-2].remove(node)
                    elif node.tag == S + "row":
                        node.clear()
                        stack[-2].remove(node)
                    elif node.tag == S + "mergeCell":
                        info["merged_ranges"] += 1
                        if len(info["merge_examples"]) < 3:
                            info["merge_examples"].append(node.get("ref"))
                    elif node.tag == S + "dataValidation":
                        info["validation_rules"] += 1
                        formula = node.find(S + "formula1")
                        value = formula.text if formula is not None else None
                        if (node.get("type") == "list" and value and value.startswith('"')
                                and value.endswith('"')):
                            info["chinese_inline_list_options"] += sum(
                                bool(HAN.search(item)) for item in value[1:-1].split(","))
                    elif len(stack) >= 2 and stack[-2].tag == S + "headerFooter":
                        info["chinese_header_footer_nodes"] += bool(HAN.search(node.text or ""))
                    stack.pop()
            result["sheets"].append(info)
        result["totals"] = {key: sum(sheet[key] for sheet in result["sheets"])
                            for key in result["sheets"][0]
                            if isinstance(result["sheets"][0][key], int)}
        result["sheet_count"] = len(result["sheets"])
        result["unique_chinese_strings"] = len(chinese_strings)
        result["most_repeated_chinese_strings"] = [
            {"text": text[:160], "count": count}
            for text, count in chinese_strings.most_common(3)]
        result["meets_core_criteria"] = (
            len(result["sheets"]) >= 3 and result["totals"]["formula_cells"] > 0
            and result["totals"]["merged_ranges"] > 0
            and result["totals"]["chinese_cells"] > 0)
    if parser_limit:
        if expected is None:
            result["parser"] = {"status": "not_run", "reason": "Chinese cell limit exceeded",
                                "max_chinese_cells": parser_limit}
        else:
            from converter.office import read_office

            with tempfile.TemporaryDirectory() as temporary:
                doc = read_office(path.resolve(), Path(temporary))
            actual = defaultdict(str)
            for segment in doc.segments:
                anchor = segment.anchor
                if "cell" in anchor and not anchor.get("embedded"):
                    actual[(anchor["part"], anchor["cell"])] += segment.source
            missing = [f"{part}!{cell}" for (part, cell), text in expected.items()
                       if actual[(part, cell)] != text]
            result["parser"] = {"status": "compared", "segments": len(doc.segments),
                                "chinese_cells_compared": len(expected),
                                "missing_or_changed_cells": len(missing),
                                "missing_examples": missing[:10],
                                "chinese_sheet_names_without_segments": [
                                    s["name"] for s in result["sheets"]
                                    if HAN.search(s["name"]) and not any(
                                        seg.anchor.get("category") == "sheet_title"
                                        and seg.source == s["name"]
                                        for seg in doc.segments)]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--parser-max-chinese-cells", type=int, default=0,
                        help="Compare parser coverage up to this many Chinese cells; 0 disables")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = []
    for path in sorted(args.directory.glob("*.xlsx")):
        result = audit(path, args.parser_max_chinese_cells)
        results.append(result)
        print(json.dumps({k: result[k] for k in ("file", "sheet_count", "totals",
                                                "meets_core_criteria")}, ensure_ascii=False),
              flush=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
