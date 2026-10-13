import pytest
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from converter.markdown import render_markdown
from converter.models import Document, Segment
from converter.pdf import PDF_ADAPTER_VERSION, read_pdf, write_pdf_docx
from converter.pipeline import Pipeline


def test_book_lines_form_paragraphs_and_keep_chinese_words_and_context(tmp_path):
    source = tmp_path / "book.pdf"
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    pdf = canvas.Canvas(str(source), pagesize=(420, 595))
    pdf.setFont("STSong-Light", 20)
    pdf.drawString(48, 550, "汽车电子系统")
    pdf.setFont("STSong-Light", 14)
    pdf.drawString(48, 500, "防抱死制动系统可以防止")
    pdf.drawString(48, 484, "车轮抱死。")
    pdf.drawString(48, 440, "请检查控制器的工作状态。")
    pdf.save()
    doc = read_pdf(source, tmp_path / "assets")
    sources = [segment.source for segment in doc.segments]
    assert "防抱死制动系统可以防止车轮抱死。" in sources
    assert "请检查控制器的工作状态。" in sources
    paragraph = next(s for s in doc.segments if "车轮抱死" in s.source)
    assert len(paragraph.anchor["line_bboxes"]) == 2
    assert "汽车电子系统" in paragraph.context
    assert "请检查控制器" in paragraph.context
    assert doc.adapter_version == PDF_ADAPTER_VERSION
    markdown = render_markdown(doc, "assets", source=True)
    assert "## 汽车电子系统" in markdown
    assert "防抱死制动系统可以防止车轮抱死。" in markdown


def test_pdf_docx_retains_page_sizes_fonts_image_size_and_real_content(
    tmp_path, image, monkeypatch
):
    from docx import Document
    from docx.enum.section import WD_ORIENT

    monkeypatch.setattr("converter.pdf.ocr_image", lambda *args: [])
    source = tmp_path / "layout.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(420, 595))
    pdf.setFillColorRGB(0.2, 0.3, 0.4)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(48, 545, "Technical manual")
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(48, 505, "Voltage must be 12 V.")
    pdf.drawImage(str(image), 48, 400, width=100, height=40)
    pdf.showPage()
    pdf.setPageSize((595, 420))
    pdf.setFont("Times-Italic", 11)
    pdf.drawString(42, 360, "Pressure must be 100 kPa.")
    pdf.save()
    doc = read_pdf(source, tmp_path / "assets", language="eng")
    for segment in doc.segments:
        segment.target = segment.source
    output = tmp_path / "layout.docx"
    write_pdf_docx(doc, output)
    word = Document(output)
    assert [(round(s.page_width.pt), round(s.page_height.pt)) for s in word.sections] == [
        (420, 595), (595, 420)
    ]
    assert word.sections[1].orientation == WD_ORIENT.LANDSCAPE
    assert all(p.text not in {"Page 1", "Page 2"} for p in word.paragraphs)
    heading = next(p for p in word.paragraphs if p.text == "Technical manual")
    assert heading.runs[0].bold
    assert heading.runs[0].font.size.pt == 20
    assert str(heading.runs[0].font.color.rgb) == "334C66"
    italic = next(p for p in word.paragraphs if "Pressure" in p.text)
    assert italic.runs[0].italic
    assert italic.runs[0].font.size.pt == 11
    assert word.inline_shapes[0].width.pt == 100
    assert word.inline_shapes[0].height.pt == 40


def test_tightly_spaced_columns_do_not_merge_into_each_other(tmp_path):
    source = tmp_path / "columns.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(612, 792))
    for index in range(3):
        pdf.drawString(48, 700 - index * 14, f"Left column line {index}")
        pdf.drawString(350, 700 - index * 14, f"Right column line {index}")
    pdf.save()
    doc = read_pdf(source, tmp_path / "assets")
    assert all(not ("Left" in s.source and "Right" in s.source) for s in doc.segments)
    markdown = render_markdown(doc, "assets", source=True)
    assert markdown.index("Left column line 2") < markdown.index("Right column line 0")
    for segment in doc.segments:
        segment.target = segment.source
    output = tmp_path / "columns.docx"
    write_pdf_docx(doc, output)
    from docx import Document as WordDocument
    word = WordDocument(output)
    assert len(word.tables) == 1
    table = word.tables[0]
    assert "Left column line 2" in table.cell(0, 0).text
    assert not table.cell(0, 1).text
    assert "Right column line 0" in table.cell(0, 2).text
    assert all("Right" not in p.text for p in table.cell(0, 0).paragraphs)
    assert all("Left" not in p.text for p in table.cell(0, 2).paragraphs)


