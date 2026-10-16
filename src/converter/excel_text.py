"""OOXML spreadsheet display text and lexical sheet-reference updates."""
from __future__ import annotations

import re

from lxml import etree

from .office import NS, q

# A header/footer control is never sent to a translator. Font names can be Han.
HEADER_CONTROL = re.compile(r'&(?:"[^"]*"|\[[^\]]*\]|K(?:[0-9A-Fa-f]{6}|[0-9]{2}[+-][0-9]{3})|\d+|[PN](?:[+-]\d+)?|[A-Za-z&])', re.S)
STRING = re.compile(r'"(?:[^"]|"")*"')
SHEET_ENDPOINT = r"(?:'(?:[^']|'')+'|(?:\[[^\]]+\])?[\w.\\]+)"
SHEET_REF = re.compile(r"(?<![\w.\]'])" + SHEET_ENDPOINT + r"(?::" + SHEET_ENDPOINT + r")?!", re.UNICODE)
FORMULA_LEXEME = re.compile('(?P<reference>' + SHEET_REF.pattern + ')|(?P<string>' + STRING.pattern + ')')



def header_literals(text):
    offset = 0
    for match in HEADER_CONTROL.finditer(text):
        if offset < match.start():
            yield offset, match.start(), text[offset:match.start()]
        offset = match.end()
    if offset < len(text):
        yield offset, len(text), text[offset:]


def display_nodes(content):
    return content.xpath('./s:t | ./s:r/s:t', namespaces=NS)


def run_groups(content):
    groups = []
    for index, text in enumerate(display_nodes(content)):
        run = text.getparent()
        props = run.find('s:rPr', NS)
        key = etree.tostring(props, method='c14n') if props is not None else b''
        style = {}
        if props is not None:
            for attr in ['b', 'i', 'strike']:
                node = props.find(f's:{attr}', NS)
                style[attr] = node is not None and node.get('val', '1') not in {'0', 'false', 'off'}
        if groups and groups[-1][0] == key:
            groups[-1][1].append(index)
            groups[-1][2] += text.text or ''
        else:
            groups.append([key, [index], text.text or '', style])
    return groups


def patch_display(content, segments, set_text):
    legacy = not any('text_indices' in segment.anchor for segment in segments)
    texts = content.findall('.//s:t', NS) if legacy else display_nodes(content)
    for segment in segments:
        for index, position in enumerate(segment.anchor.get('text_indices', [segment.anchor['text_index']])):
            set_text(texts[position], segment.text if index == 0 else '')
    # Phonetic offsets refer to the old characters; retaining them would be misleading.
    if not legacy:
        for node in content.findall('s:rPh', NS) + content.findall('s:phoneticPr', NS):
            content.remove(node)


def literal_list(text):
    """Decode a literal Excel data-validation list, never a range/formula."""
    if not text or not re.fullmatch(r'=?"(?:[^"]|"")*"', text, re.S):
        return None
    quoted = text[1:] if text.startswith('=') else text
    return quoted[1:-1].replace('""', '"').split(',')


