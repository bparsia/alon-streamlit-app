"""
Formula expansion (Pass 4): Expand defined forms to primitives.

This module expands ALOn-specific operators into primitive operators according
to the expansion rules from ALON_LANGUAGE_SPEC.md.

Expansion Rules Summary (from spec lines 107-116):
- Standard operators (v, ->, <->, <>) can be expanded or kept (serializer decides)
- PDL-Box: [a1]φ → □(do(a1) → Xφ)
- PDL-Diamond: ⟨a1⟩φ → ◊(do(a1) ∧ Xφ)
- Expected Result: do(a1) [+]→ φ → □(free_do(a1) → Xφ)
- XSTIT: [I xstit]φ → ⋁α(do(αI) ∧ [αI]φ)
- DXSTIT: [I dxstit]φ → [I xstit]φ ∧ ¬□Xφ
- But-for: but(a1, φ) → Xφ ∧ ⋁γ(do(γ) ∧ ⋀β[γ-{1}β{1}]¬φ)
- NESS: ness(a1, φ) → ⋁βJ(do(βJ) ∧ [βJ]φ ∧ ⋀K⊂J(¬[βK]φ))
- Potential Resp: [1 pres]φ → ⋁α(do(α1) ∧ (do(α1) [+]→ φ)) ∧ ¬□Xφ ∧ Xφ
- Strong Resp: [1 sres]φ → ⋁α(do(α1) ∧ (do(α1) [+]→ φ) ∧ but(α1, φ) ∧ ...)
- Plain Resp: [1 res]φ → ⋁α(do(α1) ∧ (do(α1) [+]→ φ) ∧ ness(α1, φ) ∧ ...)
"""

from typing import List, Set, Dict
from alo_translator.model.formula import (
    FormulaNode, Prop, DoAction, FreeDoAction, Opposing,
    Negation, Conjunction, Disjunction, Implication, Biconditional,
    Box, Diamond, Next, Top, Bottom,
    PDLBox, PDLDiamond, ExpectedResult, ButFor, Ness,
    XSTIT, DXSTIT, PotentialResponsibility, StrongResponsibility, PlainResponsibility,
    IndividualAction, GroupAction, IndividualAgent, AgentGroup, NamedAgentGroup,
    Action, Agent,
)
from alo_translator.model.core import ALOModel


