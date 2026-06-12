"""
Core model classes for ALOn structures.

This module defines the object model for ALOn (Action Logic with Opposing),
providing a clean API for constructing and manipulating models programmatically.

ALOModel represents a branching-time model with arbitrary temporal depth.
Models are constructed by parse_dbt_diagram() from Mermaid diagram input.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Union, Tuple


@dataclass
class Action:
    """
    An individual action performed by a single agent.

    Attributes:
        action_type: The type of action (e.g., "sd" for "shoots Dan")
        agent: The agent performing the action (e.g., "1" for Alice)
    """
    action_type: str
    agent: str

    def __str__(self) -> str:
        """Return action in standard format: actionType + agent (e.g., 'sd1')"""
        return f"{self.action_type}{self.agent}"

    def __hash__(self) -> int:
        return hash((self.action_type, self.agent))


@dataclass
class GroupAction:
    """
    A group action - a mapping from agents to their chosen actions.

    For complete group actions, all agents must have an action.
    For partial group actions, only some agents are specified.
    """
    actions: Dict[str, str]  # agent -> action_type

    def is_complete(self, all_agents: Set[str]) -> bool:
        """Check if this is a complete group action (all agents specified)"""
        return set(self.actions.keys()) == all_agents

    def to_action_list(self) -> List[Action]:
        """Convert to list of Action objects"""
        return [Action(action_type, agent)
                for agent, action_type in sorted(self.actions.items())]

    def __str__(self) -> str:
        """Return as conjunction: {1='sd', 2='ss'}"""
        items = ', '.join(f"{a}='{act}'" for a, act in sorted(self.actions.items()))
        return f"{{{items}}}"

    def opp_class_name(self) -> str:
        """Return a sanitized OWL class name for this group action's Opp2 class.

        Sorted alphabetically on composed action strings to match serializer output.
        e.g. GroupAction({1: sd, 2: ha}) → "Opp2_ha2_sd1"
        """
        composed = sorted(f"{act}{agent}" for agent, act in self.actions.items())
        return f"Opp2_{'_'.join(composed)}"


@dataclass
class History:
    """
    A history with its associated complete group action and optional name.

    In our 1-step models, each complete group action corresponds to exactly one history.
    """
    name: str  # e.g., "h1", "h2"
    complete_group_action: GroupAction

    def __str__(self) -> str:
        return self.name


@dataclass
class Proposition:
    """A propositional atom that can be true/false at moments."""
    symbol: str  # e.g., "q" for "Dan dies"

    def __str__(self) -> str:
        return self.symbol

    def __hash__(self) -> int:
        return hash(self.symbol)


@dataclass
class OpposingRelation:
    """
    An opposing relation: action opposed_action opposes action.

    Examples:
    - sd1 is opposed by ha2
    - killing (group action) is opposed by ha2
    """
    opposed_action: Union[Action, GroupAction]  # The action being opposed
    opposing_action: Union[Action, GroupAction]  # The action that opposes

    def __str__(self) -> str:
        return f"{self.opposing_action} opposes {self.opposed_action}"


@dataclass
class Result:
    """
    The result of a history: which propositions are true at its successor moment.

    Uses closed-world assumption: unlisted propositions are false.
    """
    history_name: str
    true_propositions: Set[str]  # Proposition symbols that are true
    moment_name: Optional[str] = None  # Successor moment name (e.g., "m1")

    def __str__(self) -> str:
        if self.true_propositions:
            props = ', '.join(sorted(self.true_propositions))
            return f"{self.history_name}: {props}"
        return f"{self.history_name}: (none)"


@dataclass
class Query:
    """
    An ALOn formula to be evaluated in the model.

    Evolves through pipeline:
    - Initially: just formula_string
    - After Pass 3 (parsing): formula_ast populated
    - After Pass 4 (expansion): expanded_ast populated

    Attributes:
        formula_string: The query string in ALOn syntax (e.g., "Xq", "[1 pres]q")
        formula_ast: Parsed FormulaNode (after Pass 3)
        expanded_ast: Expanded FormulaNode with only primitives (after Pass 4)
        category: Optional grouping label (e.g., "Effects", "Responsibility")
        query_id: Optional identifier (e.g., "q01")
    """
    formula_string: str
    formula_ast: Optional['FormulaNode'] = None     # After Pass 3
    expanded_ast: Optional['FormulaNode'] = None    # After Pass 4
    category: Optional[str] = None
    query_id: Optional[str] = None

    # Backwards compatibility
    @property
    def formula(self) -> str:
        """Alias for formula_string (backwards compatibility)."""
        return self.formula_string

    @property
    def modal_depth(self) -> int:
        """
        Get modal depth from expanded AST (or parsed AST if not expanded).

        Returns:
            The modal depth of the query formula.

        Raises:
            ValueError: If query has not been parsed yet.
        """
        if self.expanded_ast:
            return self.expanded_ast.modal_depth()
        elif self.formula_ast:
            return self.formula_ast.modal_depth()
        else:
            raise ValueError(f"Query not yet parsed: {self.formula_string}")

    def __str__(self) -> str:
        if self.query_id:
            return f"{self.query_id}: {self.formula_string}"
        return self.formula_string


@dataclass
class MomentNode:
    """
    A node in the moment tree (root, intermediate, or leaf).

    For TD=1 models there are only two layers: the root and leaves.
    For TD>1 models there are intermediate nodes between root and leaves.

    available_actions is inferred from the action labels on outgoing transitions
    and maps each acting agent to the list of action types available to them at
    this moment.  Agents that do not act at this moment are absent from the dict.
    """
    name: str
    parent_name: Optional[str]                    # None for root
    child_names: List[str]                        # empty for leaves
    available_actions: Dict[str, List[str]]       # agent -> [action_types]
    propositions: Set[str]                        # non-default props true here
    depth: int                                    # 0 for root

    @property
    def is_leaf(self) -> bool:
        return not self.child_names

    @property
    def is_root(self) -> bool:
        return self.parent_name is None


@dataclass
class MomentTransition:
    """
    A single edge in the moment tree.

    histories lists every history name that is undivided on this edge (i.e.,
    passes through both from_moment and to_moment without branching).
    actions contains only the agents who choose at this transition — agents
    acting at other moments are absent.
    """
    from_moment: str
    to_moment: str
    histories: List[str]              # history names undivided on this edge
    actions: Dict[str, str]           # agent -> action_type chosen here


@dataclass
class HistoryPath:
    """
    A complete history: a path from the root moment to a leaf moment.

    actions_at maps each non-leaf moment on the path to the actions chosen
    by the acting agents at that moment (only agents who act there).
    """
    name: str                                          # "h1", "h2", ...
    path: List[str]                                    # moment names root → leaf
    actions_at: Dict[str, Dict[str, str]]              # moment -> {agent: action_type}

    @property
    def leaf_moment(self) -> str:
        return self.path[-1]

    def complete_actions(self) -> Dict[str, str]:
        """Merge all per-moment actions into a single flat CGA dict."""
        result: Dict[str, str] = {}
        for acts in self.actions_at.values():
            result.update(acts)
        return result


@dataclass
class ALOModel:
    """
    ALOn model with arbitrary temporal depth.

    At each non-leaf moment a subset of agents chooses actions; different
    agents may act at different moments.  same-moment groups are built
    per moment-node: all histories that pass through a given node share
    that moment and are same-moment there.

    This is the intended long-term replacement for ALOModel.  When depth()
    returns 1 the model is behaviourally equivalent to ALOModel.
    """

    root_name: str
    moments: Dict[str, MomentNode]        # name -> MomentNode
    transitions: List[MomentTransition]
    histories: Dict[str, HistoryPath]     # name -> HistoryPath
    opposings: List[OpposingRelation]
    aliases: Dict[str, str]
    queries: List[Query]
    evaluation_history: str               # e.g. "h1"
    evaluation_moment: str                # e.g. "m" (typically root)
    target_proposition: str              # e.g. "q" or "do(sd1)"
    default_result: Optional[str] = None  # if set, labels matching this are not emitted as facts
    evaluations: List[Tuple[str, str, str]] = field(default_factory=list)
    # list of (moment, history, target_proposition) for multi-point evaluation

    def histories_through(self, moment_name: str) -> List[str]:
        """Return names of all histories whose path passes through moment_name."""
        return [h for h, hp in self.histories.items() if moment_name in hp.path]

    def get_all_agents(self) -> Set[str]:
        """Return all agent identifiers across all moments."""
        agents: Set[str] = set()
        for node in self.moments.values():
            agents.update(node.available_actions.keys())
        return agents

    def available_actions_at(self, moment_name: str) -> Dict[str, List[str]]:
        """Return the per-agent available action lists at the given moment."""
        return self.moments[moment_name].available_actions

    def depth(self) -> int:
        """Return the maximum depth of any node in the moment tree."""
        return max(node.depth for node in self.moments.values())
