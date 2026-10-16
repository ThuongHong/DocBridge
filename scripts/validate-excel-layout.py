"""Check readable XLSX export against actual rasterized Excel-like print output.

Requires the dev dependencies and local LibreOffice/UNO. Optional --corpus
reuses the saved Argos translations from validate-excel-translation.py, without
another inference run. All artifacts go to .test-data/excel-layout.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import zipfile
from pathlib import Path

import pypdfium2 as pdfium
import xlsxwriter
from lxml import etree

from converter.models import Document
from converter.office import NS, read_office, write_office

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / ".test-data" / "excel-layout"


def make_fixture():
    source = ARTIFACTS / "fixture-source.xlsx"
    book = xlsxwriter.Workbook(source)
    format = book.add_format(
        {"text_wrap": True, "font_name": "Arial", "font_size": 11, "border": 1, "valign": "top"}
    )
    cases = [
        (
            "Horizontal",
            "A1:B1",
            "The construction safety measures must be inspected before work begins.",
        ),
        (
            "Vertical",
            "A1:B2",
            "Inspect all construction safety measures and environmental protection facilities before the team starts work at this location.",
        ),
        (
            "Plain",
            "A1",
            "Complete the inspection and record all maintenance requirements before starting the installation.",
        ),
    ]
    cases.append(
        (
            "HeightCap",
            "A1:B1",
            "Please complete the construction safety inspection and record the maintenance results. "
            * 8,
        )
    )
    cases.append(
        (
            "WideColumn",
            "A1",
            "Inspect every construction safety measure and record the result before starting work. " * 4,
        )
    )
    for index, (name, merge, _) in enumerate(cases):
        sheet = book.add_worksheet(name)
        sheet.set_column("A:B", 10)
        if name == "WideColumn":
            sheet.set_column("A:A", 140)
            sheet.set_paper(9)
        sheet.set_row(0, 409 if name == "HeightCap" else 16)
        sheet.set_row(1, 16)
        cell_format = (
            book.add_format(
                {
                    "text_wrap": True,
                    "font_name": "Arial",
                    "font_size": 20,
                    "border": 1,
                    "valign": "top",
                }
            )
            if name == "HeightCap"
            else format
        )
        if ":" in merge:
            sheet.merge_range(merge, "检查内容" + str(index), cell_format)
        else:
            sheet.write(merge, "检查内容" + str(index), cell_format)
        sheet.print_area(merge)
    book.close()
    doc = read_office(source, ARTIFACTS / "assets")
    for segment in doc.segments:
        segment.target = cases[int(segment.source[-1])][2]
    return doc


def invariants(path):
    result = {}
    with zipfile.ZipFile(path) as archive:
        for part in archive.namelist():
            if not part.startswith("xl/worksheets/") or not part.endswith(".xml"):
                continue
            root = etree.fromstring(archive.read(part))
            cells = []
            for cell in root.findall("s:sheetData/s:row/s:c", NS):
                formula, value = cell.find("s:f", NS), cell.find("s:v", NS)
                entry = [cell.get("r")]
                if formula is not None:
                    entry += [formula.text, dict(formula.attrib)]
                elif cell.get("t", "n") not in {"s", "str", "inlineStr"}:
                    entry += [cell.get("t", "n"), value.text if value is not None else None]
                cells.append(entry)
            result[part] = {
                "cells": cells,
                "merges": [n.get("ref") for n in root.findall("s:mergeCells/s:mergeCell", NS)],
                "columns": [dict(n.attrib) for n in root.findall("s:cols/s:col", NS)],
                "row_flags": [
                    {k: v for k, v in n.attrib.items() if k not in {"ht", "customHeight"}}
                    for n in root.findall("s:sheetData/s:row", NS)
                ],
            }
        styles = etree.fromstring(archive.read("xl/styles.xml"))
        for tag in ["fills", "borders", "numFmts"]:
            node = styles.find("s:" + tag, NS)
            result[tag] = etree.tostring(node) if node is not None else None
    return result


def assert_original_styles_preserved(source, output):
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
        a = etree.fromstring(before.read("xl/styles.xml"))
        b = etree.fromstring(after.read("xl/styles.xml"))
        for tag in ["fonts", "cellXfs"]:
            original = list(a.find("s:" + tag, NS))
            current = list(b.find("s:" + tag, NS))
            assert len(current) >= len(original)
            assert all(
                etree.tostring(x) == etree.tostring(y)
                for x, y in zip(original, current, strict=False)
            )


def raster_evidence(path, assert_visible, expected):
    doc = pdfium.PdfDocument(path.with_suffix(".pdf"))
    evidence = []
    for index in range(len(doc)):
        page = doc[index]
        text = page.get_textpage()
        full_text_present = "".join(expected[index].split()) == "".join(
            text.get_text_range().split()
        )
        count = text.count_rects()
        within_page = all(
            0 <= text.get_rect(i)[0] <= text.get_rect(i)[2] <= page.get_width()
            for i in range(count)
        )
        x0, y0, x1, y1 = text.get_rect(count - 1)
        scale = 2
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil().convert("L")
        region = image.crop(
            (
                int(x0 * scale),
                int((page.get_height() - y1) * scale),
                int(x1 * scale) + 1,
                int((page.get_height() - y0) * scale) + 1,
            )
        )
        dark = sum(v < 128 for v in region.tobytes()) if 0 <= y0 <= y1 <= page.get_height() else 0
        image.save(ARTIFACTS / f"{path.stem}-page{index + 1}.png")
        evidence.append(
            {
                "page": index + 1,
                "final_line_dark_pixels": dark,
                "full_text_present": full_text_present,
                "text_within_page_width": within_page,
            }
        )
        if assert_visible:
            assert full_text_present, f"{path.name} page {index + 1}: missing printed text"
            assert within_page, f"{path.name} page {index + 1}: text extends beyond paper width"
            assert dark > 20, f"{path.name} page {index + 1}: final text line is clipped"
        bitmap.close()
        text.close()
        page.close()
    doc.close()
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", action="store_true")
    args = parser.parse_args()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    report = {}
    doc = make_fixture()
    outputs = []
    for mode in ["preserve", "readable"]:
        output = ARTIFACTS / f"fixture-{mode}.xlsx"
        write_office(doc, output, excel_layout=mode)
        assert invariants(Path(doc.source_path)) == invariants(output)
        assert_original_styles_preserved(Path(doc.source_path), output)
        outputs.append(output)
    subprocess.run(
        ["/usr/bin/python3", str(ROOT / "scripts/render-excel-layout.py"), *map(str, outputs)],
        check=True,
        timeout=60,
    )
    report["preserve"] = raster_evidence(outputs[0], False, [s.text for s in doc.segments])
    report["readable"] = raster_evidence(outputs[1], True, [s.text for s in doc.segments])
    assert any(item["final_line_dark_pixels"] == 0 for item in report["preserve"]), (
        "Control must reproduce visible clipping"
    )
    report["layout_diagnostics"] = doc.coverage
    if args.corpus:
        for label in ["current-hunan", "current-mof"]:
            run = ROOT / ".test-data/excel-improvements" / label
            prior = json.loads((run / "validation.json").read_text())
            doc = Document.load(run / "store/jobs" / prior["job"] / "document.json")
            output = ARTIFACTS / (Path(prior["output"]).stem + ".readable.xlsx")
            write_office(doc, output, excel_layout="readable")
            assert invariants(Path(doc.source_path)) == invariants(output)
            assert_original_styles_preserved(Path(doc.source_path), output)
            report[label] = {
                "output": str(output),
                "coverage": doc.coverage,
                "invariants_preserved": True,
            }
            subprocess.run(
                ["/usr/bin/python3", str(ROOT / "scripts/render-excel-layout.py"), str(output)],
                check=True,
                timeout=60,
            )
            pdf = pdfium.PdfDocument(output.with_suffix(".pdf"))
            report[label]["pdf_pages"] = len(pdf)
            if label == "current-hunan":
                # This real sheet has one wide cell already at Excel's height
                # cap. Text extraction alone passed even while print clipped it.
                expected = next(
                    s.text for s in doc.segments
                    if s.anchor.get("part") == "xl/worksheets/sheet2.xml"
                    and s.anchor.get("cell") == "A1"
                )
                matches = []
                for index in range(len(pdf)):
                    page = pdf[index]
                    text = page.get_textpage()
                    if "".join(text.get_text_range().split()) == "".join(expected.split()):
                        rects = [text.get_rect(i) for i in range(text.count_rects())]
                        assert all(0 <= r[0] <= r[2] <= page.get_width() for r in rects)
                        bitmap = page.render(scale=1.4)
                        bitmap.to_pil().save(ARTIFACTS / "hunan-instructions.png")
                        bitmap.close()
                        matches.append(index + 1)
                    text.close()
                    page.close()
                assert len(matches) == 1, "Hunan instructions must print in full on one page"
                report[label]["instructions_print_check"] = {
                    "page": matches[0], "full_text_present": True,
                    "text_within_page_width": True,
                }
            for index in [0, min(1, len(pdf) - 1)]:
                page = pdf[index]
                bitmap = page.render(scale=1.4)
                bitmap.to_pil().save(ARTIFACTS / f"{label}-page{index + 1}.png")
                bitmap.close()
                page.close()
            pdf.close()
    (ARTIFACTS / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
