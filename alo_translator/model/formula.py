"""
Unified FormulaNode IR for ALOn formulae.

This module provides a compositional intermediate representation for ALOn
formulae with modal depth calculation built into each node type.
"""

from dataclasses import dataclass
from typing import Optional, Union, List, Dict, TYPE_CHECKING
from abc import ABC, abstractmethod

# Forward declarations for type hints
if TYPE_CHECKING:
    from alo_translator.parsers.formula_expander import HierarchicalExpander


class FormulaNode(ABC):
    """Base class for all formula AST nodes."""

    provenance: Optional[str] = None  # Track source construct (e.g., "pres", "expected_result")

    @abstractmethod
    def modal_depth(self) -> int:
        """
        Calculate modal depth (number of nested X operators in expansion).

        Returns:
            The maximum nesting depth of X (Next) operators when this formula
            is fully expanded to primitives.
        """
        pass

    @abstractmethod
    def __eq__(self, other) -> bool:
        """Structural equality for testing."""
        pass

    @abstractmethod
    def __str__(self) -> str:
        """
        Canonical string representation (used as registry key).

        This should be a consistent, normalized representation that serves
        as the unique identifier for this formula in the registry.
        """
        pass

    @abstractmethod
    def to_owl_name(self) -> str:
        """
        Generate OWL class name using ALOn syntax.

        Returns:
            A valid OWL class name representing this formula using actual
            ALOn syntax (e.g., "Xq", "do_sd1", "1_pres_q").
        """
        pass

    def needs_expansion(self) -> bool:
        """
        Does this formula need to be expanded?

        Returns:
            True if this is a defined operator that needs expansion to primitives.
            False for primitive operators and standard boolean/modal operators.
        """
        return False  # Default: primitives don't need expansion

    def expand(self, expander: 'HierarchicalExpander') -> 'FormulaNode':
        """
        Expand this formula one level.

        For primitives, returns self.
        For defined operators, returns expansion and registers subformulas.

        Args:
            expander: The HierarchicalExpander instance with registry and model context

        Returns:
            The expanded formula (one level of expansion)
        """
        return self  # Default: primitives return themselves

    def should_be_named(self) -> bool:
        """
        Should this formula get a NamedFormula reference when appearing as a subformula?

        This determines whether a formula should be added to the registry and referenced
        by name, or kept inline in the expansion tree.

        Returns:
            True: Modal primitives (Next, Box), defined operators (ExpectedResult, NESS, etc.),
                  and special cases like FreeDoAction
            False: Structural connectives (Implication, Conjunction), basic primitives (Prop, DoAction)
        """
        return False  # Default: structural connectives and basic primitives are inlined


# ============================================================================
# Action and Agent Types (unified from model/core.py)
# ============================================================================

@dataclass(frozen=True)
class IndividualAction:
    """An individual action performed by a single agent (e.g., 'sd1')."""
    action_type: str  # e.g., "sd"
    agent: str        # e.g., "1"
    
    def __str__(self) -> str:
        return f"{self.action_type}{self.agent}"


@dataclass(frozen=True)
class GroupAction:
    """A group action - mapping from agents to their chosen actions."""
    actions: Dict[str, str]  # agent -> action_type
    
    def to_individual_actions(self) -> List[IndividualAction]:
        """Convert to list of IndividualAction objects."""
        return [IndividualAction(action_type, agent) 
                for agent, action_type in sorted(self.actions.items())]
    
    def __str__(self) -> str:
        items = ', '.join(f"{a}:{act}" for a, act in sorted(self.actions.items()))
        return f"{{{items}}}"


# Type alias for action (individual or group)
Action = Union[IndividualAction, GroupAction]


@dataclass(frozen=True)
class IndividualAgent:
    """An individual agent (e.g., '1')."""
    agent_id: str
    
    def __str__(self) -> str:
        return self.agent_id


@dataclass(frozen=True)
class AgentGroup:
    """A group of agents (e.g., '{1, 2}')."""
    agents: List[str]
    
    def __str__(self) -> str:
        return "{" + ", ".join(sorted(self.agents)) + "}"


@dataclass(frozen=True)
class NamedAgentGroup:
    """A named agent group reference (e.g., 'Ag' for all agents)."""
    name: str
    
    def __str__(self) -> str:
        return self.name


# Type alias for agent (individual, group, or named)
Agent = Union[IndividualAgent, AgentGroup, NamedAgentGroup]


# ============================================================================
# Primitive FormulaNode Types (Definition 3.3)
# ============================================================================

@dataclass
class Prop(FormulaNode):
    """Propositional atom."""
    symbol: str
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return 0

    def __eq__(self, other) -> bool:
        return isinstance(other, Prop) and self.symbol == other.symbol

    def __str__(self) -> str:
        return self.symbol

    def to_owl_name(self) -> str:
        return self.symbol


@dataclass
class NamedFormula(FormulaNode):
    """Reference to a named formula in the registry by its key."""
    formula_key: str
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return 0  # References don't contribute to modal depth

    def __eq__(self, other) -> bool:
        return isinstance(other, NamedFormula) and self.formula_key == other.formula_key

    def __str__(self) -> str:
        return f"@{self.formula_key}"

    def to_owl_name(self) -> str:
        return f"ref_{self.formula_key}"

    def needs_expansion(self) -> bool:
        return False  # References don't need expansion


