"""Full OUC structural stress test with deterministic ASCII replacements, NOT translation-quality testing."""

import hashlib
import json
import resource
import sys
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

resource.setrlimit(resource.RLIMIT_AS, (7 * 1024**3, 7 * 1024**3))
from converter.office import read_office, write_office  # noqa: E402 - isolate runtime before loading converter

root = Path(__file__).resolve().parent.parent / ".test-data" / "excel-improvements"
root.mkdir(parents=True, exist_ok=True)
source = Path(".test-data/chinese-excel-corpus/ouc-procurement-budget.xlsx").resolve()
output = root / "ouc-structural-stress.xlsx"
start = time.monotonic()
report = {
    "test_kind": "deterministic ASCII replacement; not real machine translation",
    "memory_limit_gib": 7,
}
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def digest(path):
    h = hashlib.sha256()
    with zipfile.ZipFile(path) as z:
        h.update(z.read("xl/styles.xml"))
        for part in sorted(z.namelist()):
            if not part.startswith("xl/worksheets/") or not part.endswith(".xml"):
                continue
            h.update(part.encode())
            with z.open(part) as stream:
                stack = []
                for event, n in ET.iterparse(stream, events=("start", "end")):
                    if event == "start":
                        stack.append(n)
                        continue
                    value = None
                    if n.tag == S + "c":
                        f, v = n.find(S + "f"), n.find(S + "v")
                        value = [n.get("r"), n.get("s")]
                        if f is not None:
                            value += [f.text, f.attrib]
                        elif n.get("t", "n") not in ("s", "str", "inlineStr"):
                            value += [n.get("t", "n"), v.text if v is not None else None]
                    elif n.tag in {S + "row", S + "col", S + "dimension", S + "mergeCell"}:
                        value = [n.tag, n.attrib]
                    if value is not None:
                        h.update(json.dumps(value, sort_keys=True).encode())
                    if n.tag in {S + "c", S + "row"}:
                        n.clear()
                        stack[-2].remove(n)
                    stack.pop()
    return h.hexdigest()


try:
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    doc = read_office(source, root / "large-assets-final")
    report.update(segments=len(doc.segments), parse_seconds=round(time.monotonic() - start, 3))
    print(json.dumps(report), flush=True)
    cache = {}
    for s in doc.segments:
        if s.source not in cache:
            cache[s.source] = "Text_" + hashlib.sha256(s.source.encode()).hexdigest()[:16]
        s.target = cache[s.source]
    saved = time.monotonic()
    doc.save(root / "large-document.json")
    report["save_seconds"] = round(time.monotonic() - saved, 3)
    report["document_bytes"] = (root / "large-document.json").stat().st_size
    print(
        json.dumps({"saved": report["document_bytes"], "seconds": report["save_seconds"]}),
        flush=True,
    )
    before = time.monotonic()
    write_office(doc, output)
    report["export_seconds"] = round(time.monotonic() - before, 3)
    report["coverage"] = doc.coverage
    report["output_bytes"] = output.stat().st_size
    report["invariants_preserved"] = digest(source) == digest(output)
    assert report["invariants_preserved"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    report["source_sha256"] = original_hash
    report["status"] = "passed"
except Exception as e:
    report.update(status="failed", error=type(e).__name__ + ": " + str(e))
report.update(
    elapsed_seconds=round(time.monotonic() - start, 3),
    peak_rss_mib=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
)
(root / "large-roundtrip.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False), flush=True)

if report["status"] != "passed":
    sys.exit(1)
