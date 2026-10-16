from pathlib import Path

import xlsxwriter

from converter.office import read_office, write_office

root = Path(__file__).resolve().parent.parent / ".test-data" / "excel-improvements"
root.mkdir(parents=True, exist_ok=True)
source = root / "reference-source.xlsx"
book = xlsxwriter.Workbook(source)
a = book.add_worksheet("数据一")
b = book.add_worksheet("数据二")
c = book.add_worksheet("汇总")
a.write("A1", "控制器")
a.write("B1", 9)
b.write("A1", "传感器")
b.write("B1", 4)
book.define_name("Total", "='数据一'!$B$1")
c.write_formula("A1", "=SUM('数据一:数据二'!B1)", None, 13)
c.write_formula("A2", "='数据一'!B1+'数据二'!B1", None, 13)
c.write_formula("A3", "=Total*2", None, 18)
c.write_formula("A4", '=SUMIF(数据一!A1,"控制器",数据一!B1)', None, 9)
c.write_formula("A5", '=HYPERLINK("#\'数据一\'!A1","Jump")', None, "Jump")
c.write_formula("A6", '="数据一!B1"', None, "数据一!B1")
book.close()
doc = read_office(source, root / "reference-assets")
for s in doc.segments:
    s.target = {
        "数据一": "Bob's data",
        "数据二": "Second data",
        "汇总": "Summary",
        "控制器": "Controller",
        "传感器": "Sensor",
    }.get(s.source, s.source)
write_office(doc, root / "reference-output.xlsx")
print("cross-sheet fixture exported", len(doc.segments))