@dataclass
class DoAction(FormulaNode):
    """Action execution predicate: do(a1) or do({sd1, ss2})."""
    action: Action
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return 0

    def __eq__(self, other) -> bool:
        return isinstance(other, DoAction) and self.action == other.action

    def __str__(self) -> str:
        return f"do({self.action})"

    def to_owl_name(self) -> str:
        # Actions are just their names (e.g., "sd1", not "do_sd1")
        if isinstance(self.action, IndividualAction):
            return f"{self.action.action_type}{self.action.agent}"
        else:  # GroupAction
            # For group actions, concatenate all individual actions
            parts = [f"{act}{ag}" for ag, act in sorted(self.action.actions.items())]
            return f"{'_'.join(parts)}"


@dataclass
class FreeDoAction(FormulaNode):
    """Doing unopposed: free_do(a1) - primitive after expansion."""
    action: Action
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return 0

    def __eq__(self, other) -> bool:
        return isinstance(other, FreeDoAction) and self.action == other.action

    def __str__(self) -> str:
        return f"free_do({self.action})"

    def to_owl_name(self) -> str:
        # Convert action to OWL-safe name
        # Action has action_type and agent fields
        return f"free_do_{self.action.action_type}{self.action.agent}"

    def should_be_named(self) -> bool:
        """FreeDoAction should get a named reference (special case for readability)."""
        return True


@dataclass
class Opposing(FormulaNode):
    """Opposing relation: a1 |> a2."""
    opposed: Action
    opposing: Action
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return 0

    def __eq__(self, other) -> bool:
        return (isinstance(other, Opposing) and
                self.opposed == other.opposed and
                self.opposing == other.opposing)

    def __str__(self) -> str:
        return f"{self.opposing} |> {self.opposed}"

    def to_owl_name(self) -> str:
        # Replace |> with "opposes" for OWL-safe name
        return f"{self.opposing}_opposes_{self.opposed}".replace("|>", "opposes")


@dataclass
class Negation(FormulaNode):
    """Negation: ~φ."""
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth()

    def __eq__(self, other) -> bool:
        return isinstance(other, Negation) and self.formula == other.formula

    def __str__(self) -> str:
        return f"~{self.formula}"

    def to_owl_name(self) -> str:
        return f"not_{self.formula.to_owl_name()}"


@dataclass
class Conjunction(FormulaNode):
    """Conjunction: φ & ψ."""
    left: FormulaNode
    right: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return max(self.left.modal_depth(), self.right.modal_depth())

    def __eq__(self, other) -> bool:
        return (isinstance(other, Conjunction) and
                self.left == other.left and
                self.right == other.right)

    def __str__(self) -> str:
        return f"({self.left} & {self.right})"

    def to_owl_name(self) -> str:
        return f"{self.left.to_owl_name()}_and_{self.right.to_owl_name()}"


@dataclass
class Box(FormulaNode):
    """Historical necessity: []φ."""
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth()

    def __eq__(self, other) -> bool:
        return isinstance(other, Box) and self.formula == other.formula

    def __str__(self) -> str:
        return f"[]{self.formula}"

    def to_owl_name(self) -> str:
        return f"box_{self.formula.to_owl_name()}"


@dataclass
class Next(FormulaNode):
    """Temporal next: Xφ."""
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth() + 1  # X adds 1 to depth

    def __eq__(self, other) -> bool:
        return isinstance(other, Next) and self.formula == other.formula

    def __str__(self) -> str:
        return f"X{self.formula}"

    def to_owl_name(self) -> str:
        return f"X{self.formula.to_owl_name()}"

    def needs_expansion(self) -> bool:
        return True  # Next needs translation to OWL

    def expand(self, expander: 'HierarchicalExpander') -> 'FormulaNode':
        """
        Next is primitive for expansion purposes.

        It's translated to OWL at serialization time (succ some φ),
        but doesn't need expansion in the formula tree.
        """
        # Register the inner formula
        expander.registry.register(self.formula)
        return self

    def should_be_named(self) -> bool:
        """Next operator should get a named reference."""
        return True


# ============================================================================
# Standard Defined FormulaNode Types (keep or expand per serializer)
# ============================================================================

@dataclass
class Disjunction(FormulaNode):
    """Disjunction: φ v ψ."""
    left: FormulaNode
    right: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return max(self.left.modal_depth(), self.right.modal_depth())

    def __eq__(self, other) -> bool:
        return (isinstance(other, Disjunction) and
                self.left == other.left and
                self.right == other.right)

    def __str__(self) -> str:
        return f"({self.left} v {self.right})"

    def to_owl_name(self) -> str:
        return f"{self.left.to_owl_name()}_or_{self.right.to_owl_name()}"


@dataclass
class Implication(FormulaNode):
    """Implication: φ -> ψ."""
    antecedent: FormulaNode
    consequent: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return max(self.antecedent.modal_depth(), self.consequent.modal_depth())

    def __eq__(self, other) -> bool:
        return (isinstance(other, Implication) and
                self.antecedent == other.antecedent and
                self.consequent == other.consequent)

    def __str__(self) -> str:
        return f"({self.antecedent} -> {self.consequent})"

    def to_owl_name(self) -> str:
        return f"{self.antecedent.to_owl_name()}_implies_{self.consequent.to_owl_name()}"


