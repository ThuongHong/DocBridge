"""Score both engines against manually inspected source assertions, not each other."""
import argparse
import json
import re
import unicodedata
from pathlib import Path

from lxml import html

ROOT = Path(__file__).resolve().parents[1]


def normalize(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).replace("–", "-").replace("−", "-")


def docbridge(path):
    data = json.loads(path.read_text())
    lookup = {s["id"]: s["source"] for s in data["segments"]}
    pages = []

    def text(block):
        return "".join(lookup[s] for s in block["segments"])

    for page in data["blocks"]:
        blocks, tables = [], []
        for block in page["children"]:
            if block["meta"].get("role") in {"page_header", "page_footer"}:
                continue
            if block["kind"] == "table":
                rows = [[text(c) for c in row["children"]] for row in block["children"]]
                tables.extend(rows)
                blocks.append("".join("".join(row) for row in rows))
            elif block["segments"]:
                blocks.append(text(block))
        pages.append({"blocks": [normalize(t) for t in blocks],
                      "rows": [[normalize(v) for v in r] for r in tables]})
    return pages


def docling(path):
    data = json.loads(path.read_text())
    refs = {item["self_ref"]: item for group in ["groups", "texts", "tables", "pictures"]
            for item in data[group]}
    pages = [{"blocks": [], "rows": []} for _ in data["pages"]]

    def walk(ref):
        item = refs[ref["$ref"]]
        if item.get("content_layer") == "furniture":
            return
        if item.get("prov"):
            page = pages[item["prov"][0]["page_no"] - 1]
            if "text" in item:
                page["blocks"].append(normalize(item["text"]))
            elif "data" in item and "table_cells" in item["data"]:
                table = item["data"]
                rows = [[""] * table["num_cols"] for _ in range(table["num_rows"])]
                for cell in table["table_cells"]:
                    for r in range(cell["start_row_offset_idx"], cell["end_row_offset_idx"]):
                        for c in range(cell["start_col_offset_idx"], cell["end_col_offset_idx"]):
                            rows[r][c] = normalize(cell["text"])
                page["rows"].extend(rows)
                page["blocks"].append("".join("".join(r) for r in rows))
        for child in item.get("children", []):
            walk(child)

    for child in data["body"]["children"]:
        walk(child)
    return pages


def check(case, page):
    text = "".join(page["blocks"])
    kind = case["kind"]
    if kind == "presence":
        return normalize(case["value"]) in text
    if kind == "absent":
        return normalize(case["value"]) not in text
    if kind == "block":
        return any(normalize(case["value"]) in b for b in page["blocks"])
    if kind == "order":
        a, b = normalize(case["before"]), normalize(case["after"])
        return a in text and b in text and text.index(a) < text.index(b)
    if kind == "separate":
        a, b = normalize(case["first"]), normalize(case["second"])
        return a in text and b in text and all(not (a in t and b in t) for t in page["blocks"])
    rows = [r for r in page["rows"] if r and r[0] == normalize(case["key"])]
    if kind == "row":
        return any(all(int(c) < len(r) and r[int(c)] == normalize(v)
                       for c, v in case["values"].items()) for r in rows)
    if kind == "row_contains":
        c = case["column"]
        return any(c < len(r) and normalize(case["value"]) in r[c] for r in rows)
    raise ValueError(kind)


def table_rows(source):
    parsed = html.fromstring(source)
    grid = {}
    for r, tr in enumerate(parsed.xpath('.//tr')):
        c = 0
        for cell in tr.xpath('./td|./th'):
            while (r, c) in grid:
                c += 1
            value = normalize(cell.text_content())
            for dr in range(int(cell.get('rowspan', '1'))):
                for dc in range(int(cell.get('colspan', '1'))):
                    grid[r + dr, c + dc] = value
            c += int(cell.get('colspan', '1'))
    if not grid:
        return []
    return [[grid.get((r, c), '') for c in range(max(c for _, c in grid) + 1)]
            for r in range(max(r for r, _ in grid) + 1)]

def mineru(path):
    data = json.loads(path.read_text())
    result = []
    for p in data['pages']:
        output = {'blocks': [], 'rows': []}
        def walk(block, output=output):
            if block.get('type') in {'header', 'footer', 'page_number'}:
                return
            content = block.get('content', '')
            if block.get('type') == 'table_body':
                rows = table_rows(content)
                output['rows'].extend(rows)
                output['blocks'].append(''.join(''.join(row) for row in rows))
            elif isinstance(content, str):
                if content:
                    output['blocks'].append(normalize(content))
            elif content and all(c.get('type') in {'text', 'inline_equation'} for c in content):
                output['blocks'].append(normalize(''.join(c.get('content', '') for c in content)))
            else:
                for child in content:
                    walk(child)
        for block in p['blocks']:
            walk(block)
        result.append(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", choices=["docbridge", "docling", "mineru"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    readers = {"docbridge": docbridge, "docling": docling, "mineru": mineru}
    gold = json.loads((ROOT / "docs/PDF_PARSER_GOLD.json").read_text())["cases"]
    loaded, results = {}, []
    for case in gold:
        name = case["document"]
        if name not in loaded:
            path = args.directory / (name + ".json")
            if args.engine == "docbridge":
                path = args.directory / name / "document.json"
            loaded[name] = readers[args.engine](path)
        results.append({"id": case["id"], "passed": check(case, loaded[name][case["page"] - 1])})
    report = {"engine": args.engine, "passed": sum(r["passed"] for r in results),
              "total": len(results), "cases": results}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
