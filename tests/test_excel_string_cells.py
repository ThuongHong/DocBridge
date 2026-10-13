import zipfile

from lxml import etree

from converter.office import NS, q, read_office, write_office


def typed_string_fixture(source, target):
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(target, "w") as after:
        for entry in before.infolist():
            data = before.read(entry.filename)
            if entry.filename == "xl/worksheets/sheet1.xml":
                root = etree.fromstring(data)
                for address, text in [("A1", "控制器"), ("A2", "传感器")]:
                    cell = root.find(f".//s:c[@r='{address}']", NS)
                    cell.set("t", "str")
                    cell.find("s:v", NS).text = text
                row = root.find("s:sheetData/s:row[@r='2']", NS)
                formula = etree.SubElement(row, q("s", "c"), r="C2", t="str")
                etree.SubElement(formula, q("s", "f")).text = 'IF(B1>0,"正常","故障")'
                etree.SubElement(formula, q("s", "v")).text = "正常"
                blank = etree.SubElement(row, q("s", "c"), r="D2", t="str")
                etree.SubElement(blank, q("s", "v")).text = ""
                root.find("s:dimension", NS).set("ref", "A1:D2")
                data = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
            after.writestr(entry, data)


def test_direct_string_values_are_extracted_but_formula_caches_are_not(spreadsheet, tmp_path):
    source = tmp_path / "direct-values.xlsx"
    typed_string_fixture(spreadsheet, source)
    doc = read_office(source, tmp_path / "assets")
    cells = {s.anchor.get("cell"): s for s in doc.segments if "cell" in s.anchor}
    assert cells["A1"].source == "控制器"
    assert cells["A2"].source == "传感器"
    assert "C2" not in cells
    assert cells["D2"].source == cells["D2"].target == ""


def test_direct_strings_patch_original_values_and_keep_other_parts(spreadsheet, tmp_path):
    source = tmp_path / "direct-values.xlsx"
    typed_string_fixture(spreadsheet, source)
    doc = read_office(source, tmp_path / "assets")
    for segment in doc.segments:
        segment.target = {"A1": " Controller ", "A2": "Sensor"}.get(
            segment.anchor.get("cell"), segment.source
        )
    output = tmp_path / "translated.xlsx"
    write_office(doc, output)
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
        assert set(before.namelist()) == set(after.namelist())
        for name in before.namelist():
            if name != "xl/worksheets/sheet1.xml":
                assert before.read(name) == after.read(name)
        original = etree.fromstring(before.read("xl/worksheets/sheet1.xml"))
        translated = etree.fromstring(after.read("xl/worksheets/sheet1.xml"))
        for address, text in [("A1", " Controller "), ("A2", "Sensor")]:
            cell = translated.find(f".//s:c[@r='{address}']", NS)
            assert cell.get("t") == "str"
            assert cell.find("s:v", NS).text == text
            assert cell.find("s:is", NS) is None
        for address in ["B1", "B2", "C2", "D2"]:
            assert etree.tostring(original.find(f".//s:c[@r='{address}']", NS)) == etree.tostring(
                translated.find(f".//s:c[@r='{address}']", NS)
            )


def test_long_ascii_direct_strings_remain_verbatim_through_argos_pipeline(
    spreadsheet, store, tmp_path
):
    from converter.pipeline import Pipeline
    from converter.providers import ArgosProvider

    intermediate, source = tmp_path / "direct.xlsx", tmp_path / "long.xlsx"
    typed_string_fixture(spreadsheet, intermediate)
    payload = "CAN_DIAGNOSTIC_" + "A" * 3000
    with zipfile.ZipFile(intermediate) as before, zipfile.ZipFile(source, "w") as after:
        for entry in before.infolist():
            data = before.read(entry.filename)
            if entry.filename == "xl/worksheets/sheet1.xml":
                root = etree.fromstring(data)
                root.find(".//s:c[@r='A1']/s:v", NS).text = payload
                data = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
            after.writestr(entry, data)

    class LocalTranslation:
        def translate(self, text):
            return "English"

    provider = ArgosProvider()
    provider.translation = LocalTranslation()
    job = store.add(source)
    doc = Pipeline(store).translate(job, provider, {}, "eng")
    assert next(s for s in doc.segments if s.anchor.get("cell") == "A1").target == payload