@dataclass
class Biconditional(FormulaNode):
    """Biconditional: φ <-> ψ."""
    left: FormulaNode
    right: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return max(self.left.modal_depth(), self.right.modal_depth())

    def __eq__(self, other) -> bool:
        return (isinstance(other, Biconditional) and
                self.left == other.left and
                self.right == other.right)

    def __str__(self) -> str:
        return f"({self.left} <-> {self.right})"

    def to_owl_name(self) -> str:
        return f"{self.left.to_owl_name()}_iff_{self.right.to_owl_name()}"


@dataclass
class Diamond(FormulaNode):
    """Historical possibility: <>φ."""
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth()

    def __eq__(self, other) -> bool:
        return isinstance(other, Diamond) and self.formula == other.formula

    def __str__(self) -> str:
        return f"<>{self.formula}"

    def to_owl_name(self) -> str:
        return f"diamond_{self.formula.to_owl_name()}"


@dataclass
class Top(FormulaNode):
    """Tautology: T."""
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return 0

    def __eq__(self, other) -> bool:
        return isinstance(other, Top)

    def __str__(self) -> str:
        return "T"

    def to_owl_name(self) -> str:
        return "Top"


@dataclass
class Bottom(FormulaNode):
    """Contradiction: _L."""
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return 0

    def __eq__(self, other) -> bool:
        return isinstance(other, Bottom)

    def __str__(self) -> str:
        return "_L"

    def to_owl_name(self) -> str:
        return "Bottom"


# ============================================================================
# ALOn-Specific Defined FormulaNode Types (expanded in Pass 4)
# ============================================================================

@dataclass
class PDLBox(FormulaNode):
    """PDL-style box modality: [a1]φ."""
    action: Action
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth() + 1  # Hidden X in expansion

    def __eq__(self, other) -> bool:
        return (isinstance(other, PDLBox) and
                self.action == other.action and
                self.formula == other.formula)

    def __str__(self) -> str:
        return f"[{self.action}]{self.formula}"

    def to_owl_name(self) -> str:
        # Use format like [sd1]q -> box_sd1_q
        action_str = str(self.action).replace("{", "").replace("}", "").replace(":", "_").replace(", ", "_")
        return f"box_{action_str}_{self.formula.to_owl_name()}"

    def needs_expansion(self) -> bool:
        return True  # PDL operators need expansion

    def expand(self, expander: 'HierarchicalExpander') -> 'FormulaNode':
        """
        Expand [a1]φ → [](do(a1) -> Xφ)
        """
        # Convert action to DoAction - handle both individual and group actions
        if isinstance(self.action, GroupAction):
            # Convert GroupAction to conjunction of DoAction predicates
            actions = []
            for agent, action_type in sorted(self.action.actions.items()):
                actions.append(DoAction(IndividualAction(action_type, agent)))

            if not actions:
                do_action = Top()
            else:
                do_action = actions[0]
                for action in actions[1:]:
                    do_action = Conjunction(do_action, action)
                    expander.registry.register(do_action)
        else:
            do_action = DoAction(self.action)

        expander.registry.register(do_action)

        # Build Next(φ)
        next_phi = Next(self.formula)
        expander.registry.register(next_phi)

        # Build Implication(do_action, Next(φ))
        impl = Implication(do_action, next_phi)
        expander.registry.register(impl)

        # Return Box with NamedFormula reference
        return Box(NamedFormula(impl.to_owl_name()))


@dataclass
class PDLDiamond(FormulaNode):
    """PDL-style diamond modality: <a1>φ."""
    action: Action
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth() + 1  # Hidden X in expansion

    def __eq__(self, other) -> bool:
        return (isinstance(other, PDLDiamond) and
                self.action == other.action and
                self.formula == other.formula)

    def __str__(self) -> str:
        return f"<{self.action}>{self.formula}"

    def to_owl_name(self) -> str:
        # Use format like <sd1>q -> diamond_sd1_q
        action_str = str(self.action).replace("{", "").replace("}", "").replace(":", "_").replace(", ", "_")
        return f"diamond_{action_str}_{self.formula.to_owl_name()}"

    def needs_expansion(self) -> bool:
        return True  # PDL operators need expansion

    def expand(self, expander: 'HierarchicalExpander') -> 'FormulaNode':
        """
        Expand <a1>φ → <>(do(a1) ∧ Xφ)
        """
        # Convert action to DoAction - handle both individual and group actions
        if isinstance(self.action, GroupAction):
            # Convert GroupAction to conjunction of DoAction predicates
            actions = []
            for agent, action_type in sorted(self.action.actions.items()):
                actions.append(DoAction(IndividualAction(action_type, agent)))

            if not actions:
                do_action = Top()
            else:
                do_action = actions[0]
                for action in actions[1:]:
                    do_action = Conjunction(do_action, action)
                    expander.registry.register(do_action)
        else:
            do_action = DoAction(self.action)

        expander.registry.register(do_action)

        # Build Next(φ)
        next_phi = Next(self.formula)
        expander.registry.register(next_phi)

        # Build Conjunction(do_action, Next(φ))
        conj = Conjunction(do_action, next_phi)
        expander.registry.register(conj)

        # Return Diamond with NamedFormula reference
        return Diamond(NamedFormula(conj.to_owl_name()))


