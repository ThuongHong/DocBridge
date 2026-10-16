"""Bounded residual-Han audit of exported XLSX packages (no OCR)."""
from __future__ import annotations

import io
import zipfile
from collections import defaultdict

from lxml import etree

from .excel_text import display_nodes, header_literals, literal_list
from .office import NS, rels, spreadsheet_parts, xml
from .providers import HAN


def audit_excel(path):
    categories = defaultdict(lambda: {"count": 0, "examples": []})
    images = 0

    def record(category, location, text):
        if not HAN.search(text or ''):
            return
        item = categories[category]
        item['count'] += 1
        if len(item['examples']) < 5:
            item['examples'].append({"location": location, "text": text[:160]})

    def package(archive, prefix=''):
        nonlocal images
        workbook_part, shared_part = spreadsheet_parts(archive)
        shared = ["".join(t.text or '' for t in display_nodes(item))
                  for item in xml(archive.read(shared_part))] if shared_part else []
        workbook = xml(archive.read(workbook_part))
        relationships = rels(archive, workbook_part)
        sheet_parts = set()
        for sheet in workbook.findall('s:sheets/s:sheet', NS):
            title = sheet.get('name', '')
            record('translatable_sheet_title', prefix + title, title)
            part = relationships[sheet.get('{'+NS['r']+'}id')][0]
            sheet_parts.add(part)
            # Stream worksheets so the audit does not allocate another million-cell tree.
            with archive.open(part) as stream:
                for _, node in etree.iterparse(stream, events=('end',), resolve_entities=False,
                                               no_network=True):
                    local = etree.QName(node).localname
                    for attr in ('promptTitle', 'prompt', 'errorTitle', 'error', 'tooltip', 'display', 'descr', 'title'):
                        record('unsupported_user_visible_attribute', prefix + title + ':' + local + '@' + attr,
                               node.get(attr))
                    if local == 'c' and etree.QName(node).namespace == NS['s']:
                        location = prefix + title + '!' + node.get('r', '?')
                        formula, value = node.find('s:f', NS), node.find('s:v', NS)
                        if formula is not None:
                            record('preserved_formula', location, formula.text)
                            if node.get('t') == 'str' and value is not None:
                                record('preserved_display_cache', location, value.text)
                        elif node.get('t') == 's' and value is not None:
                            record('translatable_cell', location, shared[int(value.text)])
                        elif node.get('t') == 'inlineStr':
                            content = node.find('s:is', NS)
                            record('translatable_cell', location,
                                   ''.join(t.text or '' for t in display_nodes(content)) if content is not None else '')
                        elif node.get('t') == 'str' and value is not None:
                            record('translatable_cell', location, value.text)
                        node.clear()
                        while node.getprevious() is not None:
                            del node.getparent()[0]
                    elif local in {'oddHeader', 'oddFooter', 'evenHeader', 'evenFooter', 'firstHeader', 'firstFooter'}:
                        for _, _, text in header_literals(node.text or ''):
                            record('translatable_header_footer', prefix + title + ':' + local, text)
                        node.clear()
                    elif local in {'formula', 'formula1', 'formula2'}:
                        options = literal_list(node.text) if local == 'formula1' and node.getparent().get('type') == 'list' else None
                        if options is not None:
                            for index, option in enumerate(options):
                                record('translatable_dropdown_option', prefix + title + ':dropdown:' + str(index), option)
                        else:
                            record('preserved_formula', prefix + title + ':' + local, node.text)
                    elif local == 'row':
                        node.clear()
                        while node.getprevious() is not None:
                            del node.getparent()[0]
        for part in archive.namelist():
            if '/media/' in part:
                images += 1
            if part.endswith('.xlsx'):
                with zipfile.ZipFile(io.BytesIO(archive.read(part))) as embedded:
                    package(embedded, prefix + part + ':')
            if part in sheet_parts or part == shared_part or not part.endswith(('.xml', '.vml')):
                continue
            root = xml(archive.read(part))
            for node in root.iter():
                if not isinstance(node.tag, str):
                    continue
                local = etree.QName(node).localname
                location = prefix + part + ':' + local
                if local in {'f', 'definedName', 'calculatedColumnFormula', 'totalsRowFormula'}:
                    record('preserved_formula', location, node.text)
                elif local == 'author':
                    record('preserved_metadata', location, node.text)
                elif local == 't' or (local == 'text' and not len(node)):
                    category = 'translatable_comment' if 'comment' in part.lower() else 'other_visible_text'
                    record(category, location, node.text)
                elif local == 'v' and '/charts/' in part:
                    record('other_visible_text', location, node.text)
                elif local == 'numFmt':
                    record('preserved_format_code', location + '@formatCode', node.get('formatCode'))
                else:
                    category = 'preserved_metadata' if part.startswith('docProps/') else 'other_detectable_text'
                    record(category, location, node.text)
                record('other_detectable_text', location + ':tail', node.tail)
                # Names, IDs, formulas and relation targets are metadata/code. Alt text
                # and shape titles are visible accessibility content and need review.
                for attr in ('descr', 'title'):
                    record('unsupported_accessibility_text', location + '@' + attr, node.get(attr))
    with zipfile.ZipFile(path) as archive:
        package(archive)
    return {"han_locations": dict(sorted(categories.items())), "images_not_ocr_scanned": images,
            "limitations": ['Images are not OCR-scanned; runtime formula results require Excel recalculation.',
                            'Counts cover detectable OOXML text locations, not rendered pixels.']}


def coverage_warning(report):
    counts = ', '.join(f'{name}={item["count"]}' for name, item in report['han_locations'].items())
    return 'Excel coverage: ' + (counts or 'no residual Han in detectable OOXML text') + (
        f'; {report["images_not_ocr_scanned"]} image(s) not OCR-scanned.'
        if report['images_not_ocr_scanned'] else '; formula display requires recalculation.')


def audit_markdown(doc, text):
    """Report residual extracted text and literal formulas in the Markdown view."""
    categories = defaultdict(lambda: {"count": 0, "examples": []})

    def record(category, location, value):
        if not HAN.search(value or ''):
            return
        item = categories[category]
        item['count'] += 1
        if len(item['examples']) < 5:
            item['examples'].append({'location': location, 'text': value[:160]})

    for segment in doc.segments:
        anchor = segment.anchor
        category = anchor.get('category', 'cell' if 'cell' in anchor else 'other_visible_text')
        if category != 'other_visible_text':
            category = 'translatable_' + category
        location = anchor.get('sheet', anchor.get('part', '')) + ':' + anchor.get('cell', segment.id)
        record(category, location, segment.text)

    def blocks(items):
        for block in items:
            value = block.meta.get('literal', '')
            record('preserved_formula' if str(value).startswith('=') else 'other_visible_text',
                   block.meta.get('address', block.kind), str(value))
            for address, _, literal in block.meta.get('entries', []):
                record('preserved_formula' if str(literal).startswith('=') else 'other_visible_text',
                       address, str(literal))
            blocks(block.children)
    blocks(doc.blocks)
    return {'han_locations': dict(sorted(categories.items())),
            'rendered_han_characters': len(HAN.findall(text)),
            'images_not_ocr_scanned': len(doc.assets),
            'limitations': ['Markdown reports extracted text and formulas; images are not OCR-scanned.']}
