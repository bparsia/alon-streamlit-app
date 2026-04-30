"""Resolver — merges alon-context inheritance into each ModelBlock."""

from __future__ import annotations
import copy
from typing import Any, Dict

from .document import ALOnDocument, ContextBlock, ModelBlock


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Return a new dict: *override* wins, but nested dicts are merged recursively."""
    result = copy.deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def resolve(doc: ALOnDocument) -> ALOnDocument:
    """Mutate *doc* in-place: set resolved_fm on every ModelBlock.

    Walks blocks in order; each ContextBlock replaces the running context
    (scope = from that block until the next ContextBlock).  Each ModelBlock
    receives a deep-merge of the current context with its own front_matter
    (model wins on conflicts at every nesting level).
    """
    current_context: Dict[str, Any] = {}

    for block in doc.blocks:
        if isinstance(block, ContextBlock):
            current_context = copy.deepcopy(block.data)
        elif isinstance(block, ModelBlock):
            block.resolved_fm = _deep_merge(current_context, block.front_matter)

    return doc