def test_full_width_heading_and_footer_bound_column_bands(tmp_path):
    from docx import Document as WordDocument
    source = tmp_path / "bands.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(612, 792))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(48, 740, "Full width technical document heading")
    pdf.setFont("Helvetica", 12)
    for index in range(3):
        pdf.drawString(48, 700 - index * 14, f"Left column paragraph {index}")
        pdf.drawString(350, 700 - index * 14, f"Right column paragraph {index}")
    pdf.drawString(48, 600, "Full width concluding note across the two document columns.")
    pdf.save()
    doc = read_pdf(source, tmp_path / "assets")
    for segment in doc.segments:
        segment.target = segment.source
    output = tmp_path / "bands.docx"
    write_pdf_docx(doc, output)
    word = WordDocument(output)
    assert word.paragraphs[0].text == "Full width technical document heading"
    assert word.paragraphs[-1].text.startswith("Full width concluding note")
    assert len(word.tables) == 1
    assert "Left column" in word.tables[0].cell(0, 0).text
    assert "Right column" in word.tables[0].cell(0, 2).text


def test_merging_on_first_page_keeps_ids_and_translations_separate(tmp_path, store):
    source = tmp_path / "multipage.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(420, 595))
    pdf.drawString(48, 500, "First paragraph continues")
    pdf.drawString(48, 486, "onto another line.")
    pdf.drawString(48, 420, "Figure caption")
    pdf.showPage()
    pdf.drawString(48, 500, "Second page title")
    pdf.save()

    class ReferenceProvider:
        batch_chars = 6000
        handles_long_segments = True
        def fingerprint(self, glossary):
            return "layout-reference"
        def translate(self, segments, glossary):
            return {s.id: "Verified " + s.source for s in segments}

    job = store.add(source)
    Pipeline(store).run(job, ReferenceProvider(), "markdown", tmp_path / "out", ocr_language="eng")
    doc = store.load_document(job)
    assert len({s.id for s in doc.segments}) == len(doc.segments)
    assert len(doc.segments) == 3
    assert all(s.target == "Verified " + s.source for s in doc.segments)


def test_duplicate_ids_fail_before_content_can_be_mapped_to_the_wrong_segment():
    doc = Document("source.pdf", "hash", "pdf", segments=[
        Segment("s000000", "First page"), Segment("s000000", "Second page"),
    ])
    with pytest.raises(ValueError, match="IDs"):
        doc.by_id()


def test_ocr_paragraph_ids_prevent_merging_separate_paragraphs(tmp_path, image, monkeypatch):
    source = tmp_path / "scan.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(420, 595))
    pdf.drawImage(str(image), 0, 0, width=420, height=595)
    pdf.save()
    monkeypatch.setattr("converter.pdf.configure_tesseract", lambda: "")
    monkeypatch.setattr("converter.pdf.ocr_image", lambda *args: [
        {"text": "防抱死制动系统可以防止", "bbox": [144, 180, 1200, 222],
         "confidence": 90, "paragraph": [1, 1]},
        {"text": "车轮抱死。", "bbox": [144, 228, 1200, 270],
         "confidence": 55, "paragraph": [1, 1]},
        {"text": "请检查控制器。", "bbox": [144, 276, 1200, 318],
         "confidence": 95, "paragraph": [1, 2]},
    ])
    doc = read_pdf(source, tmp_path / "assets")
    assert len(doc.segments) == 2
    assert doc.segments[0].source == "防抱死制动系统可以防止车轮抱死。"
    assert "55%" in doc.segments[0].warning
    assert doc.segments[1].source == "请检查控制器。"


def test_changed_pdf_adapter_rejects_resume_but_keeps_existing_exports(text_pdf, store, tmp_path):
    job = store.add(text_pdf)
    pipeline = Pipeline(store)
    pipeline.run(job, None, "markdown", tmp_path / "out", operation="convert", ocr_language="eng")
    doc = store.load_document(job)
    doc.adapter_version = 1
    store.save_document(job, doc)
    with pytest.raises(ValueError, match="adapter"):
        pipeline.parse(job, "eng")
    result = pipeline.run(
        job, None, "markdown", tmp_path / "out", operation="convert", export_only=True
    )
    assert result["markdown"]["status"] == "done"
