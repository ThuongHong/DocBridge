"""Private LibreOffice renderer for layout validation; never saves workbook changes."""

import subprocess
import sys
import time
from pathlib import Path

import uno
from com.sun.star.beans import PropertyValue

root = Path(__file__).resolve().parent.parent / ".test-data" / "excel-layout"
root.mkdir(parents=True, exist_ok=True)
pipe = "docbridge_layout_validation"


def prop(name, value):
    x = PropertyValue()
    x.Name = name
    x.Value = value
    return x


p = subprocess.Popen(
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
try:
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local
    )
    for _ in range(100):
        try:
            ctx = resolver.resolve(f"uno:pipe,name={pipe};urp;StarOffice.ComponentContext")
            break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError("UNO unavailable")
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    for arg in sys.argv[1:]:
        path = Path(arg).resolve()
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
        try:
            doc.storeToURL(
                path.with_suffix(".pdf").as_uri(),
                (prop("FilterName", "calc_pdf_Export"), prop("Overwrite", True)),
            )
        finally:
            doc.close(True)
    desktop.terminate()
finally:
    p.terminate()
    p.wait(timeout=10)
