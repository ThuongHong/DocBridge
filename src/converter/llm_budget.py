"""Conservative request budgeting for providers with unknown tokenizers."""

import json
import re


def estimate_input_tokens(messages: list[dict]) -> int:
    # Approximate an unknown tokenizer with headroom for technical Chinese.
    # JSON escaping/framing is included. Provider context errors still split.
    text = json.dumps(messages, ensure_ascii=False)
    units = 0
    for part in re.findall(r"[\u3400-\u9fff\uf900-\ufaff]+|[A-Za-z ]+|[0-9]+|[^\u3400-\u9fff\uf900-\ufaffA-Za-z 0-9]+", text):
        first = part[0]
        if "\u3400" <= first <= "\u9fff" or "\uf900" <= first <= "\ufaff":
            units += len(part) * 1.5
        elif first.isascii() and (first.isalpha() or first == " "):
            units += (len(part) + 2) // 3
        elif first.isascii() and first.isdigit():
            units += (len(part) + 1) // 2
        else:
            units += len(part.encode("utf-8"))
    return int(units + .999) + 64 + 32 * len(messages)


def split_source(source: str, protected_pattern: re.Pattern) -> tuple[str, str] | None:
    """Split near the middle without breaking a glossary term, code, number or URL."""
    if len(source) < 2:
        return None
    midpoint = len(source) // 2
    spans = [(match.start(), match.end()) for match in protected_pattern.finditer(source)]

    def safe(index):
        return 0 < index < len(source) and not any(a < index < b for a, b in spans)

    natural = [
        match.end() for match in re.finditer(r"[。！？；!?;\n\s]", source)
        if len(source) // 4 <= match.end() <= len(source) * 3 // 4 and safe(match.end())
    ]
    if natural:
        index = min(natural, key=lambda i: abs(i - midpoint))
    else:
        candidates = [midpoint] + [edge for span in spans for edge in span]
        valid = [i for i in candidates if safe(i)]
        if not valid:
            return None
        index = min(valid, key=lambda i: abs(i - midpoint))
    return source[:index], source[index:]


def join_translations(left: str, right: str) -> str:
    if left and right and not left[-1].isspace() and not right[0].isspace():
        if right[0] not in ",.;:!?)]}，。；：！？":
            return left + " " + right
    return left + right
