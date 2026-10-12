# Windows uses scripts/build-windows.ps1; Linux sets the same bundle environment paths.
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

root = Path(SPECPATH).parent
datas = [(str(root / "config/provider.json"), "config")]
hidden = ["keyring.backends.Windows"] if sys.platform == "win32" else []
binaries = []
datas += collect_data_files("docx")
datas += collect_data_files("converter", includes=["data/*.json"])
if os.environ.get("CONVERTER_BUNDLE_OFFLINE", "1") == "1":
    for module in ["argostranslate", "ctranslate2", "sentencepiece", "stanza"]:
        module_datas, module_binaries, module_hidden = collect_all(module)
        datas += module_datas
        binaries += module_binaries
        hidden += module_hidden
    datas.append((os.environ["CONVERTER_BUNDLE_MODELS"], "assets/models"))
    datas.append((os.environ["CONVERTER_BUNDLE_TESSERACT"], "assets/tesseract"))

a = Analysis(
    [str(root / "packaging/launcher.py")], pathex=[str(root / "src")],
    binaries=binaries, datas=datas, hiddenimports=hidden,
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
              "PySide6.QtPdf", "PySide6.QtPdfWidgets", "tkinter", "pytest", "ruff"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Converter", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Converter")