class FormulaExpander:
    """
    Expands defined operators to primitives.

    Strategy:
    - Standard operators (Disjunction, Implication, etc.) are optionally expanded
    - ALOn-specific operators are always expanded
    - Expansion is recursive - we expand bottom-up
    - Provenance is preserved through expansion
    """

    def __init__(self, model: ALOModel, expand_standard: bool = False,
                 evaluation_history: str = "h1"):
        """
        Initialize expander with model context.

        Args:
            model: The ALOModel containing agents, actions, etc.
            expand_standard: If True, expand standard operators (v, ->, <->, <>)
                            If False, leave them for serializer to handle
            evaluation_history: Which history to evaluate on (default "h1")
                               Used to look up actual actions for responsibility operators
        """
        self.model = model
        self.expand_standard = expand_standard
        self.evaluation_history = evaluation_history

    def expand(self, formula: FormulaNode) -> FormulaNode:
        """
        Recursively expand a formula to primitives.

        Args:
            formula: The formula to expand

        Returns:
            The expanded formula (all defined operators converted to primitives)
        """
        # Primitives pass through unchanged
        if isinstance(formula, (Prop, DoAction, FreeDoAction, Opposing, Top, Bottom)):
            return formula

        # Unary operators - expand child first
        if isinstance(formula, Negation):
            return Negation(self.expand(formula.formula), provenance=formula.provenance)

        if isinstance(formula, Box):
            return Box(self.expand(formula.formula), provenance=formula.provenance)

        if isinstance(formula, Next):
            return Next(self.expand(formula.formula), provenance=formula.provenance)

        # Binary operators - expand both children
        if isinstance(formula, Conjunction):
            return Conjunction(
                self.expand(formula.left),
                self.expand(formula.right),
                provenance=formula.provenance
            )

        # Standard defined operators - expand if requested
        if isinstance(formula, Diamond):
            expanded_child = self.expand(formula.formula)
            if self.expand_standard:
                # ◊φ → ¬□¬φ
                return Negation(Box(Negation(expanded_child)), provenance="diamond")
            else:
                return Diamond(expanded_child, provenance=formula.provenance)

        if isinstance(formula, Disjunction):
            left = self.expand(formula.left)
            right = self.expand(formula.right)
            if self.expand_standard:
                # φ ∨ ψ → ¬(¬φ ∧ ¬ψ)
                return Negation(
                    Conjunction(Negation(left), Negation(right)),
                    provenance="disjunction"
                )
            else:
                return Disjunction(left, right, provenance=formula.provenance)

        if isinstance(formula, Implication):
            ante = self.expand(formula.antecedent)
            cons = self.expand(formula.consequent)
            if self.expand_standard:
                # φ → ψ ≡ ¬φ ∨ ψ
                return Negation(
                    Conjunction(
                        ante,
                        Negation(cons)
                    ),
                    provenance="implication"
                )
            else:
                return Implication(ante, cons, provenance=formula.provenance)

        if isinstance(formula, Biconditional):
            left = self.expand(formula.left)
            right = self.expand(formula.right)
            if self.expand_standard:
                # φ <-> ψ ≡ (φ → ψ) ∧ (ψ → φ)
                return Conjunction(
                    self.expand(Implication(left, right)),
                    self.expand(Implication(right, left)),
                    provenance="biconditional"
                )
            else:
                return Biconditional(left, right, provenance=formula.provenance)

        # ALOn-specific operators - always expand
        if isinstance(formula, PDLBox):
            # [a1]φ → □(do(a1) → Xφ)
            expanded_formula = self.expand(formula.formula)
            # Convert action to DoAction - handle both individual and group actions
            if isinstance(formula.action, GroupAction):
                do_action = self._cga_to_do_conjunction(formula.action)
            else:
                do_action = DoAction(formula.action)
            return Box(
                Implication(
                    do_action,
                    Next(expanded_formula)
                ),
                provenance="pdl_box"
            )

        if isinstance(formula, PDLDiamond):
            # ⟨a1⟩φ → ◊(do(a1) ∧ Xφ)
            expanded_formula = self.expand(formula.formula)
            # Convert action to DoAction - handle both individual and group actions
            if isinstance(formula.action, GroupAction):
                do_action = self._cga_to_do_conjunction(formula.action)
            else:
                do_action = DoAction(formula.action)
            diamond_inner = Conjunction(
                do_action,
                Next(expanded_formula)
            )
            # Expand diamond if requested
            if self.expand_standard:
                return Negation(Box(Negation(diamond_inner)), provenance="pdl_diamond")
            else:
                return Diamond(diamond_inner, provenance="pdl_diamond")

        if isinstance(formula, ExpectedResult):
            # do(a1) [+]→ φ → □(free_do(a1) → Xφ)
            expanded_formula = self.expand(formula.formula)
            return Box(
                Implication(
                    FreeDoAction(formula.action),
                    Next(expanded_formula)
                ),
                provenance="expected_result"
            )

        if isinstance(formula, XSTIT):
            # [I xstit]φ → ⋁α(do(αI) ∧ [αI]φ)
            # This requires knowing all actions available to agent I
            return self._expand_xstit(formula)

        if isinstance(formula, DXSTIT):
            # [I dxstit]φ → [I xstit]φ ∧ ¬□Xφ
            expanded_formula = self.expand(formula.formula)
            xstit_part = self.expand(XSTIT(formula.agent, expanded_formula))
            return Conjunction(
                xstit_part,
                Negation(Box(Next(expanded_formula))),
                provenance="dxstit"
            )

        if isinstance(formula, ButFor):
            # but(a1, φ) → Xφ ∧ ⋁γ(do(γ) ∧ ⋀β[γ-{1}β{1}]¬φ)
            # This requires knowing all complete group actions
            return self._expand_but_for(formula)

        if isinstance(formula, Ness):
            # ness(a1, φ) → ⋁βJ(do(βJ) ∧ [βJ]φ ∧ ⋀K⊂J(¬[βK]φ))
            # This requires computing sufficient sets
            return self._expand_ness(formula)

        if isinstance(formula, PotentialResponsibility):
            # [I pres]φ → ⋁α(do(αI) ∧ (do(αI) [+]→ φ)) ∧ ¬□Xφ ∧ Xφ
            return self._expand_potential_responsibility(formula)

        if isinstance(formula, StrongResponsibility):
            # [I sres]φ → ⋁α(do(αI) ∧ (do(αI) [+]→ φ) ∧ but(αI, φ) ∧ ...)
            return self._expand_strong_responsibility(formula)

        if isinstance(formula, PlainResponsibility):
            # [I res]φ → ⋁α(do(αI) ∧ (do(αI) [+]→ φ) ∧ ness(αI, φ) ∧ ...)
            return self._expand_plain_responsibility(formula)

        # If we get here, something is wrong
        raise ValueError(f"Unknown formula type: {type(formula)}")

    # ========================================================================
    # Helper methods for complex expansions
    # ========================================================================

    def _expand_xstit(self, formula: XSTIT) -> FormulaNode:
        """
        Expand XSTIT: [I xstit]φ → ⋁α(do(αI) ∧ [αI]φ)

        For individual agent: iterate over their actions
        For coalition: iterate over all joint actions (CGAs restricted to coalition members)
        """
        agent = formula.agent
        expanded_formula = self.expand(formula.formula)

        if isinstance(agent, IndividualAgent):
            # Individual agent - iterate over their actions
            agent_id = agent.agent_id
            actions = self.model.agents_actions.get(agent_id, [])

            if not actions:
                return Bottom()

            disjuncts = []
            for action in actions:
                individual_action = IndividualAction(action, agent_id)
                disjunct = Conjunction(
                    DoAction(individual_action),
                    self.expand(PDLBox(individual_action, expanded_formula))
                )
                disjuncts.append(disjunct)

            result = disjuncts[0]
            for disjunct in disjuncts[1:]:
                result = Disjunction(result, disjunct)
            result.provenance = "xstit"
            return result

        elif isinstance(agent, (AgentGroup, NamedAgentGroup)):
            # Coalition - iterate over all joint actions
            # Get agent IDs in the coalition
            if isinstance(agent, AgentGroup):
                coalition_agents = set(agent.agents)
            else:  # NamedAgentGroup
                coalition_agents = set(self.model.agent_groups.get(agent.name, []))

            if not coalition_agents:
                return Bottom()

            # Generate all possible joint actions for this coalition
            # by iterating over all combinations of individual actions
            from itertools import product

            # Get actions for each agent in coalition
            agent_action_lists = []
            sorted_agents = sorted(coalition_agents)
            for agent_id in sorted_agents:
                agent_actions = self.model.agents_actions.get(agent_id, [])
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

                disjunct = Conjunction(
                    self._cga_to_do_conjunction(joint_action),
                    self.expand(PDLBox(joint_action, expanded_formula))
                )
                disjuncts.append(disjunct)

            if not disjuncts:
                return Bottom()

            result = disjuncts[0]
            for disjunct in disjuncts[1:]:
                result = Disjunction(result, disjunct)
            result.provenance = "xstit"
            return result

        else:
            return Bottom()

    def _expand_but_for(self, formula: ButFor) -> FormulaNode:
        """
        Expand but-for: but(αI, φ) → Xφ ∧ ⋁γ(do(γ) ∧ ⋀β[counterfactual]¬φ)

        Algorithm:
        1. Start with Xφ
        2. For each complete group action γ containing αI:
           - Build: do(γ) ∧ ⋀β(for all alternative actions β for agent I: [γ-{αI}∪{βI}]¬φ)
        3. Disjoin all these terms
        4. Conjoin with Xφ

        Returns: Xφ ∧ (disjunction of counterfactual checks)
        """
        expanded_formula = self.expand(formula.formula)

        # Get the tested action's agent(s) and action type(s)
        tested_action_agents = self._get_action_agents(formula.action)

        # Get all complete group actions
        all_cgas = self.model.generate_complete_group_actions()

        # Filter to only those containing the tested action
        containing_cgas = []
        for cga in all_cgas:
            if self._action_matches_cga(formula.action, cga):
                containing_cgas.append(cga)

        if not containing_cgas:
            # If no complete group actions contain this action, but-for is false
            return Conjunction(Next(expanded_formula), Bottom(), provenance="but_for")

        # For each containing CGA, build counterfactual checks
        cga_disjuncts = []
        for cga in containing_cgas:
            # Build do(cga)
            do_cga = self._cga_to_do_conjunction(cga)

            # For each agent in the tested action, build counterfactuals
            counterfactuals = []
            for agent_id in tested_action_agents:
                agent_actions = self.model.agents_actions.get(agent_id, [])
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
                        cf_check = self.expand(PDLBox(
                            counterfactual_cga,
                            Negation(expanded_formula)
                        ))
                        counterfactuals.append(cf_check)

            # Conjoin all counterfactuals for this CGA
            if counterfactuals:
                cf_conjunction = counterfactuals[0]
                for cf in counterfactuals[1:]:
                    cf_conjunction = Conjunction(cf_conjunction, cf)

                # Build: do(cga) ∧ (counterfactuals)
                cga_term = Conjunction(do_cga, cf_conjunction)
                cga_disjuncts.append(cga_term)
            else:
                # No counterfactuals (single agent, single action) - just do(cga)
                cga_disjuncts.append(do_cga)

        # Disjoin all CGA terms
        if cga_disjuncts:
            disjunction = cga_disjuncts[0]
            for term in cga_disjuncts[1:]:
                disjunction = Disjunction(disjunction, term)
        else:
            disjunction = Bottom()

        # Final: Xφ ∧ (disjunction)
        return Conjunction(
            Next(expanded_formula),
            disjunction,
            provenance="but_for"
        )

    def _expand_ness(self, formula: Ness) -> FormulaNode:
        """
        Expand NESS: ness(αI, φ) → ⋁βJ(do(βJ) ∧ [βJ]φ ∧ ⋀K⊂J(¬[βK]φ))

        Algorithm:
        1. For all group actions βJ that contain αI:
           - Check: do(βJ) ∧ [βJ]φ ∧ (all proper subsets K of βJ: ¬[βK]φ)
        2. Disjoin all these checks

        This finds minimal sufficient sets containing the tested action.
        """
        expanded_formula = self.expand(formula.formula)

        # Get the tested action's agents
        tested_action_agents = self._get_action_agents(formula.action)

        # Get all complete group actions
        all_cgas = self.model.generate_complete_group_actions()

        # Find CGAs containing the tested action
        containing_cgas = []
        for cga in all_cgas:
            if self._action_matches_cga(formula.action, cga):
                containing_cgas.append(cga)

        if not containing_cgas:
            return Bottom(provenance="ness")

        # For each CGA containing the action, generate subsets that include tested action
        from itertools import combinations

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
                    do_beta_j = self._cga_to_do_conjunction(beta_j)

                    # Part 2: [βJ]φ - βJ is sufficient for φ
                    sufficient = self.expand(PDLBox(beta_j, expanded_formula))

                    # Part 3: ⋀K⊂J(¬[βK]φ) - minimality
                    # For all proper subsets K of βJ
                    minimality_checks = []
                    for k_size in range(len(beta_j_agents)):
                        for k_agents_tuple in combinations(sorted(beta_j_agents), k_size):
                            if len(k_agents_tuple) == 0:
                                # Empty set K: check ¬[]Xφ (nothing is sufficient)
                                # [∅]φ expands to [](Top -> Xφ) = []Xφ
                                # So negation is ¬[]Xφ
                                minimality_check = Negation(Box(Next(expanded_formula)))
                                minimality_checks.append(minimality_check)
                            else:
                                # Non-empty proper subset
                                k_agents = set(k_agents_tuple)
                                beta_k = GroupAction({
                                    agent: beta_j.actions[agent]
                                    for agent in k_agents
                                })
                                # ¬[βK]φ
                                minimality_check = Negation(
                                    self.expand(PDLBox(beta_k, expanded_formula))
                                )
                                minimality_checks.append(minimality_check)

                    # Conjoin all minimality checks
                    if minimality_checks:
                        minimality = minimality_checks[0]
                        for check in minimality_checks[1:]:
                            minimality = Conjunction(minimality, check)
                    else:
                        # No proper subsets (βJ is singleton) - minimality is trivially true
                        minimality = Top()

                    # Build: do(βJ) ∧ [βJ]φ ∧ minimality
                    term = Conjunction(
                        Conjunction(do_beta_j, sufficient),
                        minimality
                    )
                    disjuncts.append(term)

        # Disjoin all terms
        if disjuncts:
            result = disjuncts[0]
            for term in disjuncts[1:]:
                result = Disjunction(result, term)
            result.provenance = "ness"
            return result
        else:
            return Bottom(provenance="ness")

    def _expand_potential_responsibility(self, formula: PotentialResponsibility) -> FormulaNode:
        """
        Expand potential responsibility:
        [I pres]φ → do(αI) ∧ (do(αI) [+]→ φ) ∧ ¬□Xφ ∧ Xφ

        where αI is the actual action performed by agent I on the evaluation history.
        """
        agent = formula.agent
        expanded_formula = self.expand(formula.formula)

        # Get actual action from evaluation history
        if self.evaluation_history not in self.model.named_histories:
            raise ValueError(
                f"Evaluation history '{self.evaluation_history}' not found in model. "
                f"Cannot expand responsibility operators."
            )

        history_profile = self.model.named_histories[self.evaluation_history]
        agent_id = self._agent_to_id(agent)

        if agent_id not in history_profile.actions:
            raise ValueError(
                f"Agent {agent_id} has no action in history '{self.evaluation_history}'. "
                f"Cannot expand [I pres]φ."
            )

        # Get the actual action performed
        action_type = history_profile.actions[agent_id]
        individual_action = IndividualAction(action_type, agent_id)

        # Build: do(αI) ∧ (do(αI) [+]→ φ) ∧ ¬□Xφ ∧ Xφ
        result = Conjunction(
            Conjunction(
                Conjunction(
                    DoAction(individual_action),
                    self.expand(ExpectedResult(individual_action, expanded_formula))
                ),
                Negation(Box(Next(expanded_formula)))
            ),
            Next(expanded_formula)
        )
        result.provenance = "pres"
        return result

    def _expand_strong_responsibility(self, formula: StrongResponsibility) -> FormulaNode:
        """
        Expand strong responsibility:
        [I sres]φ → do(αI) ∧ (do(αI) [+]→ φ) ∧ but(αI, φ)

        where αI is the actual action performed by agent I on the evaluation history.
        This is potential responsibility plus but-for causation.
        """
        agent = formula.agent
        expanded_formula = self.expand(formula.formula)

        # Get actual action from evaluation history
        if self.evaluation_history not in self.model.named_histories:
            raise ValueError(
                f"Evaluation history '{self.evaluation_history}' not found in model. "
                f"Cannot expand responsibility operators."
            )

        history_profile = self.model.named_histories[self.evaluation_history]
        agent_id = self._agent_to_id(agent)

        if agent_id not in history_profile.actions:
            raise ValueError(
                f"Agent {agent_id} has no action in history '{self.evaluation_history}'. "
                f"Cannot expand [I sres]φ."
            )

        # Get the actual action performed
        action_type = history_profile.actions[agent_id]
        individual_action = IndividualAction(action_type, agent_id)

        # Build: do(αI) ∧ (do(αI) [+]→ φ) ∧ but(αI, φ)
        result = Conjunction(
            Conjunction(
                DoAction(individual_action),
                self.expand(ExpectedResult(individual_action, expanded_formula))
            ),
            self.expand(ButFor(individual_action, expanded_formula))
        )
        result.provenance = "sres"
        return result

    def _expand_plain_responsibility(self, formula: PlainResponsibility) -> FormulaNode:
        """
        Expand plain responsibility:
        [I res]φ → do(αI) ∧ (do(αI) [+]→ φ) ∧ ness(αI, φ)

        This is potential responsibility plus NESS causation.
        Uses the actual action from the evaluation history.
        """
        agent = formula.agent
        expanded_formula = self.expand(formula.formula)

        # Get actual action from evaluation history
        if self.evaluation_history not in self.model.named_histories:
            raise ValueError(
                f"Evaluation history '{self.evaluation_history}' not found in model. "
                f"Cannot expand responsibility operators."
            )

        history_profile = self.model.named_histories[self.evaluation_history]
        agent_id = self._agent_to_id(agent)

        if agent_id not in history_profile.actions:
            raise ValueError(
                f"Agent {agent_id} has no action in history '{self.evaluation_history}'. "
                f"Cannot expand [I res]φ."
            )

        # Get the actual action performed
        action_type = history_profile.actions[agent_id]
        individual_action = IndividualAction(action_type, agent_id)

        # Build: do(αI) ∧ (do(αI) [+]→ φ) ∧ ness(αI, φ)
        result = Conjunction(
            Conjunction(
                DoAction(individual_action),
                self.expand(ExpectedResult(individual_action, expanded_formula))
            ),
            self.expand(Ness(individual_action, expanded_formula))
        )

        result.provenance = "res"
        return result

    # ========================================================================
    # Utility methods
    # ========================================================================

    def _get_agent_actions(self, agent: Agent) -> List[str]:
        """Get list of actions available to an agent."""
        if isinstance(agent, IndividualAgent):
            agent_id = agent.agent_id
            return self.model.agents_actions.get(agent_id, [])
        elif isinstance(agent, NamedAgentGroup):
            # Look up named group
            if agent.name in self.model.agent_groups:
                agents = self.model.agent_groups[agent.name]
                # Return union of all actions
                actions = set()
                for agent_id in agents:
                    actions.update(self.model.agents_actions.get(agent_id, []))
                return sorted(actions)
        elif isinstance(agent, AgentGroup):
            # Return union of actions for all agents in group
            actions = set()
            for agent_id in agent.agents:
                actions.update(self.model.agents_actions.get(agent_id, []))
            return sorted(actions)
        return []

    def _agent_to_id(self, agent: Agent) -> str:
        """Convert agent to string ID."""
        if isinstance(agent, IndividualAgent):
            return agent.agent_id
        # For groups, return first agent (this is a simplification)
        elif isinstance(agent, AgentGroup):
            return agent.agents[0] if agent.agents else "1"
        elif isinstance(agent, NamedAgentGroup):
            if agent.name in self.model.agent_groups:
                agents = self.model.agent_groups[agent.name]
                return agents[0] if agents else "1"
        return "1"  # Default fallback

    def _get_action_agents(self, action: Action) -> Set[str]:
        """Get set of agent IDs from an action."""
        if isinstance(action, IndividualAction):
            return {action.agent}
        elif isinstance(action, GroupAction):
            return set(action.actions.keys())
        return set()

    def _action_matches_cga(self, action: Action, cga: GroupAction) -> bool:
        """Check if an action matches (is contained in) a complete group action."""
        if isinstance(action, IndividualAction):
            # Check if this agent's action in CGA matches
            return cga.actions.get(action.agent) == action.action_type
        elif isinstance(action, GroupAction):
            # Check if all agents' actions match
            for agent, action_type in action.actions.items():
                if cga.actions.get(agent) != action_type:
                    return False
            return True
        return False

    def _cga_to_do_conjunction(self, cga: GroupAction) -> FormulaNode:
        """Convert a complete/group action to a conjunction of DoAction predicates."""
        actions = []
        for agent, action_type in sorted(cga.actions.items()):
            actions.append(DoAction(IndividualAction(action_type, agent)))

        if not actions:
            return Top()

        result = actions[0]
        for action in actions[1:]:
            result = Conjunction(result, action)
        return result


def expand_formula(formula: FormulaNode, model: ALOModel, expand_standard: bool = False,
                   evaluation_history: str = "h1") -> FormulaNode:
    """
    Convenience function to expand a formula.

    Args:
        formula: The formula to expand
        model: The ALOModel for context
        expand_standard: Whether to expand standard operators
        evaluation_history: Which history to evaluate on (default "h1")

    Returns:
        The expanded formula
    """
    expander = FormulaExpander(model, expand_standard=expand_standard,
                               evaluation_history=evaluation_history)
    return expander.expand(formula)