@dataclass
class ExpectedResult(FormulaNode):
    """Expected result: do(a1) [+]-> φ."""
    action: Action
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth() + 1  # Hidden X in expansion

    def __eq__(self, other) -> bool:
        return (isinstance(other, ExpectedResult) and
                self.action == other.action and
                self.formula == other.formula)

    def __str__(self) -> str:
        return f"do({self.action}) [+]-> {self.formula}"

    def to_owl_name(self) -> str:
        # Use format like expected_sd1_q
        action_str = str(self.action).replace("{", "").replace("}", "").replace(":", "_").replace(", ", "_")
        return f"expected_{action_str}_{self.formula.to_owl_name()}"

    def needs_expansion(self) -> bool:
        return True  # Expected result needs expansion

    def expand(self, expander: 'HierarchicalExpander') -> 'FormulaNode':
        """
        Expand do(a)[+]->φ → [](free_do(a) -> Xφ)
        """
        # Build subformulas and register each
        # Build the expansion tree
        # Expander will automatically handle registering nameable subformulas
        free_do = FreeDoAction(self.action)
        next_phi = Next(self.formula)
        impl = Implication(free_do, next_phi)

        # Return Box(Implication(...))
        # The expander will process this and insert NamedFormula references where needed
        return Box(impl)

    def should_be_named(self) -> bool:
        """ExpectedResult should get a named reference."""
        return True


@dataclass
class ButFor(FormulaNode):
    """But-for causation: but(a1, φ)."""
    action: Action
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth() + 1  # X at top level + hidden X in PDL-Box

    def __eq__(self, other) -> bool:
        return (isinstance(other, ButFor) and
                self.action == other.action and
                self.formula == other.formula)

    def __str__(self) -> str:
        return f"but({self.action}, {self.formula})"

    def to_owl_name(self) -> str:
        # Use format like but_sd1_q
        action_str = str(self.action).replace("{", "").replace("}", "").replace(":", "_").replace(", ", "_")
        return f"but_{action_str}_{self.formula.to_owl_name()}"

    def needs_expansion(self) -> bool:
        return True  # But-for causation needs expansion

    def expand(self, expander: 'HierarchicalExpander') -> 'FormulaNode':
        """
        Expand but-for: but(αI, φ) → Xφ ∧ ⋁γ(do(γ) ∧ ⋀β[counterfactual]¬φ)

        Algorithm:
        1. Start with Xφ
        2. For each complete group action γ containing αI:
           - Build: do(γ) ∧ ⋀β(for all alternative actions β for agent I: [γ-{αI}∪{βI}]¬φ)
        3. Disjoin all these terms
        4. Conjoin with Xφ
        """
        # Helper: Get set of agent IDs from an action
        def get_action_agents(action: Action):
            if isinstance(action, IndividualAction):
                return {action.agent}
            elif isinstance(action, GroupAction):
                return set(action.actions.keys())
            return set()

        # Helper: Check if an action matches (is contained in) a complete group action
        def action_matches_cga(action: Action, cga: GroupAction) -> bool:
            if isinstance(action, IndividualAction):
                return cga.actions.get(action.agent) == action.action_type
            elif isinstance(action, GroupAction):
                for agent, action_type in action.actions.items():
                    if cga.actions.get(agent) != action_type:
                        return False
                return True
            return False

        # Helper: Convert CGA to conjunction of DoAction predicates
        def cga_to_do_conjunction(cga: GroupAction) -> FormulaNode:
            actions = []
            for agent, action_type in sorted(cga.actions.items()):
                actions.append(DoAction(IndividualAction(action_type, agent)))

            if not actions:
                return Top()

            result = actions[0]
            for action in actions[1:]:
                result = Conjunction(result, action)
            return result

        # Build Next(φ)
        next_phi = Next(self.formula)
        expander.registry.register(next_phi)

        # Get the tested action's agents
        tested_action_agents = get_action_agents(self.action)

        # Get all complete group actions
        all_cgas = expander.model.generate_complete_group_actions()

        # Filter to only those containing the tested action
        containing_cgas = [cga for cga in all_cgas if action_matches_cga(self.action, cga)]

        if not containing_cgas:
            # If no complete group actions contain this action, but-for is false
            return Conjunction(NamedFormula(next_phi.to_owl_name()), Bottom())

        # For each containing CGA, build counterfactual checks
        cga_disjuncts = []
        for cga in containing_cgas:
            # Build do(cga)
            do_cga = cga_to_do_conjunction(cga)
            expander.registry.register(do_cga)

            # For each agent in the tested action, build counterfactuals
            counterfactuals = []
            for agent_id in tested_action_agents:
                agent_actions = expander.model.agents_actions.get(agent_id, [])
                original_action = cga.actions.get(agent_id)

                # For each alternative action for this agent
                for alt_action in agent_actions:
                    if alt_action != original_action:
                        # Build counterfactual CGA: cga with agent's action replaced
                        counterfactual_cga = GroupAction({
                            **cga.actions,
                            agent_id: alt_action
                        })
                        # Build [counterfactual]¬φ
                        neg_phi = Negation(self.formula)
                        expander.registry.register(neg_phi)

                        cf_box = PDLBox(counterfactual_cga, neg_phi)
                        expander.registry.register(cf_box)
                        counterfactuals.append(cf_box)

            # Conjoin all counterfactuals for this CGA
            if counterfactuals:
                cf_conjunction = counterfactuals[0]
                for cf in counterfactuals[1:]:
                    cf_conjunction = Conjunction(cf_conjunction, cf)
                    expander.registry.register(cf_conjunction)

                # Build: do(cga) ∧ (counterfactuals)
                cga_term = Conjunction(do_cga, cf_conjunction)
                expander.registry.register(cga_term)
                cga_disjuncts.append(cga_term)
            else:
                # No counterfactuals (single agent, single action) - just do(cga)
                cga_disjuncts.append(do_cga)

        # Disjoin all CGA terms
        if cga_disjuncts:
            disjunction = cga_disjuncts[0]
            for term in cga_disjuncts[1:]:
                disjunction = Disjunction(disjunction, term)
                expander.registry.register(disjunction)
        else:
            disjunction = Bottom()

        expander.registry.register(disjunction)

        # Final: Xφ ∧ (disjunction) with NamedFormula references
        return Conjunction(NamedFormula(next_phi.to_owl_name()), NamedFormula(disjunction.to_owl_name()))

    def should_be_named(self) -> bool:
        """ButFor should get a named reference."""
        return True


