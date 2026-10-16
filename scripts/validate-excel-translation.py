"""Independent real-workbook translation checks; offline Argos, original ZIP preserved."""

import argparse
import hashlib
import importlib.util
import json
import os
import resource
import socket
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

p = argparse.ArgumentParser()
p.add_argument("label")
p.add_argument("source")
args = p.parse_args()
root = Path(__file__).resolve().parent.parent / ".test-data" / "excel-improvements"
root.mkdir(parents=True, exist_ok=True)
run = root / args.label
run.mkdir(exist_ok=True)
os.environ["DOCBRIDGE_DATA_DIR"] = str(run / "data")
from converter.glossary import default_glossary  # noqa: E402 - isolate runtime before loading converter
from converter.pipeline import Pipeline  # noqa: E402 - isolate runtime before loading converter
from converter.providers import ArgosProvider  # noqa: E402 - isolate runtime before loading converter
from converter.store import Store  # noqa: E402 - isolate runtime before loading converter


def deny(*args, **kwargs):
    raise RuntimeError("Network blocked during offline validation")


socket.create_connection = deny
socket.socket.connect = deny
source = Path(args.source).resolve()
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
store = Store(run / "store")
job = store.add(source)
last = [0]


def progress(job, message, done, total):
    if time.monotonic() - last[0] > 25:
        print(message, done, total, flush=True)
        last[0] = time.monotonic()


provider = ArgosProvider(str(Path("assets/models/translate-zh_en-1_9.argosmodel").resolve()))
t0 = time.monotonic()
exports = Pipeline(store, progress=progress).run(
    job, provider, "both", run / "output", glossary=default_glossary()
)
elapsed = time.monotonic() - t0
assert all(v["status"] == "done" for v in exports.values()), exports
output = Path(exports["office"]["path"])
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def invariants(path):
    result = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.startswith("xl/worksheets/") or not name.endswith(".xml"):
                continue
            tree = ET.fromstring(z.read(name))
            cells = {}
            for c in tree.findall(".//" + S + "sheetData/" + S + "row/" + S + "c"):
                f, v = c.find(S + "f"), c.find(S + "v")
                entry = {"style": c.get("s")}
                if f is not None:
                    entry["formula"] = (f.text, f.attrib)
                elif c.get("t", "n") not in ("s", "inlineStr", "str"):
                    entry["numeric"] = (c.get("t", "n"), None if v is None else v.text)
                cells[c.get("r")] = entry
            result[name] = {
                "cells": cells,
                "merges": [n.attrib for n in tree.findall(".//" + S + "mergeCell")],
                "dimensions": [n.attrib for n in tree.findall(S + "dimension")],
                "rows": [n.attrib for n in tree.findall(S + "sheetData/" + S + "row")],
                "cols": [n.attrib for n in tree.findall(S + "cols/" + S + "col")],
            }
    return result


assert invariants(source) == invariants(output), (
    "Cell coordinates/styles, numeric data, formulas or sheet layout changed"
)
with zipfile.ZipFile(source) as a, zipfile.ZipFile(output) as b:
    assert a.namelist() == b.namelist()
    preserved = [n for n in a.namelist() if n == "xl/styles.xml" or "/media/" in n]
    assert all(a.read(n) == b.read(n) for n in preserved)
assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
spec = importlib.util.spec_from_file_location("audit", Path("scripts/audit-excel-corpus.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
source_audit = audit.audit(source, 0)
output_audit = audit.audit(output, 0)
doc = store.load_document(job)
report = {
    "label": args.label,
    "source": str(source),
    "source_sha256": source_hash,
    "output": str(output),
    "job": job,
    "elapsed_seconds": round(elapsed, 3),
    "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
    "segments": len(doc.segments),
    "network_blocked": True,
    "invariants_preserved": True,
    "byte_preserved_parts": preserved,
    "source_audit": source_audit,
    "output_audit": output_audit,
    "warnings": doc.warnings,
    "coverage": getattr(doc, "coverage", {}),
    "exports": exports,
}
(run / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(
    json.dumps(
        {
            k: report[k]
            for k in [
                "label",
                "elapsed_seconds",
                "peak_rss_mib",
                "segments",
                "invariants_preserved",
            ]
        },
        ensure_ascii=False,
    ),
    flush=True,
)
