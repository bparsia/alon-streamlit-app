"""Markdown renderer — expands shortcodes, suppresses context blocks."""

from __future__ import annotations
from ..document import ALOnDocument, ContextBlock, ModelBlock, TextBlock, HeadingBlock, FenceBlock
from .. import shortcodes


def render(doc: ALOnDocument, show_context: bool = False, analysis=None) -> str:
    """Render *doc* to a processed markdown string.

    - alon-context blocks are suppressed (or shown as HTML comments)
    - ModelBlocks are passed through unchanged
    - TextBlocks have {{shortcodes}} expanded
    - Everything else is passed through unchanged
    """
    parts = []

    for idx, block in enumerate(doc.blocks):

        if isinstance(block, ContextBlock):
            if show_context:
                parts.append(f"<!-- alon-context\n{block.raw_yaml}\n-->")
            # else: suppress entirely

        elif isinstance(block, ModelBlock):
            # Strip front matter — render as a clean diagram only
            parts.append(f"```mermaid\n{block.diagram}\n```")

        elif isinstance(block, (FenceBlock, HeadingBlock)):
            parts.append(block.raw)

        elif isinstance(block, TextBlock):
            expanded = shortcodes.expand(block.content, doc, idx, analysis=analysis)
            parts.append(expanded)

    return "\n".join(parts)
