from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from .models import Block, Document


def escape(text: str) -> str:
    return re.sub(r"([\\`*_{}\[\]<>#|])", r"\\\1", text).replace("\r", "")


def render_markdown(doc: Document, asset_folder: str, *, source: bool = False) -> str:
    if not source and not doc.complete():
        raise ValueError("Còn đoạn chưa dịch; hãy review trước khi xuất Markdown.")
    lookup = doc.by_id()

    def inline(block: Block) -> str:
        pieces = []
        entries = block.meta.get("inline", [{"segment": sid} for sid in block.segments])
        for entry in entries:
            if "text" in entry:
                pieces.append(escape(entry["text"]).replace("\n", "<br>"))
                continue
            sid = entry["segment"]
            segment = lookup[sid]
            text = escape(segment.source if source else segment.text)
            if not text.strip():
                pieces.append(text)
                continue
            leading = text[: len(text) - len(text.lstrip())]
            trailing = text[len(text.rstrip()) :]
            content = text.strip()
            if content:
                if segment.style.get("b"):
                    content = f"**{content}**"
                if segment.style.get("i"):
                    content = f"*{content}*"
                if segment.style.get("strike"):
                    content = f"~~{content}~~"
                if segment.style.get("link"):
                    content = f"[{content}]({quote(segment.style['link'], safe=':/?=&%#@+')})"
            pieces.append(leading + content + trailing)
        return "".join(pieces) if pieces else escape(str(block.meta.get("literal", "")))

    def render(block: Block) -> str:
        if block.kind == "section":
            title = escape(block.meta.get("title", ""))
            children = [child for child in block.children
                        if child.meta.get("role") not in {"page_header", "page_footer"}]
            return f"## {title}\n\n" + "\n\n".join(render(child) for child in children)
        if block.kind == "heading":
            return "#" * block.meta.get("level", 1) + " " + inline(block)
        if block.kind == "list":
            return "- " + inline(block)
        if block.kind == "image":
            key = block.meta.get("asset")
            if key in doc.assets:
                return f"![Image]({quote(asset_folder)}/{quote(Path(key).name)})"
            return ""
        if block.kind == "table":
            rows = []
            width = max((len(row.children) for row in block.children), default=0)
            if not width:
                return ""
            for row in block.children:
                cells = [render(cell).replace("\n", "<br>") for cell in row.children]
                rows.append(cells + [""] * (width - len(cells)))
            # Keep every row as data: do not silently turn the first data row into headings.
            return "\n".join(
                [
                    "| " + " | ".join([""] * width) + " |",
                    "| " + " | ".join(["---"] * width) + " |",
                    *["| " + " | ".join(row) + " |" for row in rows],
                ]
            )
        if block.kind == "cell":
            return inline(block) + "\n".join(render(child) for child in block.children)
        return inline(block)

    return "\n\n".join(filter(None, (render(block) for block in doc.blocks))) + "\n"
