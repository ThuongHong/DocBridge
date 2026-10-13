"""Conservative raster layout recovery using the existing Pillow/OCR runtime."""
from __future__ import annotations

from PIL import ImageDraw


def ruled_tables(image) -> list[dict]:
    """Detect complete rectangular grids; incomplete/merged grids remain images."""
    gray = image.convert("L")
    pixels = gray.load()
    minimum = max(80, image.width // 8)
    rows = []
    for y in range(image.height):
        start = None
        for x in range(image.width + 1):
            dark = x < image.width and pixels[x, y] < 150
            if dark and start is None:
                start = x
            elif not dark and start is not None:
                if x - start >= minimum:
                    rows.append((y, start, x - 1))
                start = None
    groups = []
    for y, left, right in rows:
        group = next((g for g in groups if abs(g[0][1] - left) <= 4
                      and abs(g[0][2] - right) <= 4), None)
        if group is None:
            groups.append([(y, left, right)])
        else:
            group.append((y, left, right))

    def centers(values):
        bands = []
        for value in sorted(set(values)):
            if bands and value - bands[-1][-1] <= 3:
                bands[-1].append(value)
            else:
                bands.append([value])
        return [round(sum(band) / len(band)) for band in bands]

    result = []
    for group in groups:
        ys = centers([row[0] for row in group])
        if len(ys) < 3 or min(b - a for a, b in zip(ys, ys[1:], strict=False)) < 12:
            continue
        left, right = group[0][1:]
        top, bottom = ys[0], ys[-1]
        xs = centers([x for x in range(max(0, left - 3), min(image.width, right + 4))
                      if sum(pixels[x, y] < 150 for y in range(top, bottom + 1))
                      >= (bottom - top + 1) * 0.9])
        if len(xs) < 3 or abs(xs[0] - left) > 4 or abs(xs[-1] - right) > 4:
            continue
        if min(b - a for a, b in zip(xs, xs[1:], strict=False)) < 12:
            continue
        # Reject grids whose horizontal lines do not reach every column boundary.
        if not all(any(pixels[xx, yy] < 150
                       for xx in range(max(0, x - 2), min(image.width, x + 3))
                       for yy in range(max(0, y - 2), min(image.height, y + 3)))
                   for x in xs for y in ys):
            continue
        result.append({"bbox": [xs[0], top, xs[-1], bottom], "xs": xs, "ys": ys})
    gray.close()
    return result


def remaining_figures(image, text_boxes: list, table_boxes: list, text_height: float) -> list:
    """Keep substantial unrecognized ink regions without duplicating OCR text."""
    residual = image.convert("L").point(lambda value: 255 if value >= 180 else 0)
    draw = ImageDraw.Draw(residual)
    for box in text_boxes + table_boxes:
        draw.rectangle((box[0] - 3, box[1] - 3, box[2] + 3, box[3] + 3), fill=255)
    bands = []
    for y in range(residual.height):
        row = residual.crop((0, y, residual.width, y + 1))
        box = row.point(lambda value: 255 - value).getbbox()
        row.close()
        if box:
            if bands and y - bands[-1][3] <= max(4, text_height / 3):
                band = bands[-1]
                band[0], band[2], band[3] = min(band[0], box[0]), max(band[2], box[2]), y + 1
            else:
                bands.append([box[0], y, box[2], y + 1])
    residual.close()
    return [box for box in bands
            if box[2] - box[0] >= text_height * 1.5
            and box[3] - box[1] >= text_height * 0.8
            and (box[2] - box[0]) * (box[3] - box[1]) >= text_height ** 2 * 6
            and (box[2] - box[0]) * (box[3] - box[1]) < image.width * image.height * 0.8]