def patch_dropdown(node, items, segments, sheet):
    from itertools import groupby

    from openpyxl.utils.cell import range_boundaries

    options = literal_list(node.text)
    if options is None:
        raise ValueError('Excel dropdown mapping changed; re-analyze the workbook.')
    for segment in items:
        options[segment.anchor['option_index']] = segment.text
    if any(',' in value or any(ord(char) < 32 for char in value) for value in options):
        raise ValueError('Excel dropdown options cannot contain commas or control characters. '
                         'Review the translated dropdown options before exporting.')
    joined = ','.join(options)
    if len(joined.replace('"', '""').encode('utf-16-le')) // 2 > 255:
        raise ValueError('Translated Excel inline dropdown exceeds 255 characters. '
                         'Shorten the options in review before exporting.')
    validation = node.getparent()
    bounds = [range_boundaries(item) for item in validation.get('sqref', '').split()]
    sources = {}
    for segment in items:
        if segment.source in sources and sources[segment.source] != segment.text:
            raise ValueError('Duplicate Excel dropdown labels have different translations; '
                             'use the same reviewed label before exporting.')
        sources[segment.source] = segment.text
    selected = {}
    cell_segments = (s for s in segments if 'cell' in s.anchor and s.anchor.get('sheet') == sheet)
    for (_, address), group in groupby(cell_segments, key=lambda s: (s.anchor.get('sheet'), s.anchor['cell'])):
        group = list(group)
        source = ''.join(s.source for s in group)
        if source not in sources:
            continue
        match = re.fullmatch(r'([A-Z]+)(\d+)', address, re.I)
        if match is None:
            continue
        column = 0
        for char in match[1].upper():
            column = column * 26 + ord(char) - 64
        row = int(match[2])
        if any((left or 1) <= column <= (right or 16384)
               and (top or 1) <= row <= (bottom or 1048576) for left, top, right, bottom in bounds):
            selected.setdefault(source, set()).add(''.join(s.text for s in group))
    for source, targets in selected.items():
        if targets != {sources[source]}:
            raise ValueError('Excel dropdown option and validated cells have different translations: '
                             + source[:80] + '. Use the same reviewed label for the option and cells before exporting.')
    node.text = ('=' if (node.text or '').startswith('=') else '') + '"' + joined.replace('"', '""') + '"'


def sheet_names(segments, reserved=()):
    translated = {s.source for s in segments if s.anchor.get('category') == 'sheet_title'}
    names = {name: name for name in reserved if name not in translated}
    used = {name.casefold() for name in names}
    # Reserve unchanged names before assigning translated ones.
    for segment in segments:
        if segment.anchor.get('category') == 'sheet_title' and segment.text == segment.source:
            names[segment.source] = segment.source
            used.add(segment.source.casefold())
    for segment in segments:
        if segment.anchor.get('category') != 'sheet_title' or segment.source in names:
            continue
        name = re.sub(r'[\\/*?:\[\]\x00-\x1f]', ' ', segment.text).strip().strip("'")
        name = name[:31].rstrip("'") or 'Sheet'
        if name.casefold() == 'history':
            name = 'History sheet'
        candidate, counter = name, 2
        while candidate.casefold() in used:
            suffix = f' ({counter})'
            candidate = name[:31-len(suffix)].rstrip("'") + suffix
            counter += 1
        used.add(candidate.casefold())
        names[segment.source] = candidate
    return names


def rewrite_references(expression, names):
    """Replace local sheet qualifiers outside string literals; retain source spans."""
    lookup = {old.casefold(): new for old, new in names.items() if old != new}
    if not lookup or not expression:
        return expression
    # Match a whole sheet qualifier before looking for string constants: a valid
    # quoted sheet name can itself contain a double quote.
    tokens = list(FORMULA_LEXEME.finditer(expression))
    code, offset = [], 0
    for token in tokens:
        code.append(expression[offset:token.start()])
        code.append(' ' * len(token[0]))
        offset = token.end()
    code.append(expression[offset:])
    if re.search(r'(?i)(?<![\w.])(?:_xlfn\.)?INDIRECT\s*\(', ''.join(code)):
        raise ValueError('Excel INDIRECT uses dynamic sheet references. Preserve the original worksheet '
                         'names in review before exporting, or replace/review INDIRECT references.')
    link_rewrites = {}
    for call in re.finditer(r'(?i)(?<![\w.])(?:_xlfn\.)?HYPERLINK\s*\(', ''.join(code)):
        start = call.end()
        while start < len(expression) and expression[start].isspace():
            start += 1
        target = STRING.match(expression, start)
        tail = expression[target.end():].lstrip() if target is not None else ''
        if target is None or not tail.startswith((',', ';', ')')):
            raise ValueError('Excel HYPERLINK uses a dynamic target. Preserve the original worksheet '
                             'names in review before exporting, or review/replace the link target.')
        value = target[0][1:-1].replace('""', '"')
        if value.startswith('#'):
            value = '#' + rewrite_references(value[1:], names)
            link_rewrites[target.start()] = '"' + value.replace('"', '""') + '"'
    pieces, offset, bracket_depth = [], 0, 0
    for match in tokens:
        gap = expression[offset:match.start()]
        bracket_depth += gap.count('[') - gap.count(']')
        pieces.append(gap)
        token = match[0]
        replacement = link_rewrites.get(match.start(), token)
        if match.lastgroup == 'reference' and bracket_depth <= 0:
            qualifier = token[:-1]
            if '[' not in qualifier and ']' not in qualifier:
                endpoints = re.findall(SHEET_ENDPOINT, qualifier)
                decoded = [item[1:-1].replace("''", "'") if item.startswith("'") else item
                           for item in endpoints]
                # Excel also writes 3D ranges as one quoted 'first:last' qualifier.
                if len(decoded) == 1:
                    decoded = decoded[0].split(':')
                replaced = [lookup.get(item.casefold(), item) for item in decoded]
                if replaced != decoded:
                    replacement = "'" + ':'.join(replaced).replace("'", "''") + "'!"
        pieces.append(replacement)
        offset = match.end()
    pieces.append(expression[offset:])
    return ''.join(pieces)


