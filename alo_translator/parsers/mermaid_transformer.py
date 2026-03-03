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
        - moments: List[dict] - List of moment (class) definitions
        - succs: List[dict] - List of succession (association) links
        - shorthand_members: List[dict] - List of shorthand member declarations
        """
        direction = None
        moments = []
        succs = []
        shorthand_members = []

        for item in items:
            if isinstance(item, dict):
                if 'direction' in item:
                    direction = item['direction']
                elif 'moment_id' in item:
                    moments.append(item)
                elif 'from_moment' in item:
                    succs.append(item)
                elif 'shorthand' in item:
                    shorthand_members.append(item)

        return {
            "direction": direction,
            "moments": moments,
            "succs": succs,
            "shorthand_members": shorthand_members
        }

    def direction(self, items):
        """
        Direction specification: "direction" DIRECTION _NL

        Returns dict with direction value (BT/TB/LR/RL).
        """
        direction_token = items[0]
        return {"direction": str(direction_token)}

    def moment(self, items):
        """
        Moment (class) definition: "class" IDENTIFIER "{" _NL? members? "}" _NL?

        Returns dict with:
        - moment_id: str - The identifier for this moment
        - actions: List[str] - List of action method names
        - propositions: List[str] - List of propositions (with optional ~)
        """
        moment_id = str(items[0])

        actions = []
        propositions = []

        # Check if members present (items[1] if exists)
        if len(items) > 1 and isinstance(items[1], dict):
            members = items[1]
            actions = members.get('actions', [])
            propositions = members.get('propositions', [])

        return {
            "moment_id": moment_id,
            "actions": actions,
            "propositions": propositions
        }

    def members(self, items):
        """
        Members list: member+

        Returns dict with:
        - actions: List[str] - Action method names
        - propositions: List[str] - Proposition attributes
        """
        actions = []
        propositions = []

        for item in items:
            if isinstance(item, dict):
                if 'action' in item:
                    actions.append(item['action'])
                elif 'proposition' in item:
                    propositions.append(item['proposition'])

        return {
            "actions": actions,
            "propositions": propositions
        }

    def action(self, items):
        """
        Action (method): IDENTIFIER "()"

        Returns dict with action name.
        """
        action_name = str(items[0])
        return {"action": action_name}

    def proposition(self, items):
        """
        Proposition (attribute): "~"? IDENTIFIER

        Returns dict with proposition (possibly negated).
        """
        if len(items) == 2:
            # Has negation
            prop_name = str(items[1])
            return {"proposition": f"~{prop_name}"}
        else:
            # No negation
            prop_name = str(items[0])
            return {"proposition": prop_name}

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

    def shorthand_member(self, items):
        """
        Shorthand member: IDENTIFIER ":" member_value _NL?

        Returns dict with:
        - shorthand: True
        - identifier: str - Class/moment identifier
        - value: str - Member value
        """
        identifier = str(items[0])
        value = str(items[1])

        return {
            "shorthand": True,
            "identifier": identifier,
            "value": value
        }

    def member_value(self, items):
        """
        Member value: /[^\n]+/

        Returns the value as a string.
        """
        return str(items[0]).strip()

    # Terminal transformers
    def IDENTIFIER(self, token):
        """Transform IDENTIFIER terminal."""
        return token.value

    def DIRECTION(self, token):
        """Transform DIRECTION terminal."""
        return token.value
