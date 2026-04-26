"""Expander Transformer for ALOn formulas.

Expands defined operators into expansion axioms using `=>` syntax.
Accumulates axioms in self.axioms, returns name references.
"""

import inspect
from alo_translator.parsers.grammar_transformer import AlonTransformer


class ExpanderTransformer(AlonTransformer):
    """Expands ALOn formulas to expansion axioms.

    Overrides expansion operators to generate axioms.
    """

    def __init__(self, parser, model=None, evaluation_moment=None):
        """Initialize expander.

        Args:
            parser: Lark parser instance for recursive parsing
            model: ALOModel or LayeredALOModel (required for responsibility operators)
            evaluation_moment: For LayeredALOModel, the moment name at which operators
                are being evaluated. Determines which actions are available for xstit
                and which history CGA to use for but_for/ness. Ignored for ALOModel.
        """
        super().__init__()
        self.parser = parser
        self.model = model
        self.evaluation_moment = evaluation_moment
        self.axioms = set()  # Accumulate expansion axioms here (set for auto-deduplication)
        self.always_false_names = set()  # Predicate names that are always False (bottom)

        # Systematic formula-name counter and bidirectional mapping
        # Uses 'f' prefix to avoid collision with user-defined query IDs ('q' prefix)
        self.q_counter = 0
        self.formula_to_name = {}  # formula_string -> fname
        self.name_to_formula = {}  # fname -> formula_string

    # ========== Model abstraction helpers ==========

    def _get_agent_actions(self, agent: str):
        """Return the list of action types available to agent at the evaluation moment.

        For LayeredALOModel: uses available_actions_at(evaluation_moment).
        For ALOModel: uses the global agents_actions table.
        """
        from ..model.core import LayeredALOModel
        if isinstance(self.model, LayeredALOModel):
            if self.evaluation_moment is None:
                raise ValueError("evaluation_moment required for LayeredALOModel")
            return self.model.available_actions_at(self.evaluation_moment).get(agent, [])
        return self.model.agents_actions.get(agent)

    def _get_eval_history_cga(self) -> dict:
        """Return the {agent: action_type} mapping for the evaluation history at the evaluation moment.

        For LayeredALOModel: returns the stage actions of the evaluation history at
            evaluation_moment (only the agents acting there).
        For ALOModel: returns the full named_histories['h1'].actions.
        """
        from ..model.core import LayeredALOModel
        if isinstance(self.model, LayeredALOModel):
            if self.evaluation_moment is None:
                raise ValueError("evaluation_moment required for LayeredALOModel")
            hp = self.model.histories.get(self.model.evaluation_history)
            if hp is None:
                raise ValueError(f"Evaluation history '{self.model.evaluation_history}' not found")
            return hp.actions_at.get(self.evaluation_moment, {})
        h1 = self.model.named_histories.get("h1")
        if h1 is None:
            raise ValueError("History 'h1' not found in model")
        return h1.actions

    def _get_agent_groups(self) -> dict:
        """Return the agent_groups dict (may be empty for LayeredALOModel)."""
        return getattr(self.model, 'agent_groups', {})

    # ========== Name Generation ==========

    def _name_for(self, formula_string):
        """Generate or retrieve a systematic q-name for a formula.

        Uses a cache to return the same name for the same formula.
        Generates new q-names (q1, q2, ...) sequentially.

        Args:
            formula_string: The formula to name (as string)

        Returns:
            A q-name like "q1", "q2", etc.
        """
        # Check if we've already named this formula
        if formula_string in self.formula_to_name:
            return self.formula_to_name[formula_string]

        # Generate a new formula name (f prefix avoids collision with user query IDs)
        self.q_counter += 1
        qname = f"f{self.q_counter}"

        # Store bidirectional mapping
        self.formula_to_name[formula_string] = qname
        self.name_to_formula[qname] = formula_string

        return qname

    def _get_axiom_body(self, name):
        """Return the expansion body (LHS) for a named formula.

        Axioms are stored as "body => name". Scanning for the matching axiom
        lets callers negate the body directly rather than the name, which is
        necessary under OWA: "expansion => name" gives expansion ⊑ name, so
        ¬name ⊑ ¬expansion (not the other way). Negating the body directly
        lets the reasoner evaluate the complement as a concrete class expression.
        """
        suffix = f"=> {name}"
        for axiom in self.axioms:
            if axiom.endswith(suffix):
                return axiom[:-len(suffix)].strip()
        return None

    # ========== PDL-Style Modalities ==========

    def pdl_box(self, items):
        """[a]φ  →  [](do(a) -> Xφ)

        Adds: [](do(a) -> Xφ) => pdl_box_a_φ
        Returns: pdl_box_a_φ
        """
        action, formula = items
        expansion = f"[](do({action}) -> X{formula})"
        name = self._name_for(expansion)
        self.axioms.add(f"{expansion} => {name}")
        return name

    def pdl_diamond(self, items):
        """<a>φ  →  <>(do(a) & Xφ)

        Adds: <>(do(a) & Xφ) => pdl_diamond_a_φ
        Returns: pdl_diamond_a_φ
        """
        action, formula = items
        expansion = f"<>(do({action}) & X{formula})"
        name = self._name_for(expansion)
        self.axioms.add(f"{expansion} => {name}")
        return name

    # ========== Expected Result ==========

    def expected_result(self, items):
        """do(a) [+]-> φ  →  [](free_do(a) -> Xφ)

        Adds: [](free_do(a) -> Xφ) => expected_result_a_φ
        Returns: expected_result_a_φ
        """
        action, formula = items
        expansion = f"[](free_do({action}) -> X{formula})"
        name = self._name_for(expansion)
        self.axioms.add(f"{expansion} => {name}")
        return name

    # ========== XSTIT Operators ==========

    def xstit(self, items):
        """[I xstit]φ  →  ⋁α∈Acts_I (do(α_I) & [α_I]φ)

        For individual: (do(a1_I) & [a1_I]φ) | (do(a2_I) & [a2_I]φ) | ...
        For coalition: disjunction over Cartesian product of members' actions

        Adds: expansion => xstit_I_φ
        Returns: xstit_I_φ
        """
        agent_expr, formula = items
        name = self._name_for(f"[{agent_expr} xstit]{formula}")

        if self.model is None:
            raise ValueError("Model required for xstit operator")

        # Parse agent expression to determine individual vs group
        agents = self._parse_agent_expr(agent_expr)

        # Build disjunction over Cartesian product of agents' actions
        from itertools import product

        # Get action lists for each agent
        action_lists = []
        for agent in agents:
            agent_actions = self._get_agent_actions(agent)
            if agent_actions is None:
                raise ValueError(f"Agent {agent} not found in model")
            action_lists.append(agent_actions)

        # Generate all action combinations
        disjuncts = []
        for action_combo in product(*action_lists):
            # Build action: individual action (if single agent) or group action (if coalition)
            if len(agents) == 1:
                # Individual action: sd1
                action_str = f"{action_combo[0]}{agents[0]}"
            else:
                # Group action: {1:sd, 2:ss}
                action_dict = {agents[i]: action_combo[i] for i in range(len(agents))}
                action_str = "{" + ", ".join(f"{a}:{act}" for a, act in sorted(action_dict.items())) + "}"

            # Build do(action)
            do_expr = f"do({action_str})"

            # Build [action]φ and recursively expand
            pdl_expr = f"[{action_str}]{formula}"
            tree = self.parser.parse(pdl_expr)
            pdl_name = self.transform(tree)

            # Combine: do(action) & [action]φ
            conjunction = f"({do_expr} & {pdl_name})"
            disjuncts.append(conjunction)

        # Build final disjunction
        expansion = " v ".join(disjuncts)

        self.axioms.add(f"({expansion}) => {name}")
        return name

    def _parse_agent_expr(self, agent_expr):
        """Parse agent expression to list of agent IDs.

        Args:
            agent_expr: String like "1", "{1, 2}", or "coalition1"

        Returns:
            List of agent IDs (strings)
        """
        agent_expr = agent_expr.strip()

        # Check if it's an agent group: {1, 2}
        if agent_expr.startswith("{") and agent_expr.endswith("}"):
            # Parse agent list
            inner = agent_expr[1:-1]
            agents = [a.strip() for a in inner.split(",")]
            return agents

        # Check if it's a named agent group
        agent_groups = self._get_agent_groups()
        if agent_expr in agent_groups:
            return agent_groups[agent_expr]

        # Otherwise it's an individual agent
        return [agent_expr]

    def _get_actual_action_str(self, agent_expr, h1_cga: dict):
        """Get the actual action string for an agent or coalition from h1_cga dict.

        h1_cga: {agent: action_type} mapping for the evaluation history at the
                evaluation moment (as returned by _get_eval_history_cga()).

        For individual agents returns e.g. "sd1".
        For coalitions returns e.g. "{1:sd, 2:ss}".

        Raises ValueError if any agent in the coalition has no action in h1_cga.
        """
        agents = self._parse_agent_expr(agent_expr)
        if len(agents) == 1:
            agent = agents[0]
            action_type = h1_cga.get(agent)
            if action_type is None:
                return None  # Agent does not act at this evaluation moment
            return f"{action_type}{agent}"
        else:
            mappings = {}
            for agent in agents:
                action_type = h1_cga.get(agent)
                if action_type is None:
                    return None  # Some coalition member doesn't act at this moment
                mappings[agent] = action_type
            return "{" + ", ".join(f"{a}:{act}" for a, act in sorted(mappings.items())) + "}"

    def _parse_action_str(self, action_str):
        """Parse action string to dict of {agent: action_type}.

        For individual: "sd1" → {"1": "sd"}
        For group: "{1:sd, 2:ss}" → {"1": "sd", "2": "ss"}
        """
        action_str = action_str.strip()
        if action_str.startswith("{"):
            # Group action: {1:sd, 2:ss}
            inner = action_str[1:-1]  # remove braces
            result = {}
            for mapping in inner.split(","):
                mapping = mapping.strip()
                if ":" in mapping:
                    ag, act = mapping.split(":", 1)
                    result[ag.strip()] = act.strip()
            return result
        else:
            # Individual action: "sd1" (last char is agent, rest is action_type)
            return {action_str[-1]: action_str[:-1]}

    def dxstit(self, items):
        """[I dxstit]φ  →  [I xstit]φ & ~[]Xφ

        Adds: (xstit_name & not_settled_name) => dxstit_I_φ
        Returns: dxstit_I_φ

        Recursively expands xstit and the negation.
        """
        agent, formula = items
        name = self._name_for(f"[{agent} DXSTIT]{formula}")

        # Recursively expand: [I XSTIT]φ
        xstit_expr = f"[{agent} XSTIT]{formula}"
        tree = self.parser.parse(xstit_expr)
        xstit_name = self.transform(tree)

        # Recursively expand: ~[]Xφ
        not_settled_expr = f"~[]X{formula}"
        tree = self.parser.parse(not_settled_expr)
        not_settled_name = self.transform(tree)

        # Build dxstit expansion
        expansion = f"({xstit_name} & {not_settled_name})"
        self.axioms.add(f"{expansion} => {name}")
        return name

    # ========== Causation Operators ==========

    def but_for(self, items):
        """but(a_I, φ)  →  Xφ & ⋁γ∈CGA_I (do(γ) & ⋀β∈Alt(I) [γ_{-I,β}]~φ)

        φ actually occurs AND for some complete group action containing a_I,
        replacing I's action with any alternative would prevent φ.

        For m/h1: Xφ & do(h1) & ⋀β∈Alt(I) [h1_{-I,β}]~φ

        Adds: expansion => but_a_φ
        Returns: but_a_φ
        """
        action, formula = items
        name = self._name_for(f"but({action}, {formula})")

        if self.model is None:
            raise ValueError("Model required for but_for operator")

        h1_cga = self._get_eval_history_cga()
        if not h1_cga:
            raise ValueError("Evaluation history CGA is empty — cannot expand but_for")

        # Parse action string to get {agent: action_type} mapping
        # Works for both individual ("sd1") and group ("{1:sd, 2:ss}")
        parsed_actions = self._parse_action_str(action)

        # Build conjunction of counterfactual PDL boxes for ALL agents in action
        # For each agent and each alternative β: [h1_{-I,β}]~φ
        counterfactual_parts = []
        for ag, actual_action_type in parsed_actions.items():
            # Get all actions for this agent
            agent_actions = self._get_agent_actions(ag)
            if agent_actions is None:
                raise ValueError(f"Agent {ag} not found in model")

            # Get alternatives (all actions except the actual one)
            alternatives = [a for a in agent_actions if a != actual_action_type]

            for alt in alternatives:
                # Build h1 with this agent's action replaced by alt
                alt_actions = dict(h1_cga)
                alt_actions[ag] = alt

                # Format as group action: {1:alt, 2:action2, ...}
                group_str = "{" + ", ".join(f"{a}:{act}" for a, act in sorted(alt_actions.items())) + "}"

                # Recursively expand [{...}](~φ)
                cf_expr = f"[{group_str}](~{formula})"
                tree = self.parser.parse(cf_expr)
                cf_name = self.transform(tree)
                counterfactual_parts.append(cf_name)

        # Build do(h1) group action string
        h1_str = "{" + ", ".join(f"{a}:{act}" for a, act in sorted(h1_cga.items())) + "}"

        # Build expansion: Xφ & do(h1) & counterfactual_parts
        parts = [f"X{formula}", f"do({h1_str})"] + counterfactual_parts
        expansion = " & ".join(parts)

        self.axioms.add(f"({expansion}) => {name}")
        return name

    def ness(self, items):
        """ness(a_I, φ)  →  ⋁β_J⊇{a_I} (do(β_J) & [β_J]φ & ⋀K⊂J (~[β_K]φ))

        There exists a minimal sufficient set of actions containing a_I.
        Minimality: no proper subset (including ∅ → ~[]Xφ) is sufficient.

        For m/h1: powerset of h1 CGA containing a_I.

        Adds: expansion => ness_a_φ
        Returns: ness_a_φ
        """
        action, formula = items
        name = self._name_for(f"ness({action}, {formula})")

        if self.model is None:
            raise ValueError("Model required for ness operator")

        h1_cga = self._get_eval_history_cga()
        if not h1_cga:
            raise ValueError("Evaluation history CGA is empty — cannot expand ness")

        # Parse action string to get {agent: action_type} mapping
        # Works for both individual ("sd1") and group ("{1:sd, 2:ss}")
        parsed_actions = self._parse_action_str(action)

        # Get h1 CGA actions as set of (agent, action_type) tuples
        h1_actions = set(h1_cga.items())  # {('1', 'sd'), ('2', 'ha')}
        target_actions = set(parsed_actions.items())  # {('1', 'sd')} or {('1', 'sd'), ('2', 'ss')}

        # Generate powerset of h1 actions, filter to subsets containing ALL target actions
        from itertools import chain, combinations

        def powerset(iterable):
            "powerset([1,2,3]) --> () (1,) (2,) (3,) (1,2) (1,3) (2,3) (1,2,3)"
            s = list(iterable)
            return chain.from_iterable(combinations(s, r) for r in range(len(s)+1))

        # Get all subsets containing all target actions
        relevant_subsets = [
            list(subset) for subset in powerset(h1_actions)
            if target_actions.issubset(set(subset))
        ]

        # Build disjunction over all relevant subsets
        disjuncts = []
        for J in relevant_subsets:
            # Build do(a_I) - always check the action we're testing, not the full set J
            # NESS: a_I is an element of minimal sufficient set J
            do_expr = f"do({action})"

            # Build [J]φ and recursively expand
            if len(J) == 1:
                a, act = J[0]
                sufficient_expr = f"[{act}{a}]{formula}"
            else:
                group_str = "{" + ", ".join(f"{a}:{act}" for a, act in sorted(J)) + "}"
                sufficient_expr = f"[{group_str}]{formula}"

            tree = self.parser.parse(sufficient_expr)
            sufficient_name = self.transform(tree)

            # Build minimality checks: ⋀K⊂J (~[K]φ)
            minimality_parts = []

            # Get all proper subsets of J
            proper_subsets = [
                list(subset) for subset in powerset(J)
                if len(subset) < len(J)
            ]

            for K in proper_subsets:
                if len(K) == 0:
                    # Empty set: positive form is []Xφ
                    pos_sufficient_expr = f"[]X{formula}"
                elif len(K) == 1:
                    a, act = K[0]
                    pos_sufficient_expr = f"[{act}{a}]{formula}"
                else:
                    group_str = "{" + ", ".join(f"{a}:{act}" for a, act in sorted(K)) + "}"
                    pos_sufficient_expr = f"[{group_str}]{formula}"

                # Transform positive form to register its axiom, then build a NAMED
                # negation class. With "expansion => pos_name" (expansion ⊑ pos_name),
                # complement(pos_name) under OWA cannot be inferred from complement(expansion).
                # Instead, add "~(expansion) => neg_name" (complement(expansion) ⊑ neg_name):
                # forward direction works — reasoner sees m∉expansion → m∈neg_name.
                tree = self.parser.parse(pos_sufficient_expr)
                pos_name = self.transform(tree)
                body = self._get_axiom_body(pos_name)
                if body is not None:
                    neg_formula_str = f"~({body})"
                    neg_name = self._name_for(neg_formula_str)
                    self.axioms.add(f"{neg_formula_str} => {neg_name}")
                    minimality_parts.append(neg_name)
                else:
                    # Atom (no expansion axiom): negating the name is safe
                    minimality_parts.append(f"~{pos_name}")

            # Combine: do(J) & [J]φ & ⋀K⊂J (~[K]φ)
            parts = [do_expr, sufficient_name] + minimality_parts
            conjunction = " & ".join(parts)
            disjuncts.append(f"({conjunction})")

        # Build final disjunction
        expansion = " v ".join(disjuncts)

        self.axioms.add(f"({expansion}) => {name}")
        return name

    # ========== Responsibility Operators ==========
    # All use actual action α_I from evaluation history

    def pres(self, items):
        """[I pres]φ  →  do(α_I) & (do(α_I) [+]-> φ) & ~[]Xφ & Xφ

        Potential responsibility: I did α, α's expected result includes φ,
        φ is avoidable, and φ actually occurred.

        Adds: (do(α_I) & expected_result_name & ~[]Xφ & Xφ) => pres_I_φ
        Returns: pres_I_φ

        Note: Uses α_I notation (actual action from evaluation history).
        Looks up actual action from model's h1 history.
        """
        agent, formula = items
        name = self._name_for(f"[{agent} pres]{formula}")

        if self.model is None:
            raise ValueError("Model required for pres operator - cannot look up actual action")

        h1_cga = self._get_eval_history_cga()
        actual_action = self._get_actual_action_str(agent, h1_cga)  # e.g., "sd1" or "{1:sd, 2:ss}"
        if actual_action is None:
            self.always_false_names.add(name)  # Agent doesn't act at eval moment → always False
            return name

        # Recursively expand: do(actual_action) [+]-> φ
        expected_expr = f"do({actual_action}) [+]-> {formula}"
        tree = self.parser.parse(expected_expr)
        expected_name = self.transform(tree)  # Adds axiom, returns name

        # Build pres expansion using the expected_result name
        expansion = f"(do({actual_action}) & {expected_name} & ~[]X{formula} & X{formula})"
        self.axioms.add(f"{expansion} => {name}")
        return name

    def sres(self, items):
        """[I sres]φ  →  do(α_I) & (do(α_I) [+]-> φ) & but(α_I, φ) & ~[]Xφ & ~[]do(α_I)

        Strong responsibility: I did α, α's expected result includes φ,
        α is but-for cause of φ, φ was not inevitable, and α was not the
        only action available (freedom condition).

        Adds: (do(α_I) & expected_result_name & but_for_name & ~[]Xφ & ~[]do(α_I)) => sres_I_φ
        Returns: sres_I_φ

        Note: Uses α_I notation (actual action from evaluation history).
        Recursively expands expected_result and but_for.
        """
        agent, formula = items
        name = self._name_for(f"[{agent} sres]{formula}")

        if self.model is None:
            raise ValueError("Model required for sres operator")

        h1_cga = self._get_eval_history_cga()
        actual_action = self._get_actual_action_str(agent, h1_cga)  # e.g., "sd1" or "{1:sd, 2:ss}"
        if actual_action is None:
            self.always_false_names.add(name)  # Agent doesn't act at eval moment → always False
            return name

        # Recursively expand: do(actual_action) [+]-> φ
        expected_expr = f"do({actual_action}) [+]-> {formula}"
        tree = self.parser.parse(expected_expr)
        expected_name = self.transform(tree)

        # Recursively expand: but(actual_action, φ)
        but_expr = f"but({actual_action}, {formula})"
        tree = self.parser.parse(but_expr)
        but_name = self.transform(tree)

        # Build sres expansion (Def 3.11: add contingency ~[]Xφ and freedom ~[]do(αI))
        expansion = f"(do({actual_action}) & {expected_name} & {but_name} & ~[]X{formula} & ~[]do({actual_action}))"
        self.axioms.add(f"{expansion} => {name}")
        return name

    def res(self, items):
        """[I res]φ  →  do(α_I) & (do(α_I) [+]-> φ) & ness(α_I, φ) & ~[]Xφ & ~[]do(α_I)

        Plain responsibility: I did α, α's expected result includes φ,
        α is NESS cause of φ, φ was not inevitable, and α was not the
        only action available (freedom condition).

        Adds: (do(α_I) & expected_result_name & ness_name & ~[]Xφ & ~[]do(α_I)) => res_I_φ
        Returns: res_I_φ

        Note: Uses α_I notation (actual action from evaluation history).
        Recursively expands expected_result and ness.
        """
        agent, formula = items
        name = self._name_for(f"[{agent} res]{formula}")

        if self.model is None:
            raise ValueError("Model required for res operator")

        h1_cga = self._get_eval_history_cga()
        actual_action = self._get_actual_action_str(agent, h1_cga)  # e.g., "sd1" or "{1:sd, 2:ss}"
        if actual_action is None:
            self.always_false_names.add(name)  # Agent doesn't act at eval moment → always False
            return name

        # Recursively expand: do(actual_action) [+]-> φ
        expected_expr = f"do({actual_action}) [+]-> {formula}"
        tree = self.parser.parse(expected_expr)
        expected_name = self.transform(tree)

        # Recursively expand: ness(actual_action, φ)
        ness_expr = f"ness({actual_action}, {formula})"
        tree = self.parser.parse(ness_expr)
        ness_name = self.transform(tree)

        # Build res expansion (Def 3.11: add contingency ~[]Xφ and freedom ~[]do(αI))
        expansion = f"(do({actual_action}) & {expected_name} & {ness_name} & ~[]X{formula} & ~[]do({actual_action}))"
        self.axioms.add(f"{expansion} => {name}")
        return name
