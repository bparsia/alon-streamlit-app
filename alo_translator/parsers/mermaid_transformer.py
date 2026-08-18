"""
Transformer skeleton for Mermaid class diagram grammar.

Converts parsed Mermaid diagrams into structured data.
"""

from lark import Transformer, Token
from typing import Any, List, Optional, Dict


class MermaidTransformer(Transformer):
    """Transform parsed Mermaid class diagrams into structured data."""

    def start(self, items):
        """
        Top-level rule: frontmatter? diagram

        Returns dict with:
        - frontmatter: Optional[dict] - YAML front matter (if present)
        - diagram: dict - The class diagram structure
        """
        if len(items) == 2:
            frontmatter, diagram = items
            return {"frontmatter": frontmatter, "diagram": diagram}
        else:
            diagram = items[0]
            return {"frontmatter": None, "diagram": diagram}

    def frontmatter(self, items):
        """
        Parse YAML front matter: "---" _NL YAML_BLOCK "---" _NL

        Returns the raw YAML content as a string (to be parsed separately if needed).
        """
        yaml_block = str(items[0])  # YAML_BLOCK terminal
        return yaml_block.rstrip('\n')  # Remove trailing newlines

    def diagram(self, items):
        """
        Main diagram: "classDiagram" _NL direction? statement*

        Returns dict with:
        - direction: Optional[str] - Direction specification (BT/TB/LR/RL)
        - succs: List[dict] - List of succession (association) links
        - moment_props: List[dict] - List of moment proposition declarations
        """
        direction = None
        succs = []
        moment_props = []

        for item in items:
            if isinstance(item, dict):
                if 'direction' in item:
                    direction = item['direction']
                elif 'from_moment' in item:
                    succs.append(item)
                elif 'moment_id' in item:
                    moment_props.append(item)

        return {
            "direction": direction,
            "succs": succs,
            "moment_props": moment_props
        }

    def direction(self, items):
        """
        Direction specification: "direction" DIRECTION _NL

        Returns dict with direction value (BT/TB/LR/RL).
        """
        direction_token = items[0]
        return {"direction": str(direction_token)}

    def proposition(self, items):
        """
        Proposition (attribute): "~"? IDENTIFIER

        Returns the proposition name (possibly negated with a leading ~).
        """
        if len(items) == 2:
            # Has negation
            prop_name = str(items[1])
            return f"~{prop_name}"
        else:
            # No negation
            prop_name = str(items[0])
            return prop_name

    def succ(self, items):
        """
        Succession (association): IDENTIFIER "-->" IDENTIFIER (":" label)? _NL?

        Returns dict with:
        - from_moment: str - Source moment identifier
        - to_moment: str - Target moment identifier
        - label: Optional[str] - Link label (usually "succ")
        """
        from_moment = str(items[0])
        to_moment = str(items[1])
        label = None

        if len(items) > 2:
            label = items[2]

        return {
            "from_moment": from_moment,
            "to_moment": to_moment,
            "label": label
        }

    def label(self, items):
        """
        Label text: /[^\n]+/

        Returns the label as a string.
        """
        return str(items[0]).strip()

    def moment_props(self, items):
        """
        Moment proposition declaration: IDENTIFIER ":" proposition ("," proposition)* _NL?

        Returns dict with:
        - moment_id: str - Moment identifier
        - propositions: List[str] - Proposition names (possibly negated with a leading ~)
        """
        identifier = str(items[0])
        propositions = [p for p in items[1:] if isinstance(p, str)]

        return {
            "moment_id": identifier,
            "propositions": propositions
        }

    # Terminal transformers
    def IDENTIFIER(self, token):
        """Transform IDENTIFIER terminal."""
        return token.value

    def DIRECTION(self, token):
        """Transform DIRECTION terminal."""
        return token.value