def rename_package(archive, roots, names, workbook_part, rels, xml):
    if not any(old != new for old, new in names.items()):
        return
    workbook = roots.get(workbook_part)
    if workbook is None:
        workbook = xml(archive.read(workbook_part))
    for sheet in workbook.findall('s:sheets/s:sheet', NS):
        sheet.set('name', names.get(sheet.get('name'), sheet.get('name')))
    roots[workbook_part] = workbook
    # Includes defined names, formulas, chart refs, validation/conditional expressions,
    # table calculated formulas, sparkline formulas and internal hyperlink locations.
    formula_tags = {'f', 'formula', 'formula1', 'formula2', 'definedName',
                    'calculatedColumnFormula', 'totalsRowFormula', 'FmlaLink', 'FmlaRange'}
    for part in archive.namelist():
        if not part.endswith(('.xml', '.rels')) :
            continue
        root = roots.get(part)
        if root is None:
            root = xml(archive.read(part))
        changed = False
        if '/charts/' in part:
            external = root.find('c:externalData', NS)
            relationship = rels(archive, part).get(external.get(q('r', 'id'))) if external is not None else None
            if relationship and not relationship[2] and relationship[0].endswith('.xlsx'):
                continue  # This chart is rewritten using its embedded workbook's names.
        for node in root.iter():
            if not isinstance(node.tag, str):
                continue
            local = etree.QName(node).localname
            namespace = etree.QName(node).namespace or ''
            formula_namespace = (namespace in {NS['s'], NS['c'],
                                 'http://schemas.microsoft.com/office/excel/2006/main',
                                 'urn:schemas-microsoft-com:office:excel'}
                                 or namespace.startswith('http://schemas.microsoft.com/office/spreadsheetml/'))
            if local == 'worksheetSource' and namespace == NS['s'] and node.get('sheet') and not node.get(q('r', 'id')):
                name = node.get('sheet')
                updated = next((new for old, new in names.items() if old.casefold() == name.casefold()), name)
                if updated != name:
                    node.set('sheet', updated)
                    changed = True
            if local in formula_tags and formula_namespace and node.text:
                value = rewrite_references(node.text, names)
                if value != node.text:
                    node.text, changed = value, True
            if local == 'hyperlink' and namespace == NS['s'] and node.get('location'):
                value = rewrite_references(node.get('location'), names)
                if value != node.get('location'):
                    node.set('location', value)
                    changed = True
            if local == 'Relationship' and node.get('Type', '').endswith('/hyperlink'):
                target = node.get('Target', '')
                if target.startswith('#'):
                    value = '#' + rewrite_references(target[1:], names)
                    if value != target:
                        node.set('Target', value)
                        changed = True
        if changed:
            roots[part] = root
    calculation = workbook.find('s:calcPr', NS)
    if calculation is None:
        calculation = etree.SubElement(workbook, q('s', 'calcPr'))
    calculation.set('fullCalcOnLoad', '1')
    calculation.set('forceFullCalc', '1')
