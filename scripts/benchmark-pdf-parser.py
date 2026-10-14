"""Measure source-language PDF parsing, with no translation or API calls."""
import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

from converter.markdown import render_markdown
from converter.pdf import read_pdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    fingerprint = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                   for name in ['src/converter/pdf.py', 'src/converter/pdf_layout.py',
                                'src/converter/markdown.py']}
    started = time.perf_counter()
    doc = read_pdf(args.source, args.output / 'assets', progress=print)
    elapsed = time.perf_counter() - started
    doc.save(args.output / 'document.json')
    (args.output / 'source.md').write_text(render_markdown(doc, 'assets', source=True), encoding='utf-8')
    status = Path('/proc/self/status')
    peak = next((int(line.split()[1]) for line in status.read_text().splitlines()
                 if line.startswith('VmHWM:')), None) if status.exists() else None
    report = {'source': str(args.source.resolve()), 'source_sha256': doc.source_hash,
              'adapter_version': doc.adapter_version, 'pages': len(doc.blocks),
              'segments': len(doc.segments), 'assets': len(doc.assets),
              'parse_seconds': elapsed, 'linux_process_peak_rss_kib': peak,
              'python': platform.python_version(), 'source_hashes': fingerprint,
              'translation_invoked': False}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
