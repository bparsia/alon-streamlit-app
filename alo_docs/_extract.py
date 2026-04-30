"""Extraction — produce self-contained mermaid blocks from resolved ModelBlocks."""

from __future__ import annotations
from typing import Optional

import yaml

from .document import ModelBlock


def model_to_mmd(block: ModelBlock) -> str:
    """Return a self-contained mermaid source string for *block*.

    The returned string starts with the opening fence line (```mermaid),
    embeds the **resolved** front matter (so inherited context is inlined),
    and closes with the fence.  Safe to paste into any markdown document.
    """
    fm = block.resolved_fm if block.resolved_fm else block.front_matter
    fm_yaml = yaml.dump(fm, default_flow_style=False, allow_unicode=True).rstrip()
    return f"```mermaid\n---\n{fm_yaml}\n---\n{block.diagram}\n```"


def extract_models(text: str) -> list[str]:
    """Parse *text*, resolve context, and return one mermaid string per ModelBlock."""
    from .parser import parse
    from .resolver import resolve

    doc = resolve(parse(text))
    return [model_to_mmd(b) for b in doc.models()]
