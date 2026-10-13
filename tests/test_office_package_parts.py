import zipfile

import pytest

from converter.markdown import render_markdown
from converter.office import read_office, write_office


@pytest.mark.parametrize("fixture,renames", [
    ("word_file", {"word/document.xml":"word/manual.xml",
                   "word/header1.xml":"word/title-header.xml", "word/footer1.xml":"word/page-footer.xml"}),
    ("slides_file", {"ppt/presentation.xml":"ppt/deck.xml"}),
    ("spreadsheet", {"xl/workbook.xml":"xl/book.xml", "xl/sharedStrings.xml":"xl/text-pool.xml"}),
])
def test_office_discovers_parts_through_package_relationships(request, tmp_path, fixture, renames):
    original = request.getfixturevalue(fixture)
    source = tmp_path / ("custom" + original.suffix)
    mapping = dict(renames)
    for old, new in renames.items():
        old_dir, old_name = old.rsplit("/", 1)
        new_dir, new_name = new.rsplit("/", 1)
        mapping[f"{old_dir}/_rels/{old_name}.rels"] = f"{new_dir}/_rels/{new_name}.rels"
    with zipfile.ZipFile(original) as before, zipfile.ZipFile(source, "w") as after:
        for entry in before.infolist():
            name, data = mapping.get(entry.filename, entry.filename), before.read(entry.filename)
            if entry.filename.endswith((".xml", ".rels")):
                for old, new in renames.items():
                    data = data.replace(old.encode(), new.encode())
                    data = data.replace(old.rsplit("/",1)[1].encode(), new.rsplit("/",1)[1].encode())
            after.writestr(name, data)
    expected = read_office(original, tmp_path / "original-assets")
    doc = read_office(source, tmp_path / "assets")
    assert sorted(s.source for s in doc.segments) == sorted(s.source for s in expected.segments)
    assert render_markdown(doc, "assets", source=True) == render_markdown(expected, "assets", source=True)
    for segment in doc.segments:
        segment.target = "English " + segment.source
    output = tmp_path / ("out" + original.suffix)
    write_office(doc, output)
    extracted = read_office(output, tmp_path / "result-assets")
    assert sorted(s.source for s in extracted.segments) == sorted(s.text for s in doc.segments)
