"""Markdown parser — produces an ALOnDocument from raw markdown text."""

from __future__ import annotations
import re
from typing import List, Tuple

import yaml

from .document import (
    ALOnDocument, Block,
    ContextBlock, ModelBlock, FenceBlock, HeadingBlock, TextBlock,
)

_FENCE_OPEN  = re.compile(r'^(?P<chars>`{3,}|~{3,})(?P<lang>\S*)\s*$')
_HEADING     = re.compile(r'^(?P<hashes>#{1,6})\s+(?P<text>.+)$')


def _extract_front_matter(mermaid_body: str) -> Tuple[dict, str]:
    """Split YAML front matter from diagram body.

    Returns (front_matter_dict, diagram_text).  If no front matter is found
    both the dict is empty and the full body is returned as diagram text.
    """
    lines = mermaid_body.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, mermaid_body

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, mermaid_body

    yaml_src = "\n".join(lines[1:end])
    diagram  = "\n".join(lines[end + 1:]).strip()
    try:
        fm = yaml.safe_load(yaml_src) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, diagram


def parse(text: str) -> ALOnDocument:
    """Parse *text* into an ALOnDocument."""
    doc = ALOnDocument()
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── Fenced block ────────────────────────────────────────────────
        m = _FENCE_OPEN.match(line)
        if m:
            fence_char = m.group("chars")[0]
            fence_len  = len(m.group("chars"))
            lang       = m.group("lang").lower().strip()
            close_re   = re.compile(
                r'^' + re.escape(fence_char) + r'{' + str(fence_len) + r',}\s*$'
            )

            j = i + 1
            body_lines: List[str] = []
            while j < len(lines) and not close_re.match(lines[j]):
                body_lines.append(lines[j])
                j += 1

            body = "\n".join(body_lines)
            raw  = "\n".join(lines[i : j + 1])

            if lang == "alon-context":
                try:
                    data = yaml.safe_load(body) or {}
                except yaml.YAMLError:
                    data = {}
                doc.blocks.append(ContextBlock(data=data, raw_yaml=body))

            elif lang == "mermaid":
                fm, diagram = _extract_front_matter(body)
                if fm:
                    doc.blocks.append(ModelBlock(
                        raw=raw,
                        front_matter=fm,
                        diagram=diagram,
                    ))
                else:
                    doc.blocks.append(FenceBlock(language="mermaid",
                                                  content=body, raw=raw))
            else:
                doc.blocks.append(FenceBlock(language=lang, content=body, raw=raw))

            i = j + 1
            continue

        # ── Heading ─────────────────────────────────────────────────────
        hm = _HEADING.match(line)
        if hm:
            doc.blocks.append(HeadingBlock(
                level=len(hm.group("hashes")),
                text=hm.group("text").strip(),
                raw=line,
            ))
            i += 1
            continue

        # ── Plain text (accumulate until next fence or heading) ─────────
        text_lines: List[str] = []
        while i < len(lines):
            l = lines[i]
            if _FENCE_OPEN.match(l) or _HEADING.match(l):
                break
            text_lines.append(l)
            i += 1

        doc.blocks.append(TextBlock(content="\n".join(text_lines)))

    return doc
