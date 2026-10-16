"""Conservative readable XLSX layout using worker-safe Pillow/FreeType metrics.

Column pixels follow ISO/IEC 29500's maximum-digit-width formula documented at
https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.column
The result estimates fit; native spreadsheet font substitution/printing can differ.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
from collections import OrderedDict
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from .excel_text import display_nodes
from .office import NS, column_index, q, rels, spreadsheet_parts, xml


@lru_cache(maxsize=256)
def font_metrics(family, size, bold=False, italic=False):
    pixels = max(1, round(float(size) * 96 / 72))
    filename = None
    if shutil.which('fc-match'):
        pattern = family + (':weight=bold' if bold else '') + (':slant=italic' if italic else '')
        try:
            filename = subprocess.run(['fc-match', '-f', '%{file}', pattern], capture_output=True,
                                      text=True, timeout=5, check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    candidates = [filename] if filename else []
    # Pillow searches the Windows fonts directory for TrueType filenames.
    basename = {'arial': 'arial', 'calibri': 'calibri', 'times new roman': 'times',
                'courier new': 'cour'}.get(family.casefold(), family.replace(' ', ''))
    if family.casefold() == 'calibri':
        suffix = 'z' if bold and italic else 'b' if bold else 'i' if italic else ''
    else:
        suffix = 'bi' if bold and italic else 'bd' if bold else 'i' if italic else ''
    candidates.extend([basename + suffix + '.ttf', family + '.ttf', 'DejaVuSans.ttf'])
    system_fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    candidates.extend(str(system_fonts / name) for name in list(candidates) if name)
    for candidate in candidates:
        if not candidate:
            continue
        try:
            font = ImageFont.truetype(candidate, pixels)
            actual, face = font.getname()
            face = face.casefold()
            actual_bold = any(value in face for value in ('bold', 'black', 'heavy'))
            actual_italic = 'italic' in face or 'oblique' in face
            substituted = (actual.casefold() != family.casefold()
                           or actual_bold != bold or actual_italic != italic)
            return font, substituted, actual + (' ' + face if bold or italic else '')
        except OSError:
            continue
    font = ImageFont.load_default(size=pixels)
    return font, True, font.getname()[0]


def font_spec(node, base=('Calibri', 11.0, False, False)):
    family, size, bold, italic = base
    if node is not None:
        name = node.find('s:name', NS)
        if name is None:
            name = node.find('s:rFont', NS)
        if name is not None:
            family = name.get('val', family)
        point = node.find('s:sz', NS)
        if point is not None:
            size = float(point.get('val', size))
        for attr in ('b', 'i'):
            value = node.find(f's:{attr}', NS)
            if value is not None:
                enabled = value.get('val', '1') not in {'0', 'false', 'off'}
                if attr == 'b':
                    bold = enabled
                else:
                    italic = enabled
    return family, size, bold, italic


def measured_height(text, width, specs):
    fonts = [font_metrics(*spec)[0] for spec in specs]
    # Envelope metrics retain mixed run styles and safely account for their
    # widest words/largest line box without flattening or changing any run.
    def advance(value):
        return max(font.getlength(value) for font in fonts)

    lines = 0
    for paragraph in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        current = 0.0
        for word in re.findall(r'\S+\s*|\s+', paragraph):
            word_width = advance(word)
            if current and current + advance(word.rstrip()) > width:
                lines += 1
                current = 0.0
            if word_width <= width:
                current += word_width
                continue
            # Long unbroken labels wrap at characters without repeatedly
            # measuring an ever-growing string (bounded work per character).
            for char in word:
                char_width = advance(char)
                if current and current + char_width > width:
                    lines += 1
                    current = 0.0
                current += char_width
        lines += 1
    line_pixels = max(sum(font.getmetrics()) for font in fonts)
    return math.ceil(lines * line_pixels * .75 * 1.12 + 3)


def readable_layout(archive, roots, cell_groups, cell_indexes):
    report = {'mode': 'readable', 'changed_text_cells': len(cell_groups), 'wrapped_cells': 0,
              'increased_rows': 0, 'reduced_font_cells': 0, 'print_fit_sheets': 0, 'issues': {},
              'limitations': ['Measured with available font metrics; native Excel/LibreOffice printing may differ.',
                              'Column widths, hidden rows/columns, formulas, values and merged ranges are preserved.',
                              'Row growth can change pagination and printed page counts.']}

    def issue(kind, location):
        item = report['issues'].setdefault(kind, {'count': 0, 'examples': []})
        item['count'] += 1
        if len(item['examples']) < 5:
            item['examples'].append(location)

    if not cell_groups:
        return report
    workbook_part, shared_part = spreadsheet_parts(archive)
    style_part = next((target for target, kind, external in rels(archive, workbook_part).values()
                       if kind.endswith('/styles') and not external), None)
    if style_part is None:
        issue('missing_styles', workbook_part)
        return report
    styles = roots.get(style_part)
    if styles is None:
        styles = xml(archive.read(style_part))
    fonts = styles.find('s:fonts', NS)
    xfs = styles.find('s:cellXfs', NS)
    if fonts is None or xfs is None:
        issue('missing_styles', style_part)
        return report
    base_specs = [font_spec(font) for font in fonts]
    normal = base_specs[0] if base_specs else ('Calibri', 11.0, False, False)
    style_xfs = styles.find('s:cellStyleXfs', NS)
    normal_style = next((item for item in styles.findall('s:cellStyles/s:cellStyle', NS)
                         if item.get('builtinId') == '0' or item.get('name', '').casefold() == 'normal'), None)
    if normal_style is not None and style_xfs is not None:
        index = int(normal_style.get('xfId', '0'))
        if index < len(style_xfs):
            normal = base_specs[int(style_xfs[index].get('fontId', '0'))]
    normal_font, normal_fallback, normal_actual = font_metrics(*normal)
    digit_width = max(normal_font.getlength(str(value)) for value in range(10))
    print_digit_width = digit_width
    if normal_fallback:
        issue('normal_font_substitution', normal[0] + ' → ' + normal_actual)
        if normal[0].casefold() == 'calibri':
            # The documented Calibri11 normal-style digit width is7px. An
            # unavailable replacement with wider digits must not enlarge the
            # assumed existing columns and underestimate wrapping.
            digit_width = 7 * normal[1] / 11
    shared = roots.get(shared_part) if shared_part else None
    if shared is None and shared_part:
        shared = xml(archive.read(shared_part))
    clone_styles, reduced_fonts, measurements, content_cache, worksheets = {}, {}, OrderedDict(), {}, {}
    changed_rows = set()
    for (part, address), _segments in cell_groups.items():
        if part not in worksheets:
            root = roots[part]
            sheet_format = root.find('s:sheetFormatPr', NS)
            defaults = dict(sheet_format.attrib) if sheet_format is not None else {}
            rows = {int(row.get('r')): row for row in root.findall('s:sheetData/s:row', NS)}
            columns = root.findall('s:cols/s:col', NS)
            merges = {}
            for merge in root.findall('s:mergeCells/s:mergeCell', NS):
                first, _, last = merge.get('ref').partition(':')
                last = last or first
                merges[first] = (column_index(first), int(re.search(r'\d+', first)[0]),
                                 column_index(last), int(re.search(r'\d+', last)[0]))
            worksheets[part] = root, rows, columns, merges, defaults
        root, rows, columns, merges, defaults = worksheets[part]
        cell = cell_indexes[part][address]
        row_number = int(re.search(r'\d+', address)[0])
        row = rows[row_number]
        if row.get('hidden', defaults.get('zeroHeight', '0')) in {'1', 'true'}:
            issue('hidden_cells_skipped', part + '!' + address)
            continue
        col_number = column_index(address)
        column_style = next((item.get('style') for item in columns
                             if int(item.get('min')) <= col_number <= int(item.get('max'))), None)
        style_index = int(cell.get('s', row.get('s', column_style or '0')))
        original_xf = xfs[style_index]
        custom_formats = styles.find('s:numFmts', NS)
        format_code = next((item.get('formatCode', '') for item in custom_formats
                            if item.get('numFmtId') == original_xf.get('numFmtId')), '') if custom_formats is not None else ''
        if ';' in format_code or ('@' in format_code and format_code.strip() != '@'):
            issue('custom_display_format_not_fitted', part + '!' + address)
            continue
        alignment = original_xf.find('s:alignment', NS)
        if alignment is not None and alignment.get('textRotation', '0') != '0':
            issue('rotated_text_not_fitted', part + '!' + address)
            continue
        if alignment is not None and alignment.get('horizontal') == 'fill':
            issue('special_alignment_not_fitted', part + '!' + address)
            continue
        base = base_specs[int(original_xf.get('fontId', '0'))]
        if cell.get('t') == 's':
            shared_index = int(cell.find('s:v', NS).text)
            cache_key = shared_index, base
            cached = content_cache.get(cache_key)
            if cached is None:
                content = shared[shared_index]
                nodes = display_nodes(content)
                text = ''.join(node.text or '' for node in nodes)
                specs = tuple(dict.fromkeys(font_spec(node.getparent().find('s:rPr', NS), base)
                                           for node in nodes if node.text)) or (base,)
                cached = text, specs, content.find('s:r', NS) is not None
                content_cache[cache_key] = cached
            text, specs, rich = cached
        elif cell.get('t') == 'inlineStr':
            content = cell.find('s:is', NS)
            rich = content.find('s:r', NS) is not None
            nodes = display_nodes(content)
            text = ''.join(node.text or '' for node in nodes)
            specs = tuple(dict.fromkeys(font_spec(node.getparent().find('s:rPr', NS), base)
                                       for node in nodes if node.text)) or (base,)
        else:
            text, specs, rich = cell.find('s:v', NS).text or '', (base,), False
        for spec in specs:
            _, fallback, actual = font_metrics(*spec)
            if fallback:
                issue('font_substitution', part + '!' + address + ': ' + spec[0] + ' → ' + actual)
                break
        left, top, right, bottom = merges.get(address, (col_number, row_number, col_number, row_number))
        if bottom - top > 4096:
            issue('large_vertical_merge_not_fitted', part + '!' + address)
            continue
        width = 0
        for number in range(left, right + 1):
            column = next((item for item in columns
                           if int(item.get('min')) <= number <= int(item.get('max'))), None)
            if column is not None and column.get('hidden') in {'1', 'true'}:
                continue
            units = float(column.get('width', defaults.get('defaultColWidth', '8.43'))
                          if column is not None else defaults.get('defaultColWidth', '8.43'))
            width += math.trunc(((256 * units + math.trunc(128 / digit_width)) / 256) * digit_width)
        indent = int(alignment.get('indent', '0')) if alignment is not None else 0
        width -= 7 + indent * digit_width * 3
        if width <= 1:
            issue('no_visible_width', part + '!' + address)
            continue
        key = text, round(width, 2), specs
        required = measurements.get(key)
        if required is None:
            required = measured_height(text, width, specs)
            measurements[key] = required
            if len(measurements) > 4096:
                measurements.popitem(last=False)
        measurements.move_to_end(key)
        visible_rows = [number for number in range(top, bottom + 1)
                        if (rows[number].get('hidden', defaults.get('zeroHeight', '0')) if number in rows else defaults.get('zeroHeight', '0')) not in {'1', 'true'}]
        heights = {number: float(rows[number].get('ht', defaults.get('defaultRowHeight', '15')))
                   if number in rows else float(defaults.get('defaultRowHeight', '15'))
                   for number in visible_rows}
        font_id = int(original_xf.get('fontId', '0'))
        capacity = 409 * len(visible_rows)
        if required > capacity and not rich and base[1] > 9:
            size = base[1]
            while size > 9 and required > capacity:
                size = max(9, size - .5)
                reduced_specs = ((base[0], size, base[2], base[3]),)
                reduced_key = text, round(width, 2), reduced_specs
                required = measurements.get(reduced_key)
                if required is None:
                    required = measured_height(text, width, reduced_specs)
                    measurements[reduced_key] = required
                    if len(measurements) > 4096:
                        measurements.popitem(last=False)
            font_key = font_id, size
            if font_key not in reduced_fonts:
                clone_font = deepcopy(fonts[font_id])
                point = clone_font.find('s:sz', NS)
                if point is None:
                    point = etree_element('sz')
                    clone_font.append(point)
                point.set('val', str(size))
                reduced_fonts[font_key] = len(fonts)
                fonts.append(clone_font)
            font_id = reduced_fonts[font_key]
            report['reduced_font_cells'] += 1
            issue('font_reduced', part + '!' + address + f': {base[1]:g}pt → {size:g}pt')
        elif required > capacity and rich:
            issue('rich_text_height_cap_not_scaled', part + '!' + address)
        style_key = style_index, font_id
        if style_key not in clone_styles:
            if len(xfs) >= 65490:
                issue('cell_style_limit_not_fitted', part + '!' + address)
                continue
            clone = deepcopy(original_xf)
            clone.set('fontId', str(font_id))
            clone.set('applyFont', '1')
            align = clone.find('s:alignment', NS)
            if align is None:
                align = etree_element('alignment')
                # alignment precedes protection/extLst in CT_Xf.
                position = next((i for i, child in enumerate(clone)
                                 if child.tag in {q('s', 'protection'), q('s', 'extLst')}), len(clone))
                clone.insert(position, align)
            align.set('wrapText', '1')
            align.set('shrinkToFit', '0')
            clone.set('applyAlignment', '1')
            clone_styles[style_key] = len(xfs)
            xfs.append(clone)
        cell.set('s', str(clone_styles[style_key]))
        report['wrapped_cells'] += 1
        remaining = max(0, required - sum(heights.values()))
        # Distribute extra height over visible vertical-merge rows, honoring the
        # per-row Excel cap. Nothing is inserted/deleted or made visible.
        while remaining > .01:
            available = [number for number in visible_rows if heights[number] < 409]
            if not available:
                issue('row_height_cap_unresolved', part + '!' + address)
                break
            addition = remaining / len(available)
            for number in available:
                increase = min(addition, 409 - heights[number])
                heights[number] += increase
                remaining -= increase
        for number, height in heights.items():
            old = float(rows[number].get('ht', defaults.get('defaultRowHeight', '15'))) if number in rows else float(defaults.get('defaultRowHeight', '15'))
            if height <= old + .01:
                continue
            if number not in rows:
                new_row = etree_element('row', r=str(number))
                data = root.find('s:sheetData', NS)
                following = next((item for item in data if int(item.get('r')) > number), None)
                if following is None:
                    data.append(new_row)
                else:
                    following.addprevious(new_row)
                rows[number] = new_row
            rows[number].set('ht', f'{height:.2f}')
            rows[number].set('customHeight', '1')
            changed_rows.add((part, number))
    # Fit only sheets whose printed logical width exceeds the selected paper.
    # Keep height unlimited so readability is not traded for a single tall page.
    workbook = roots.get(workbook_part)
    if workbook is None:
        workbook = xml(archive.read(workbook_part))
    book_relationships = rels(archive, workbook_part)
    for sheet_index, sheet in enumerate(workbook.findall('s:sheets/s:sheet', NS)):
        part = book_relationships[sheet.get(q('r', 'id'))][0]
        if part not in worksheets:
            continue
        root, _, columns, _, defaults = worksheets[part]
        setup = root.find('s:pageSetup', NS)
        sizes = {'1': (8.5, 11), '5': (8.5, 14), '8': (11.69, 16.54),
                 '9': (8.27, 11.69), '11': (5.83, 8.27), '13': (7.17, 10.12)}
        paper = sizes.get(setup.get('paperSize', '1') if setup is not None else '1')
        if paper is None:
            issue('print_width_not_checked', part)
            continue
        paper_width = paper[1] if setup is not None and setup.get('orientation') == 'landscape' else paper[0]
        margins = root.find('s:pageMargins', NS)
        left_margin = float(margins.get('left', '.75')) if margins is not None else .75
        right_margin = float(margins.get('right', '.75')) if margins is not None else .75
        printable = max(1, (paper_width - left_margin - right_margin) * 96)
        defined = next((name.text for name in workbook.findall('s:definedNames/s:definedName', NS)
                        if name.get('name') == '_xlnm.Print_Area' and name.get('localSheetId') == str(sheet_index)), None)
        spans = re.findall(r'!\$?([A-Z]+)\$?\d+(?::\$?([A-Z]+)\$?\d+)?', defined or '', re.I)
        if spans:
            first = min(column_index(start + '1') for start, _ in spans)
            last = max(column_index((end or start) + '1') for start, end in spans)
        else:
            dimension = root.find('s:dimension', NS)
            address = dimension.get('ref', 'A1') if dimension is not None else 'A1'
            start, _, end = address.partition(':')
            first, last = column_index(start), column_index(end or start)
        logical = 0
        visible_columns = 0
        for number in range(first, last + 1):
            column = next((item for item in columns if int(item.get('min')) <= number <= int(item.get('max'))), None)
            if column is not None and column.get('hidden') in {'1', 'true'}:
                continue
            visible_columns += 1
            units = float(column.get('width', defaults.get('defaultColWidth', '8.43')) if column is not None else defaults.get('defaultColWidth', '8.43'))
            # Wrapping uses the conservative original width, but a renderer
            # can substitute a wider Normal font and enlarge the whole column.
            # Printing must allow for that wider physical extent.
            print_digit_width = max(print_digit_width, digit_width)
            logical += math.trunc(((256 * units + math.trunc(128 / print_digit_width)) / 256) * print_digit_width)
        if logical <= printable:
            continue
        properties = root.find('s:sheetPr', NS)
        if properties is None:
            properties = etree_element('sheetPr')
            root.insert(0, properties)
        page_properties = properties.find('s:pageSetUpPr', NS)
        if page_properties is None:
            page_properties = etree_element('pageSetUpPr')
            properties.append(page_properties)
        page_properties.set('fitToPage', '1')
        if setup is None:
            setup = etree_element('pageSetup')
            # pageSetup belongs after pageMargins and before headers/breaks/drawings.
            after = root.find('s:pageMargins', NS)
            if after is not None:
                after.addnext(setup)
            else:
                position = next((i for i, child in enumerate(root) if child.tag in {
                    q('s', 'headerFooter'), q('s', 'rowBreaks'), q('s', 'colBreaks'),
                    q('s', 'drawing'), q('s', 'legacyDrawing'), q('s', 'extLst')}), len(root))
                root.insert(position, setup)
        setup.attrib.pop('scale', None)
        setup.set('fitToWidth', '1')
        setup.set('fitToHeight', '0')
        report['print_fit_sheets'] += 1
        if visible_columns == 1:
            # LibreOffice imports fitToWidth but does not shrink a single
            # oversized column. Use an explicit percentage for this case.
            # Leave a small allowance for rounding and substituted metrics.
            scale = max(10, min(100, math.floor(98 * printable / logical)))
            page_properties.set('fitToPage', '0')
            setup.set('scale', str(scale))
            issue('print_single_column_scale', part + f': {scale}% for {logical:g}px content / {printable:.0f}px paper width')
            if logical * scale / 100 > printable:
                issue('print_scale_limit_unresolved', part)
        else:
            issue('print_fit_one_page_wide', part + f': {logical:g}px content / {printable:.0f}px paper width; unlimited height')
    if reduced_fonts:
        fonts.set('count', str(len(fonts)))
    if clone_styles:
        xfs.set('count', str(len(xfs)))
        roots[style_part] = styles
    report['increased_rows'] = len(changed_rows)
    return report


def etree_element(name, **attrs):
    from lxml import etree

    return etree.Element(q('s', name), **attrs)
