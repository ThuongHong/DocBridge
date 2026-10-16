import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import uno
from com.sun.star.beans import PropertyValue

root = Path(__file__).resolve().parent.parent / ".test-data" / "excel-improvements"
root.mkdir(parents=True, exist_ok=True)
pipe = "docbridge_excel_extended_validation"
process = subprocess.Popen(
    [
        "/usr/bin/libreoffice",
        "-env:UserInstallation=" + (root / "lo-profile").as_uri(),
        "--headless",
        "--norestore",
        "--nodefault",
        "--nofirststartwizard",
        f"--accept=pipe,name={pipe};urp;StarOffice.ComponentContext",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)


def prop(name, value):
    item = PropertyValue()
    item.Name, item.Value = name, value
    return item


S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def coordinates(filename):
    result = []
    with zipfile.ZipFile(filename) as z:
        book = ET.fromstring(z.read("xl/workbook.xml"))
        rel = {
            n.get("Id"): n.get("Target").lstrip("/")
            for n in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        }
        for index, sheet in enumerate(book.find(S + "sheets")):
            rid = sheet.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            )
            part = rel[rid]
            if not part.startswith("xl/"):
                part = "xl/" + part
            tree = ET.fromstring(z.read(part))
            for cell in tree.findall(".//" + S + "c"):
                if cell.find(S + "f") is not None:
                    result.append((index, cell.get("r")))
    return result


try:
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local
    )
    for _ in range(100):
        try:
            context = resolver.resolve(f"uno:pipe,name={pipe};urp;StarOffice.ComponentContext")
            break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError("LibreOffice UNO connection failed")
    desktop = context.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", context
    )
    report = {}
    for filename in sys.argv[1:]:
        path = Path(filename).resolve()
        name = path.stem
        doc = desktop.loadComponentFromURL(
            path.as_uri(),
            "_blank",
            0,
            (
                prop("Hidden", True),
                prop("ReadOnly", True),
                prop(
                    "UpdateDocMode",
                    uno.getConstantByName("com.sun.star.document.UpdateDocMode.NO_UPDATE"),
                ),
                prop(
                    "MacroExecutionMode",
                    uno.getConstantByName("com.sun.star.document.MacroExecMode.NEVER_EXECUTE"),
                ),
            ),
        )
        if doc is None:
            raise RuntimeError("LibreOffice failed to open " + filename)
        try:
            doc.calculateAll()
            values = []
            for sheet_index, address in coordinates(path):
                sheet = doc.getSheets().getByIndex(sheet_index)
                cell = sheet.getCellRangeByName(address)
                values.append(
                    {
                        "sheet_index": sheet_index,
                        "cell": address,
                        "value": cell.getValue(),
                        "display": cell.getString(),
                        "error": cell.getError(),
                    }
                )
            report[name] = {
                "formula_cells": values,
                "sheets": list(doc.getSheets().getElementNames()),
            }
            if "hunan" in name:
                doc.storeToURL(
                    (root / (name + ".pdf")).as_uri(),
                    (prop("FilterName", "calc_pdf_Export"), prop("Overwrite", True)),
                )
        finally:
            doc.close(True)
    labels = [Path(name).stem for name in sys.argv[1:]]
    assert labels and len(labels) % 2 == 0, "Pass source/output pairs"
    for index in range(0, len(labels), 2):
        assert (
            report[labels[index]]["formula_cells"] == report[labels[index + 1]]["formula_cells"]
        ), labels[index]
    (root / "recalculation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    desktop.terminate()
finally:
    process.terminate()
    process.wait(timeout=10)
print(json.dumps(report, ensure_ascii=False, indent=2))
