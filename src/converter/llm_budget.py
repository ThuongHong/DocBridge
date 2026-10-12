"""Conservative request budgeting for providers with unknown tokenizers."""

import json
import re


def estimate_input_tokens(messages: list[dict]) -> int:
    # A UTF-8 byte count overestimates common byte/BPE tokenizers, including JSON
    # escaping and chat framing. It is an estimate, not a vendor tokenizer oracle.
    encoded = json.dumps(messages, ensure_ascii=False).encode("utf-8")
    return len(encoded) + 64 + 32 * len(messages)


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