@dataclass
class Ness(FormulaNode):
    """NESS causation: ness(a1, φ)."""
    action: Action
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth() + 1  # Hidden X in PDL-Box

    def __eq__(self, other) -> bool:
        return (isinstance(other, Ness) and
                self.action == other.action and
                self.formula == other.formula)

    def __str__(self) -> str:
        return f"ness({self.action}, {self.formula})"

    def to_owl_name(self) -> str:
        # Use format like ness_sd1_q
        action_str = str(self.action).replace("{", "").replace("}", "").replace(":", "_").replace(", ", "_")
        return f"ness_{action_str}_{self.formula.to_owl_name()}"

    def needs_expansion(self) -> bool:
        return True  # NESS causation needs expansion

    def expand(self, expander: 'HierarchicalExpander') -> 'FormulaNode':
        """
        Expand NESS: ness(αI, φ) → ⋁βJ(do(βJ) ∧ [βJ]φ ∧ ⋀K⊂J(¬[βK]φ))

        Algorithm:
        1. For all group actions βJ that contain αI:
           - Check: do(βJ) ∧ [βJ]φ ∧ (all proper subsets K of βJ: ¬[βK]φ)
        2. Disjoin all these checks

        This finds minimal sufficient sets containing the tested action.
        """
        from itertools import combinations

        # Helper: Get set of agent IDs from an action
        def get_action_agents(action: Action):
            if isinstance(action, IndividualAction):
                return {action.agent}
            elif isinstance(action, GroupAction):
                return set(action.actions.keys())
            return set()

        # Helper: Check if an action matches (is contained in) a complete group action
        def action_matches_cga(action: Action, cga: GroupAction) -> bool:
            if isinstance(action, IndividualAction):
                return cga.actions.get(action.agent) == action.action_type
            elif isinstance(action, GroupAction):
                for agent, action_type in action.actions.items():
                    if cga.actions.get(agent) != action_type:
                        return False
                return True
            return False

        # Helper: Convert CGA to conjunction of DoAction predicates
        def cga_to_do_conjunction(cga: GroupAction) -> FormulaNode:
            actions = []
            for agent, action_type in sorted(cga.actions.items()):
                actions.append(DoAction(IndividualAction(action_type, agent)))

            if not actions:
                return Top()

            result = actions[0]
            for action in actions[1:]:
                result = Conjunction(result, action)
            return result

        # Get the tested action's agents
        tested_action_agents = get_action_agents(self.action)

        # Get all complete group actions
        all_cgas = expander.model.generate_complete_group_actions()

        # Find CGAs containing the tested action
        containing_cgas = [cga for cga in all_cgas if action_matches_cga(self.action, cga)]

        if not containing_cgas:
            return Bottom()

        # For each CGA containing the action, generate subsets that include tested action
        disjuncts = []
        for cga in containing_cgas:
            cga_agents = set(cga.actions.keys())
            other_agents = cga_agents - tested_action_agents

            # Generate all subsets of other agents (powerset)
            for r in range(len(other_agents) + 1):
                for subset in combinations(sorted(other_agents), r):
                    # Build group action βJ = tested agents + this subset
                    beta_j_agents = tested_action_agents | set(subset)
                    beta_j = GroupAction({
                        agent: cga.actions[agent]
                        for agent in beta_j_agents
                    })

                    # Part 1: do(βJ)
                    do_beta_j = cga_to_do_conjunction(beta_j)
                    expander.registry.register(do_beta_j)

                    # Part 2: [βJ]φ - βJ is sufficient for φ
                    sufficient = PDLBox(beta_j, self.formula)
                    expander.registry.register(sufficient)

                    # Part 3: ⋀K⊂J(¬[βK]φ) - minimality
                    # For all proper subsets K of βJ
                    minimality_checks = []
                    for k_size in range(len(beta_j_agents)):
                        for k_agents_tuple in combinations(sorted(beta_j_agents), k_size):
                            if len(k_agents_tuple) == 0:
                                # Empty set K: check ¬[]Xφ (nothing is sufficient)
                                # [∅]φ expands to [](Top -> Xφ) = []Xφ
                                # So negation is ¬[]Xφ
                                box_next = Box(Next(self.formula))
                                expander.registry.register(box_next)
                                minimality_check = Negation(box_next)
                                expander.registry.register(minimality_check)
                                minimality_checks.append(minimality_check)
                            else:
                                # Non-empty proper subset
                                k_agents = set(k_agents_tuple)
                                beta_k = GroupAction({
                                    agent: beta_j.actions[agent]
                                    for agent in k_agents
                                })
                                # ¬[βK]φ
                                box_k = PDLBox(beta_k, self.formula)
                                expander.registry.register(box_k)
                                minimality_check = Negation(box_k)
                                expander.registry.register(minimality_check)
                                minimality_checks.append(minimality_check)

                    # Conjoin all minimality checks
                    if minimality_checks:
                        minimality = minimality_checks[0]
                        for check in minimality_checks[1:]:
                            minimality = Conjunction(minimality, check)
                            expander.registry.register(minimality)
                    else:
                        # No proper subsets (βJ is singleton) - minimality is trivially true
                        minimality = Top()

                    # Build: do(βJ) ∧ [βJ]φ ∧ minimality
                    term = Conjunction(
                        Conjunction(do_beta_j, sufficient),
                        minimality
                    )
                    expander.registry.register(term)
                    disjuncts.append(term)

        # Disjoin all terms
        if disjuncts:
            result = disjuncts[0]
            for term in disjuncts[1:]:
                result = Disjunction(result, term)
                expander.registry.register(result)
            # Return NamedFormula reference to the disjunction
            # Note: The last disjunct is already registered
            return NamedFormula(result.to_owl_name())
        else:
            return Bottom()

    def should_be_named(self) -> bool:
        """Ness should get a named reference."""
        return True


