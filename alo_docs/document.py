"""Document data model — blocks produced by the parser."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


def _str_keys(d: Any) -> Any:
    """Recursively normalise dict keys to str (YAML parses bare integers as int)."""
    if isinstance(d, dict):
        return {str(k): _str_keys(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_str_keys(v) for v in d]
    return d


@dataclass
class ContextBlock:
    """An ```alon-context``` fenced block — shared metadata until the next one."""
    data: Dict[str, Any]
    raw_yaml: str

    def __post_init__(self):
        self.data = _str_keys(self.data)


@dataclass
class ModelBlock:
    """A ```mermaid``` fenced block with ALOn YAML front matter."""
    raw: str                          # full original text including fence lines
    front_matter: Dict[str, Any]      # parsed YAML front matter (raw from source)
    diagram: str                      # everything after the closing ---
    resolved_fm: Dict[str, Any] = field(default_factory=dict)  # set by resolver

    def __post_init__(self):
        self.front_matter = _str_keys(self.front_matter)

    @property
    def title(self) -> str:
        return self.front_matter.get("title", "")

    @property
    def aliases(self) -> Dict[str, str]:
        return self.resolved_fm.get("aliases", self.front_matter.get("aliases", {}))

    @property
    def actions(self) -> Dict[str, List[str]]:
        return self.resolved_fm.get("actions", self.front_matter.get("actions", {}))

    @property
    def opposings(self) -> Dict[str, List[str]]:
        return self.resolved_fm.get("opposings", self.front_matter.get("opposings", {}))


@dataclass
class FenceBlock:
    """Any other fenced block — passed through unchanged."""
    language: str
    content: str
    raw: str


@dataclass
class HeadingBlock:
    """A markdown heading."""
    level: int   # 1–6
    text: str
    raw: str


@dataclass
class TextBlock:
    """Plain markdown text; may contain {{shortcode}} calls."""
    content: str


Block = Union[ContextBlock, ModelBlock, FenceBlock, HeadingBlock, TextBlock]


@dataclass
class ALOnDocument:
    blocks: List[Block] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def models(self) -> List[ModelBlock]:
        return [b for b in self.blocks if isinstance(b, ModelBlock)]

    def model_by_title(self, title: str) -> Optional[ModelBlock]:
        for b in self.blocks:
            if isinstance(b, ModelBlock) and b.title == title:
                return b
        return None

    def nearest_model(self, block_idx: int) -> Optional[ModelBlock]:
        """Nearest ModelBlock preceding position block_idx."""
        for i in range(block_idx - 1, -1, -1):
            if isinstance(self.blocks[i], ModelBlock):
                return self.blocks[i]
        return None

    def all_aliases(self) -> Dict[str, str]:
        """Merge all aliases from every ContextBlock and ModelBlock in document order."""
        merged: Dict[str, str] = {}
        for block in self.blocks:
            if isinstance(block, ContextBlock):
                merged.update(block.data.get("aliases", {}))
            elif isinstance(block, ModelBlock):
                merged.update(block.resolved_fm.get("aliases",
                              block.front_matter.get("aliases", {})))
        return merged

    def models_in_section(self, block_idx: int) -> List[ModelBlock]:
        """All ModelBlocks under the same markdown section as block_idx."""
        # Find the opening heading for this block
        section_start = 0
        section_level = 1
        for i in range(block_idx - 1, -1, -1):
            if isinstance(self.blocks[i], HeadingBlock):
                section_start = i
                section_level = self.blocks[i].level
                break

        # Find the closing heading (same or higher level)
        section_end = len(self.blocks)
        for i in range(section_start + 1, len(self.blocks)):
            b = self.blocks[i]
            if isinstance(b, HeadingBlock) and b.level <= section_level:
                section_end = i
                break

        return [b for b in self.blocks[section_start:section_end]
                if isinstance(b, ModelBlock)]
