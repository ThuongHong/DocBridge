"""Keep direct text criteria aligned with translated worksheet labels.

Tokenize for classification only: replace original string spans, never rebuild a
formula or save the workbook through openpyxl.
"""
from __future__ import annotations

import re
from collections import defaultdict

from openpyxl.formula.tokenizer import Tokenizer, TokenizerError


def criteria_pairs(name, count):
    if name in {"SUMIF", "COUNTIF", "AVERAGEIF"}:
        return [(0, 1)] if count >= 2 else []
    if name in {"SUMIFS", "AVERAGEIFS"}:
        return (list(zip(range(1, count - 1, 2), range(2, count, 2), strict=True))
                if count >= 3 and count % 2 else [])
    if name == "COUNTIFS" and count >= 2 and count % 2 == 0:
        return list(zip(range(0, count - 1, 2), range(1, count, 2), strict=True))
    return []


def range_bounds(reference, current_sheet):
    sheet, separator, address = reference.rpartition("!")
    if not separator:
        sheet, address = current_sheet, reference
    elif sheet.startswith("'") and sheet.endswith("'"):
        sheet = sheet[1:-1].replace("''", "'")
    if any(char in sheet for char in "[]:"):
        return None
    match = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?", address, re.I)
    if match:
        col, row, end_col, end_row = match.groups()
        return sheet, (column(col), int(row), column(end_col or col), int(end_row or row))
    match = re.fullmatch(r"\$?([A-Z]+):\$?([A-Z]+)", address, re.I)
    if match:
        return sheet, (column(match[1]), 1, column(match[2]), 1048576)
    return None


def column(name):
    value = 0
    for letter in name.upper():
        value = value * 26 + ord(letter) - 64
    return value


def translated_cells(segments):
    groups = defaultdict(list)
    for segment in segments:
        anchor = segment.anchor
        if "cell" in anchor:
            groups[(anchor.get("sheet", ""), anchor["cell"])].append(segment)
    result = defaultdict(list)
    for (sheet, address), items in groups.items():
        match = re.fullmatch(r"([A-Z]+)(\d+)", address, re.I)
        if match:
            result[sheet.casefold()].append((column(match[1]), int(match[2]),
                "".join(s.source for s in items), "".join(s.text for s in items)))
    return result


def aligned_criterion(value, reference, sheet, cells):
    bounds = range_bounds(reference, sheet)
    if bounds is None or any(char in value for char in "*?~"):
        return value
    # Ordered string comparisons depend on lexical order, which translation changes.
    match = re.fullmatch(r"(<>|=)?(.*)", value, re.S)
    prefix, label = match.groups()
    if label.startswith(("<", ">")):
        return value
    name, (left, top, right, bottom) = bounds
    selected = [(source, target) for col, row, source, target in cells[name.casefold()]
                if left <= col <= right and top <= row <= bottom]
    targets = {target for source, target in selected if source.casefold() == label.casefold()}
    if not targets:
        if any(target.casefold() == label.casefold() for source, target in selected):
            raise ValueError("Bản dịch nhãn tạo thêm ô khớp điều kiện Excel; "
                             "hãy review nhãn trước khi xuất.")
        return value
    if len(targets) != 1:
        raise ValueError("Điều kiện Excel có nhiều bản dịch trong cùng vùng dữ liệu; "
                         "hãy dùng cùng bản dịch cho các nhãn trước khi xuất.")
    target = targets.pop()
    if any(char in target for char in "*?~") or (not prefix and target.startswith(("=", "<", ">"))):
        raise ValueError("Bản dịch nhãn tạo ký tự điều kiện Excel; hãy review nhãn trước khi xuất.")
    if any(source.casefold() != label.casefold() and translated.casefold() == target.casefold()
           for source, translated in selected):
        raise ValueError("Các nhãn khác nhau có cùng bản dịch trong vùng điều kiện Excel; "
                         "hãy review nhãn trước khi xuất.")
    return (prefix or "") + target


def align_formula(formula, sheet, cells):
    try:
        tokens = Tokenizer("=" + formula).items
    except TokenizerError:
        return formula
    # Tokenizer normalizes whitespace; recover spans from the untouched formula.
    spans, offset = [], 0
    for token in tokens:
        start = offset
        if token.type == "WHITE-SPACE":
            whitespace = re.match(r"[ \n]+", formula[offset:])
            if whitespace is None:
                return formula
            offset += whitespace.end()
        elif formula.startswith(token.value, offset):
            offset += len(token.value)
        else:
            return formula
        spans.append((start, offset))
    if offset != len(formula):
        return formula
    replacements = {}
    for index, token in enumerate(tokens):
        if token.type != "FUNC" or token.subtype != "OPEN":
            continue
        arguments, current, depth = [], [], 1
        for next_index in range(index + 1, len(tokens)):
            item = tokens[next_index]
            if item.subtype == "OPEN":
                depth += 1
            elif item.subtype == "CLOSE":
                depth -= 1
                if depth == 0:
                    arguments.append(current)
                    break
            if depth == 1 and item.type == "SEP" and item.subtype == "ARG":
                arguments.append(current)
                current = []
            elif item.type != "WHITE-SPACE":
                current.append(next_index)
        for range_index, criterion_index in criteria_pairs(token.value[:-1].upper(), len(arguments)):
            range_arg, criterion_arg = arguments[range_index], arguments[criterion_index]
            if len(range_arg) != 1 or len(criterion_arg) != 1:
                continue
            reference, criterion = tokens[range_arg[0]], tokens[criterion_arg[0]]
            if reference.subtype != "RANGE" or criterion.subtype != "TEXT":
                continue
            value = criterion.value[1:-1].replace('""', '"')
            aligned = aligned_criterion(value, reference.value, sheet, cells)
            if aligned != value:
                replacements[criterion_arg[0]] = '"' + aligned.replace('"', '""') + '"'
    for index, value in sorted(replacements.items(), reverse=True):
        start, end = spans[index]
        formula = formula[:start] + value + formula[end:]
    return formula