@dataclass
class XSTIT(FormulaNode):
    """XSTIT operator: [1 xstit]φ."""
    agent: Agent
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth() + 1  # Hidden X via PDL-Box

    def __eq__(self, other) -> bool:
        return (isinstance(other, XSTIT) and
                self.agent == other.agent and
                self.formula == other.formula)

    def __str__(self) -> str:
        return f"[{self.agent} xstit]{self.formula}"

    def to_owl_name(self) -> str:
        # Use format like 1_xstit_q or 1_2_xstit_q for coalitions
        agent_str = str(self.agent).replace("{", "").replace("}", "").replace(", ", "_").replace(" ", "")
        return f"{agent_str}_xstit_{self.formula.to_owl_name()}"

    def needs_expansion(self) -> bool:
        return True  # XSTIT needs expansion

    def expand(self, expander: 'HierarchicalExpander') -> 'FormulaNode':
        """
        Expand XSTIT: [I xstit]φ → ⋁α(do(αI) ∧ [αI]φ)

        For individual agent: iterate over their actions
        For coalition: iterate over all joint actions (CGAs restricted to coalition members)
        """
        from itertools import product

        agent = self.agent

        if isinstance(agent, IndividualAgent):
            # Individual agent - iterate over their actions
            agent_id = agent.agent_id
            actions = expander.model.agents_actions.get(agent_id, [])

            if not actions:
                return Bottom()

            disjuncts = []
            for action in actions:
                individual_action = IndividualAction(action, agent_id)

                do_action = DoAction(individual_action)
                expander.registry.register(do_action)

                pdl_box = PDLBox(individual_action, self.formula)
                expander.registry.register(pdl_box)

                disjunct = Conjunction(do_action, pdl_box)
                expander.registry.register(disjunct)
                disjuncts.append(disjunct)

            result = disjuncts[0]
            for disjunct in disjuncts[1:]:
                result = Disjunction(result, disjunct)
                expander.registry.register(result)
            # Return NamedFormula reference to the disjunction
            return NamedFormula(result.to_owl_name())

        elif isinstance(agent, (AgentGroup, NamedAgentGroup)):
            # Coalition - iterate over all joint actions
            # Get agent IDs in the coalition
            if isinstance(agent, AgentGroup):
                coalition_agents = set(agent.agents)
            else:  # NamedAgentGroup
                coalition_agents = set(expander.model.agent_groups.get(agent.name, []))

            if not coalition_agents:
                return Bottom()

            # Generate all possible joint actions for this coalition
            # by iterating over all combinations of individual actions
            # Get actions for each agent in coalition
            agent_action_lists = []
            sorted_agents = sorted(coalition_agents)
            for agent_id in sorted_agents:
                agent_actions = expander.model.agents_actions.get(agent_id, [])
                if not agent_actions:
                    return Bottom()  # Agent has no actions
                agent_action_lists.append(agent_actions)

            # Generate all combinations (Cartesian product)
            disjuncts = []
            for action_combo in product(*agent_action_lists):
                # Build GroupAction for this combination
                joint_action = GroupAction({
                    agent_id: action_type
                    for agent_id, action_type in zip(sorted_agents, action_combo)
                })

                # Convert GroupAction to conjunction of DoAction predicates
                do_actions = []
                for agent_id, action_type in sorted(joint_action.actions.items()):
                    do_actions.append(DoAction(IndividualAction(action_type, agent_id)))

                do_cga = do_actions[0]
                for action in do_actions[1:]:
                    do_cga = Conjunction(do_cga, action)
                    expander.registry.register(do_cga)
                expander.registry.register(do_cga)

                pdl_box = PDLBox(joint_action, self.formula)
                expander.registry.register(pdl_box)

                disjunct = Conjunction(do_cga, pdl_box)
                expander.registry.register(disjunct)
                disjuncts.append(disjunct)

            if not disjuncts:
                return Bottom()

            result = disjuncts[0]
            for disjunct in disjuncts[1:]:
                result = Disjunction(result, disjunct)
                expander.registry.register(result)
            # Return NamedFormula reference to the disjunction
            return NamedFormula(result.to_owl_name())

        else:
            return Bottom()


