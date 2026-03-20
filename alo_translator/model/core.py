"""
Core model classes for ALOn structures.

This module defines the object model for ALOn (Action Logic with Opposing),
providing a clean API for constructing and manipulating models programmatically.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Union


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
class ALOModel:
    """
    Complete ALOn model specification.

    This represents a 1-step branching-time model with:
    - A current moment (conventionally "m")
    - One history per complete group action
    - One successor moment per history
    - Opposing relations between actions
    - Results (propositions true at successors)
    - Queries to evaluate
    """

    # Core structure
    agents_actions: Dict[str, List[str]]  # agent -> list of action types

    # Optional sections
    aliases: Dict[str, str] = field(default_factory=dict)  # symbol -> description
    agent_groups: Dict[str, List[str]] = field(default_factory=dict)  # group name -> list of agents
    opposings: List[OpposingRelation] = field(default_factory=list)
    named_histories: Dict[str, GroupAction] = field(default_factory=dict)  # name -> group action
    results: List[Result] = field(default_factory=list)
    queries: List[Query] = field(default_factory=list)
    responsibility_config: Optional['ResponsibilityConfig'] = None  # Auto-gen config

    def get_all_agents(self) -> Set[str]:
        """Get all agent identifiers"""
        return set(self.agents_actions.keys())

    def get_all_action_types(self) -> Set[str]:
        """Get all action types (without agents)"""
        action_types = set()
        for actions in self.agents_actions.values():
            action_types.update(actions)
        return action_types

    def get_all_actions(self) -> List[Action]:
        """Get all individual actions (action type + agent combinations)"""
        actions = []
        for agent, action_types in self.agents_actions.items():
            for action_type in action_types:
                actions.append(Action(action_type, agent))
        return actions

    def generate_complete_group_actions(self) -> List[GroupAction]:
        """
        Generate all complete group actions.

        Returns one GroupAction for each combination of agent choices.
        """
        from itertools import product

        agents = sorted(self.agents_actions.keys())
        action_lists = [self.agents_actions[agent] for agent in agents]

        complete_actions = []
        for combo in product(*action_lists):
            cga = GroupAction({agents[i]: combo[i] for i in range(len(agents))})
            complete_actions.append(cga)

        return complete_actions

    def complete(self, target_prop: str = "q", eval_history: str = "h1") -> None:
        """
        Complete the partial model in place.

        - Names all unnamed complete group actions (h2, h3, …)
        - Adds default results for every unspecified history:
            eval_history → target_prop is True
            all others   → target_prop is False (~target_prop)
        """
        import re

        # Name every CGA that doesn't already have a history name
        history_counter = 1
        for cga in self.generate_complete_group_actions():
            if not any(ga.actions == cga.actions for ga in self.named_histories.values()):
                while f"h{history_counter}" in self.named_histories:
                    history_counter += 1
                self.named_histories[f"h{history_counter}"] = cga
                history_counter += 1

        # Default results for histories with no explicit result
        existing = {r.history_name for r in self.results}
        moment_counter = 1
        for result in self.results:
            if result.moment_name:
                m = re.match(r'm(\d+)', result.moment_name)
                if m:
                    moment_counter = max(moment_counter, int(m.group(1)) + 1)

        for hist_name in self.named_histories:
            if hist_name not in existing:
                props = {target_prop} if hist_name == eval_history else {f"~{target_prop}"}
                self.results.append(Result(hist_name, props, f"m{moment_counter}"))
                moment_counter += 1

    def get_all_propositions(self) -> Set[str]:
        """Get all proposition symbols mentioned in results"""
        props = set()
        for result in self.results:
            props.update(result.true_propositions)
        return props

    def max_modal_depth(self) -> int:
        """
        Get the maximum modal depth across all queries in the model.

        Returns:
            The maximum modal depth, or 0 if no queries.

        Raises:
            ValueError: If any query has not been parsed yet.
        """
        if not self.queries:
            return 0
        return max(query.modal_depth for query in self.queries)
