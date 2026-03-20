"""PyDatalog Expander Transformer for ALOn formulas.

Extends ExpanderTransformer to generate pyDatalog-compatible axioms
by eliminating implications and disjunctions that pyDatalog cannot handle.
"""

from .expander_transformer import ExpanderTransformer


class PyDatalogExpanderTransformer(ExpanderTransformer):
    """Expander that generates pyDatalog-compatible axioms.

    Overrides operators that generate disjunctions to produce
    multiple axioms or named implications instead.

    PyDatalog does NOT support the | operator anywhere, so we must:
    1. Name implications and create multiple rules
    2. Split top-level disjunctions into separate axioms
    """

    def pdl_box(self, items):
        """[a]φ  →  [](imp_a_φ) where imp_a_φ is named implication

        Strategy: Name the implication and create multiple rules.

        Instead of:
            [](do(a) -> Xφ) => pdl_box_a_φ

        Generate:
            ~do(a) => imp_do_a_Xφ
            Xφ => imp_do_a_Xφ
            []imp_do_a_Xφ => pdl_box_a_φ

        Returns:
            pdl_box_a_φ (name)
        """
        action, formula = items

        # Name the implication: do(a) -> Xφ
        imp_name = self._name_for(f"imp_do({action})_X{formula}")

        # Generate two axioms for the implication (modeling ~do(a) | Xφ)
        self.axioms.add(f"~do({action}) => {imp_name}")
        self.axioms.add(f"X{formula} => {imp_name}")

        # Now generate the box axiom
        expansion = f"[]{imp_name}"
        name = self._name_for(expansion)
        self.axioms.add(f"{expansion} => {name}")
        return name

    def expected_result(self, items):
        """do(a) [+]-> φ  →  [](imp_free_a_φ) where imp_free_a_φ is named

        Strategy: Similar to pdl_box but for free_do.

        Generate:
            ~free_do(a) => imp_free_do_a_Xφ
            Xφ => imp_free_do_a_Xφ
            []imp_free_do_a_Xφ => expected_result_a_φ

        Returns:
            expected_result_a_φ (name)
        """
        action, formula = items

        # Name the implication: free_do(a) -> Xφ
        imp_name = self._name_for(f"imp_free_do({action})_X{formula}")

        # Generate two axioms for the implication
        self.axioms.add(f"~free_do({action}) => {imp_name}")
        self.axioms.add(f"X{formula} => {imp_name}")

        # Generate the box axiom
        expansion = f"[]{imp_name}"
        name = self._name_for(expansion)
        self.axioms.add(f"{expansion} => {name}")
        return name

    def xstit(self, items):
        """[I xstit]φ  →  Multiple axioms (one per disjunct)

        Strategy: Generate one axiom per action combination.

        Instead of:
            (do(a1) & [a1]φ) v (do(a2) & [a2]φ) => xstit_I_φ

        Generate:
            (do(a1) & [a1]φ) => xstit_I_φ
            (do(a2) & [a2]φ) => xstit_I_φ

        Returns:
            xstit_I_φ (name)
        """
        agent_expr, formula = items
        name = self._name_for(f"[{agent_expr} xstit]{formula}")

        if self.model is None:
            raise ValueError("Model required for xstit operator")

        agents = self._parse_agent_expr(agent_expr)

        # Build disjunction over Cartesian product of agents' actions
        from itertools import product
        action_lists = []
        for agent in agents:
            agent_actions = self.model.agents_actions.get(agent)
            if agent_actions is None:
                raise ValueError(f"Agent {agent} not found in model")
            action_lists.append(agent_actions)

        # Generate one axiom per action combination
        for action_combo in product(*action_lists):
            # Build action string
            if len(agents) == 1:
                action_str = f"{action_combo[0]}{agents[0]}"
            else:
                action_dict = {agents[i]: action_combo[i] for i in range(len(agents))}
                action_str = "{" + ", ".join(f"{a}:{act}" for a, act in sorted(action_dict.items())) + "}"

            # Build do(action) & [action]φ
            do_expr = f"do({action_str})"
            pdl_expr = f"[{action_str}]{formula}"
            tree = self.parser.parse(pdl_expr)
            pdl_name = self.transform(tree)

            # Add axiom: (do(action) & [action]φ) => xstit_I_φ
            conjunction = f"({do_expr} & {pdl_name})"
            self.axioms.add(f"{conjunction} => {name}")

        return name

    def ness(self, items):
        """ness(a_I, φ)  →  Multiple axioms (one per minimal sufficient set)

        Strategy: Generate one axiom per minimal sufficient set.

        Instead of:
            (conjunct1) v (conjunct2) v ... => ness_a_φ

        Generate:
            conjunct1 => ness_a_φ
            conjunct2 => ness_a_φ
            ...

        Returns:
            ness_a_φ (name)
        """
        action, formula = items
        name = self._name_for(f"ness({action}, {formula})")

        if self.model is None:
            raise ValueError("Model required for ness operator")

        h1 = self.model.named_histories.get("h1")
        if h1 is None:
            raise ValueError("History 'h1' not found in model")

        # Parse action string to get {agent: action_type} mapping
        parsed_actions = self._parse_action_str(action)
        h1_actions = set(h1.actions.items())
        target_actions = set(parsed_actions.items())

        # Generate powerset of h1 actions, filter to subsets containing ALL target actions
        from itertools import chain, combinations

        def powerset(iterable):
            s = list(iterable)
            return chain.from_iterable(combinations(s, r) for r in range(len(s)+1))

        relevant_subsets = [
            list(subset) for subset in powerset(h1_actions)
            if target_actions.issubset(set(subset))
        ]

        # Generate one axiom per relevant subset
        for J in relevant_subsets:
            # Build do(a_I)
            do_expr = f"do({action})"

            # Build [J]φ
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

                # Transform positive form, then build named negation
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

            # Add ONE axiom for this subset
            parts = [do_expr, sufficient_name] + minimality_parts
            conjunction = " & ".join(parts)
            self.axioms.add(f"({conjunction}) => {name}")

        return name

    # ========== Responsibility Operators ==========
    # Override to ensure ALL subformulas are recursively expanded

    def pres(self, items):
        """[I pres]φ  →  do(α_I) & expected_result & not_settled & next_φ

        Recursively expands ALL subformulas to avoid inline complex expressions.
        """
        agent, formula = items
        name = self._name_for(f"[{agent} pres]{formula}")

        if self.model is None:
            raise ValueError("Model required for pres operator")

        h1 = self.model.named_histories.get("h1")
        if h1 is None:
            raise ValueError("History 'h1' not found in model")

        actual_action = self._get_actual_action_str(agent, h1)

        # Recursively expand: do(actual_action) [+]-> φ
        expected_expr = f"do({actual_action}) [+]-> {formula}"
        tree = self.parser.parse(expected_expr)
        expected_name = self.transform(tree)

        # Recursively expand: ~[]Xφ (not settled)
        not_settled_expr = f"~[]X{formula}"
        tree = self.parser.parse(not_settled_expr)
        not_settled_name = self.transform(tree)

        # Recursively expand: Xφ
        next_expr = f"X{formula}"
        tree = self.parser.parse(next_expr)
        next_name = self.transform(tree)

        # Build pres expansion using ALL named subformulas
        expansion = f"(do({actual_action}) & {expected_name} & {not_settled_name} & {next_name})"
        self.axioms.add(f"{expansion} => {name}")
        return name

    def sres(self, items):
        """[I sres]φ  →  do(α_I) & expected_result & but_for

        Recursively expands ALL subformulas.
        """
        agent, formula = items
        name = self._name_for(f"[{agent} sres]{formula}")

        if self.model is None:
            raise ValueError("Model required for sres operator")

        h1 = self.model.named_histories.get("h1")
        if h1 is None:
            raise ValueError("History 'h1' not found in model")

        actual_action = self._get_actual_action_str(agent, h1)

        # Recursively expand: do(actual_action) [+]-> φ
        expected_expr = f"do({actual_action}) [+]-> {formula}"
        tree = self.parser.parse(expected_expr)
        expected_name = self.transform(tree)

        # Recursively expand: but(actual_action, φ)
        but_expr = f"but({actual_action}, {formula})"
        tree = self.parser.parse(but_expr)
        but_name = self.transform(tree)

        # Build sres expansion
        expansion = f"(do({actual_action}) & {expected_name} & {but_name})"
        self.axioms.add(f"{expansion} => {name}")
        return name

    def res(self, items):
        """[I res]φ  →  do(α_I) & expected_result & ness

        Recursively expands ALL subformulas.
        """
        agent, formula = items
        name = self._name_for(f"[{agent} res]{formula}")

        if self.model is None:
            raise ValueError("Model required for res operator")

        h1 = self.model.named_histories.get("h1")
        if h1 is None:
            raise ValueError("History 'h1' not found in model")

        actual_action = self._get_actual_action_str(agent, h1)

        # Recursively expand: do(actual_action) [+]-> φ
        expected_expr = f"do({actual_action}) [+]-> {formula}"
        tree = self.parser.parse(expected_expr)
        expected_name = self.transform(tree)

        # Recursively expand: ness(actual_action, φ)
        ness_expr = f"ness({actual_action}, {formula})"
        tree = self.parser.parse(ness_expr)
        ness_name = self.transform(tree)

        # Build res expansion
        expansion = f"(do({actual_action}) & {expected_name} & {ness_name})"
        self.axioms.add(f"{expansion} => {name}")
        return name

    # ========== Basic Modal Operators (Override to Create Axioms) ==========
    # These operators are inherited from AlonTransformer which just returns strings.
    # We need to override them to create expansion axioms for pyDatalog compatibility.

    def box(self, items):
        """[]φ  →  Named expansion axiom

        Instead of returning string "[]φ", create an axiom and return name.
        This ensures complex expressions like ~[]Xq get properly expanded.
        """
        # Recursively transform inner formula
        inner_formula = items[0]

        # Create expansion
        expansion = f"[]{inner_formula}"
        name = self._name_for(expansion)
        self.axioms.add(f"{expansion} => {name}")
        return name

    def negation(self, items):
        """~φ  →  Named expansion axiom

        Instead of returning string "~φ", create an axiom and return name.
        This ensures complex negations get properly expanded.
        """
        # Recursively transform inner formula
        inner_formula = items[0]

        # Create expansion
        expansion = f"~{inner_formula}"
        name = self._name_for(expansion)
        self.axioms.add(f"{expansion} => {name}")
        return name

    def next(self, items):
        """Xφ  →  Named expansion axiom

        Instead of returning string "Xφ", create an axiom and return name.
        This ensures complex next expressions get properly expanded.
        """
        # items[0] is X_OP token, items[1] is the formula
        inner_formula = items[1]

        # Create expansion
        expansion = f"X{inner_formula}"
        name = self._name_for(expansion)
        self.axioms.add(f"{expansion} => {name}")
        return name