@dataclass
class DXSTIT(FormulaNode):
    """Deliberative XSTIT: [1 dxstit]φ."""
    agent: Agent
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth() + 1  # Hidden X via XSTIT

    def __eq__(self, other) -> bool:
        return (isinstance(other, DXSTIT) and
                self.agent == other.agent and
                self.formula == other.formula)

    def __str__(self) -> str:
        return f"[{self.agent} dxstit]{self.formula}"

    def to_owl_name(self) -> str:
        # Use format like 1_dxstit_q or 1_2_dxstit_q for coalitions
        agent_str = str(self.agent).replace("{", "").replace("}", "").replace(", ", "_").replace(" ", "")
        return f"{agent_str}_dxstit_{self.formula.to_owl_name()}"

    def needs_expansion(self) -> bool:
        return True  # DXSTIT needs expansion

    def expand(self, expander: 'HierarchicalExpander') -> 'FormulaNode':
        """
        Expand [I dxstit]φ → [I xstit]φ ∧ ¬□Xφ
        """
        # Build XSTIT part
        xstit = XSTIT(self.agent, self.formula)
        expander.registry.register(xstit)

        # Build ¬□Xφ part
        next_phi = Next(self.formula)
        expander.registry.register(next_phi)

        box_next = Box(next_phi)
        expander.registry.register(box_next)

        not_box = Negation(box_next)
        expander.registry.register(not_box)

        # Return conjunction with NamedFormula references
        return Conjunction(NamedFormula(xstit.to_owl_name()), NamedFormula(not_box.to_owl_name()))


@dataclass
class PotentialResponsibility(FormulaNode):
    """Potential responsibility: [1 pres]φ."""
    agent: Agent
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth() + 1  # Multiple X in expansion

    def __eq__(self, other) -> bool:
        return (isinstance(other, PotentialResponsibility) and
                self.agent == other.agent and
                self.formula == other.formula)

    def __str__(self) -> str:
        return f"[{self.agent} pres]{self.formula}"

    def to_owl_name(self) -> str:
        # Use format like 1_pres_q or 1_2_pres_q for coalitions
        agent_str = str(self.agent).replace("{", "").replace("}", "").replace(", ", "_").replace(" ", "")
        return f"{agent_str}_pres_{self.formula.to_owl_name()}"

    def needs_expansion(self) -> bool:
        return True  # Potential responsibility needs expansion

    def expand(self, expander: 'HierarchicalExpander') -> 'FormulaNode':
        """
        Expand [I pres]φ → do(α_I) ∧ expected(α_I, φ) ∧ ~[]Xφ ∧ Xφ

        Note: For evaluation at m/h1, we use the actual action from the
        designated evaluation history.
        """
        # Get agent ID
        if isinstance(self.agent, IndividualAgent):
            agent_id = self.agent.agent_id
        elif isinstance(self.agent, AgentGroup):
            agent_id = self.agent.agents[0] if self.agent.agents else "1"
        elif isinstance(self.agent, NamedAgentGroup):
            if self.agent.name in expander.model.agent_groups:
                agents = expander.model.agent_groups[self.agent.name]
                agent_id = agents[0] if agents else "1"
            else:
                agent_id = "1"
        else:
            agent_id = "1"

        # Get actual action from evaluation history
        if expander.evaluation_history not in expander.model.named_histories:
            raise ValueError(
                f"Evaluation history '{expander.evaluation_history}' not found in model. "
                f"Cannot expand [I pres]φ."
            )

        history = expander.model.named_histories[expander.evaluation_history]
        if agent_id not in history.actions:
            raise ValueError(
                f"Agent {agent_id} has no action in history '{expander.evaluation_history}'. "
                f"Cannot expand [I pres]φ."
            )

        action_type = history.actions[agent_id]
        action = IndividualAction(action_type, agent_id)

        # Build subformulas and register each
        do_a = DoAction(action)
        expander.registry.register(do_a)

        next_phi = Next(self.formula)
        expander.registry.register(next_phi)

        expected = ExpectedResult(action, self.formula)
        expander.registry.register(expected)

        box_next = Box(next_phi)
        expander.registry.register(box_next)

        not_box = Negation(box_next)
        expander.registry.register(not_box)

        # Build conjunction with NamedFormula references: do(α_I) ∧ expected(α_I, φ) ∧ ~[]Xφ ∧ Xφ
        return Conjunction(
            Conjunction(
                Conjunction(
                    NamedFormula(do_a.to_owl_name()),
                    NamedFormula(expected.to_owl_name())
                ),
                NamedFormula(not_box.to_owl_name())
            ),
            NamedFormula(next_phi.to_owl_name())
        )

    def should_be_named(self) -> bool:
        """PotentialResponsibility should get a named reference."""
        return True


@dataclass
class StrongResponsibility(FormulaNode):
    """Strong responsibility: [1 sres]φ."""
    agent: Agent
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth() + 1  # Multiple X in expansion

    def __eq__(self, other) -> bool:
        return (isinstance(other, StrongResponsibility) and
                self.agent == other.agent and
                self.formula == other.formula)

    def __str__(self) -> str:
        return f"[{self.agent} sres]{self.formula}"

    def to_owl_name(self) -> str:
        # Use format like 1_sres_q or 1_2_sres_q for coalitions
        agent_str = str(self.agent).replace("{", "").replace("}", "").replace(", ", "_").replace(" ", "")
        return f"{agent_str}_sres_{self.formula.to_owl_name()}"

    def needs_expansion(self) -> bool:
        return True  # Strong responsibility needs expansion

    def expand(self, expander: 'HierarchicalExpander') -> 'FormulaNode':
        """
        Expand strong responsibility:
        [I sres]φ → do(αI) ∧ (do(αI) [+]→ φ) ∧ but(αI, φ)

        where αI is the actual action performed by agent I on the evaluation history.
        This is potential responsibility plus but-for causation.
        """
        # Get agent ID
        if isinstance(self.agent, IndividualAgent):
            agent_id = self.agent.agent_id
        elif isinstance(self.agent, AgentGroup):
            agent_id = self.agent.agents[0] if self.agent.agents else "1"
        elif isinstance(self.agent, NamedAgentGroup):
            if self.agent.name in expander.model.agent_groups:
                agents = expander.model.agent_groups[self.agent.name]
                agent_id = agents[0] if agents else "1"
            else:
                agent_id = "1"
        else:
            agent_id = "1"

        # Get actual action from evaluation history
        if expander.evaluation_history not in expander.model.named_histories:
            raise ValueError(
                f"Evaluation history '{expander.evaluation_history}' not found in model. "
                f"Cannot expand [I sres]φ."
            )

        history = expander.model.named_histories[expander.evaluation_history]
        if agent_id not in history.actions:
            raise ValueError(
                f"Agent {agent_id} has no action in history '{expander.evaluation_history}'. "
                f"Cannot expand [I sres]φ."
            )

        action_type = history.actions[agent_id]
        action = IndividualAction(action_type, agent_id)

        # Build subformulas and register each
        do_a = DoAction(action)
        expander.registry.register(do_a)

        expected = ExpectedResult(action, self.formula)
        expander.registry.register(expected)

        but_for = ButFor(action, self.formula)
        expander.registry.register(but_for)

        # Build: do(αI) ∧ (do(αI) [+]→ φ) ∧ but(αI, φ) with NamedFormula references
        return Conjunction(
            Conjunction(NamedFormula(do_a.to_owl_name()), NamedFormula(expected.to_owl_name())),
            NamedFormula(but_for.to_owl_name())
        )

    def should_be_named(self) -> bool:
        """StrongResponsibility should get a named reference."""
        return True


@dataclass
class PlainResponsibility(FormulaNode):
    """Plain responsibility: [1 res]φ."""
    agent: Agent
    formula: FormulaNode
    provenance: Optional[str] = None

    def modal_depth(self) -> int:
        return self.formula.modal_depth() + 1  # Multiple X in expansion

    def __eq__(self, other) -> bool:
        return (isinstance(other, PlainResponsibility) and
                self.agent == other.agent and
                self.formula == other.formula)

    def __str__(self) -> str:
        return f"[{self.agent} res]{self.formula}"

    def to_owl_name(self) -> str:
        # Use format like 1_res_q or 1_2_res_q for coalitions
        agent_str = str(self.agent).replace("{", "").replace("}", "").replace(", ", "_").replace(" ", "")
        return f"{agent_str}_res_{self.formula.to_owl_name()}"

    def needs_expansion(self) -> bool:
        return True  # Plain responsibility needs expansion

    def expand(self, expander: 'HierarchicalExpander') -> 'FormulaNode':
        """
        Expand plain responsibility:
        [I res]φ → do(αI) ∧ (do(αI) [+]→ φ) ∧ ness(αI, φ)

        This is potential responsibility plus NESS causation.
        Uses the actual action from the evaluation history.
        """
        # Get agent ID
        if isinstance(self.agent, IndividualAgent):
            agent_id = self.agent.agent_id
        elif isinstance(self.agent, AgentGroup):
            agent_id = self.agent.agents[0] if self.agent.agents else "1"
        elif isinstance(self.agent, NamedAgentGroup):
            if self.agent.name in expander.model.agent_groups:
                agents = expander.model.agent_groups[self.agent.name]
                agent_id = agents[0] if agents else "1"
            else:
                agent_id = "1"
        else:
            agent_id = "1"

        # Get actual action from evaluation history
        if expander.evaluation_history not in expander.model.named_histories:
            raise ValueError(
                f"Evaluation history '{expander.evaluation_history}' not found in model. "
                f"Cannot expand [I res]φ."
            )

        history = expander.model.named_histories[expander.evaluation_history]
        if agent_id not in history.actions:
            raise ValueError(
                f"Agent {agent_id} has no action in history '{expander.evaluation_history}'. "
                f"Cannot expand [I res]φ."
            )

        action_type = history.actions[agent_id]
        action = IndividualAction(action_type, agent_id)

        # Build subformulas and register each
        do_a = DoAction(action)
        expander.registry.register(do_a)

        expected = ExpectedResult(action, self.formula)
        expander.registry.register(expected)

        ness = Ness(action, self.formula)
        expander.registry.register(ness)

        # Build: do(αI) ∧ (do(αI) [+]→ φ) ∧ ness(αI, φ) with NamedFormula references
        return Conjunction(
            Conjunction(NamedFormula(do_a.to_owl_name()), NamedFormula(expected.to_owl_name())),
            NamedFormula(ness.to_owl_name())
        )

    def should_be_named(self) -> bool:
        """PlainResponsibility should get a named reference."""
        return True
