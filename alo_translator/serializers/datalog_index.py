"""
Datalog Index serializer using pyDatalog.

Serializes ALOn models to pyDatalog syntax for pure-Python reasoning.
"""

from typing import Dict, List, Set, Tuple, Optional
from ..model.core import ALOModel, GroupAction, Result, Query
from ..model.formula import (
    FormulaNode, Prop, DoAction, FreeDoAction, NamedFormula,
    Next, Box, Diamond, Conjunction, Disjunction, Negation, Implication
)
from .base import Serializer


class DatalogFormulaVisitor:
    """
    Translates FormulaNode AST to pyDatalog rule bodies.

    Key differences from OWL visitor:
    - Produces Datalog predicate calls instead of XML
    - Uses variable bindings (uppercase: I, J, K, ...)
    - Translates quantification to explicit variables
    """

    def __init__(self, model: ALOModel, registry=None):
        self.model = model
        self.registry = registry
        self.var_counter = 0

    def translate(self, formula: FormulaNode, index_var: str = "I") -> str:
        """
        Translate formula to Datalog rule body.

        Args:
            formula: The formula to translate
            index_var: Variable name for current index (default: "I")

        Returns:
            Datalog expression string
        """
        self.var_counter = 0  # Reset for each formula
        return self.visit(formula, index_var)

    def visit(self, node: FormulaNode, index_var: str) -> str:
        """Dispatch to appropriate visitor method."""
        if isinstance(node, NamedFormula):
            # Reference to registered predicate
            predicate_name = self._owl_name_to_predicate(node.formula_key)
            return f"{predicate_name}({index_var})"

        elif isinstance(node, Prop):
            return f"prop({index_var}, '{node.symbol}')"

        elif isinstance(node, DoAction):
            action_name = str(node.action)
            return f"action({index_var}, '{action_name}')"

        elif isinstance(node, FreeDoAction):
            action_name = str(node.action)
            # free_do(a) = action(I, a) & ~opposing_a(I)
            opp_pred = f"opposing_{action_name}"
            return f"(action({index_var}, '{action_name}') & ~{opp_pred}({index_var}))"

        elif isinstance(node, Next):
            # Xφ: exists successor J where φ(J)
            succ_var = self._fresh_var()
            inner = self.visit(node.formula, succ_var)
            return f"(succ({index_var}, {succ_var}) & {inner})"

        elif isinstance(node, Box):
            # []φ: forall J at same moment, φ(J)
            # In Datalog: ~(exists J: same_moment(I,J) & ~φ(J))
            alt_var = self._fresh_var()
            inner = self.visit(node.formula, alt_var)
            return f"~(same_moment({index_var}, {alt_var}) & ~({inner}))"

        elif isinstance(node, Diamond):
            # <>φ: exists J at same moment where φ(J)
            alt_var = self._fresh_var()
            inner = self.visit(node.formula, alt_var)
            return f"(same_moment({index_var}, {alt_var}) & {inner})"

        elif isinstance(node, Negation):
            inner = self.visit(node.formula, index_var)
            return f"~({inner})"

        elif isinstance(node, Conjunction):
            left = self.visit(node.left, index_var)
            right = self.visit(node.right, index_var)
            return f"({left} & {right})"

        elif isinstance(node, Disjunction):
            left = self.visit(node.left, index_var)
            right = self.visit(node.right, index_var)
            return f"({left} | {right})"

        elif isinstance(node, Implication):
            # φ → ψ ≡ ~φ | ψ
            ante = self.visit(node.antecedent, index_var)
            cons = self.visit(node.consequent, index_var)
            return f"(~({ante}) | {cons})"

        else:
            raise NotImplementedError(
                f"Datalog visitor doesn't support {type(node).__name__}"
            )

    def _fresh_var(self) -> str:
        """Generate fresh variable name (J, K, L, ...)."""
        var_name = chr(ord('J') + self.var_counter)
        self.var_counter += 1
        return var_name

    def _owl_name_to_predicate(self, owl_name: str) -> str:
        """
        Convert OWL class name to valid Datalog predicate name.

        Rules:
        - Handle numeric prefix: "1_pres_q" -> "agent1_pres_q"
        - Lowercase first letter if uppercase
        - Replace invalid characters with underscores

        Examples:
            "Xq" -> "xq"
            "1_pres_q" -> "agent1_pres_q"
            "expected_sd1_q" -> "expected_sd1_q"
        """
        # Handle numeric prefix
        if owl_name and owl_name[0].isdigit():
            predicate = f"agent{owl_name}"
        else:
            predicate = owl_name

        # Lowercase first char
        if predicate:
            predicate = predicate[0].lower() + predicate[1:]

        # Replace invalid chars
        predicate = predicate.replace('-', '_').replace(' ', '_')

        return predicate


class DatalogSerializer(Serializer):
    """
    Serializes ALOn models to pyDatalog syntax.

    Translation approach:
    - Facts: Ground assertions for indices, actions, propositions, structural relations
    - Rules: Datalog rules for query definitions using registry-based predicates
    - Same-moment: Explicit base facts + transitive closure rule
    """

    def __init__(self, model: ALOModel,
                 evaluation_history: str = "h1",
                 enable_evaluation: bool = False):
        """
        Initialize the serializer.

        Args:
            model: The ALOn model to serialize
            evaluation_history: Root history for query evaluation (default: h1)
            enable_evaluation: If True, include evaluation queries in output
        """
        super().__init__(model)
        self.evaluation_history = evaluation_history
        self.enable_evaluation = enable_evaluation
        self.cga_to_history: Dict[tuple, str] = {}
        self.history_to_cga: Dict[str, GroupAction] = {}
        self._term_names: Set[str] = set()

    def serialize(self) -> str:
        """
        Serialize to pyDatalog string.

        Returns:
            Complete pyDatalog program with facts and rules
        """
        # Build CGA mappings
        self._build_cga_mappings()

        # Collect all term names
        self._collect_terms()

        sections = []
        sections.append("# PyDatalog program generated from ALOn model")
        sections.append("# Import pyDatalog")
        sections.append("from pyDatalog import pyDatalog")
        sections.append("")

        # Term declarations
        sections.append(self._generate_term_declarations())
        sections.append("")

        # Structural facts
        sections.append(self._generate_structural_facts())
        sections.append("")

        # Action facts
        sections.append(self._generate_action_facts())
        sections.append("")

        # Proposition facts
        sections.append(self._generate_proposition_facts())
        sections.append("")

        # Opposing rules
        sections.append(self._generate_opposing_rules())
        sections.append("")

        # Query rules
        sections.append(self._generate_query_rules())

        # Evaluation queries (if enabled)
        if self.enable_evaluation:
            sections.append("")
            sections.append(self._generate_evaluation_queries())

        return "\n".join(sections)

    def _build_cga_mappings(self):
        """Build mappings between CGAs and history names (same as OWL)."""
        complete_gas = self.model.generate_complete_group_actions()
        history_counter = 1

        for cga in complete_gas:
            cga_key = tuple(sorted(cga.actions.items()))

            # Check for named history
            hist_name = None
            for name, named_cga in self.model.named_histories.items():
                if named_cga.actions == cga.actions:
                    hist_name = name
                    break

            # Generate name if needed
            if hist_name is None:
                while f"h{history_counter}" in self.model.named_histories:
                    history_counter += 1
                hist_name = f"h{history_counter}"
                history_counter += 1

            self.cga_to_history[cga_key] = hist_name
            self.history_to_cga[hist_name] = cga

    def _get_all_indices(self) -> List[Tuple[str, str]]:
        """
        Get all (moment, history) index pairs.

        Returns list like: [('m', 'h1'), ('m', 'h2'), ('m1', 'h1'), ('m2', 'h2')]
        """
        if not self.history_to_cga:
            self._build_cga_mappings()

        indices = []
        history_names = list(self.history_to_cga.keys())

        # Root indices
        for history_name in history_names:
            indices.append(('m', history_name))

        # Successor indices - use result.moment_name!
        for history_name in history_names:
            result = self._find_result_for_history(history_name)
            if result and result.moment_name:
                successor_moment = result.moment_name
            else:
                # Fallback - shouldn't happen with fixed DBT parser
                successor_moment = f"m{len([idx for idx in indices if idx[0] != 'm']) + 1}"
            indices.append((successor_moment, history_name))

        return indices

    def _index_name(self, moment: str, history: str) -> str:
        """Generate index name: m_h1, m1_h1, etc."""
        return f"{moment}_{history}"

    def _find_result_for_history(self, history_name: str) -> Optional[Result]:
        """Find the Result for a given history name."""
        for result in self.model.results:
            if result.history_name == history_name:
                return result
        return None

    def _collect_terms(self):
        """
        Collect all term names that need to be declared.

        Terms include:
        - Variables: I, J, K, L, M, N (for quantification)
        - Predicates: succ, same_moment, same_moment_base, action, prop, opposing_X
        - Query predicates from registry
        """
        # Variables for rules
        self._term_names.update(['I', 'J', 'K', 'L', 'M', 'N'])

        # Base predicates
        self._term_names.update(['succ', 'same_moment', 'same_moment_base', 'action', 'prop'])

        # Opposing predicates for each action
        for action in self.model.get_all_actions():
            action_str = str(action)
            self._term_names.add(f"opposing_{action_str}")

        # Query predicates from registry (if available)
        if hasattr(self.model, 'formula_registry') and self.model.formula_registry:
            visitor = DatalogFormulaVisitor(self.model)
            for owl_name in self.model.formula_registry.formulas.keys():
                predicate_name = visitor._owl_name_to_predicate(owl_name)
                self._term_names.add(predicate_name)

    def _generate_term_declarations(self) -> str:
        """Generate pyDatalog.create_terms() call."""
        term_list = ', '.join(sorted(self._term_names))
        return f"pyDatalog.create_terms('{term_list}')"

    def _generate_structural_facts(self) -> str:
        """
        Generate succ and same_moment facts.

        Strategy for same_moment:
        1. Generate base facts (same_moment_base) for reflexive + symmetric pairs at each moment
        2. Add transitive closure rule: same_moment(I,K) <= same_moment_base(I,K)
        3. Add transitivity: same_moment(I,K) <= same_moment(I,J) & same_moment(J,K)
        """
        facts = []
        facts.append("# Structural facts: succession and same-moment equivalence")
        facts.append("")

        all_indices = self._get_all_indices()

        # Succ facts
        facts.append("# Succession relation")
        for history_name in self.history_to_cga.keys():
            root_index = self._index_name('m', history_name)
            result = self._find_result_for_history(history_name)
            successor_moment = result.moment_name if result and result.moment_name else "m1"
            succ_index = self._index_name(successor_moment, history_name)

            facts.append(f"+ succ('{root_index}', '{succ_index}')")
        facts.append("")

        # Same-moment base facts (reflexive + symmetric at each moment)
        facts.append("# Same-moment base relation (reflexive + symmetric)")
        moment_groups: Dict[str, List[str]] = {}
        for moment, history in all_indices:
            if moment not in moment_groups:
                moment_groups[moment] = []
            moment_groups[moment].append(self._index_name(moment, history))

        for moment, indices in sorted(moment_groups.items()):
            facts.append(f"# Moment: {moment}")
            for i, idx1 in enumerate(indices):
                # Reflexive
                facts.append(f"+ same_moment_base('{idx1}', '{idx1}')")
                # Symmetric pairs (only one direction needed for base)
                for idx2 in indices[i+1:]:
                    facts.append(f"+ same_moment_base('{idx1}', '{idx2}')")
                    facts.append(f"+ same_moment_base('{idx2}', '{idx1}')")
        facts.append("")

        # Transitive closure rules
        facts.append("# Same-moment transitive closure")
        facts.append("same_moment(I, J) <= same_moment_base(I, J)")
        facts.append("same_moment(I, K) <= same_moment(I, J) & same_moment(J, K)")

        return "\n".join(facts)

    def _generate_action_facts(self) -> str:
        """Generate action membership facts."""
        facts = []
        facts.append("# Action facts")
        facts.append("")

        for history_name, group_action in self.history_to_cga.items():
            root_index = self._index_name('m', history_name)

            # Comment with human-readable CGA
            action_desc = ', '.join(
                f"{a}={t}" for a, t in sorted(group_action.actions.items())
            )
            facts.append(f"# History {history_name}: {{{action_desc}}}")

            # Facts for each action
            for action in group_action.to_action_list():
                action_str = str(action)
                facts.append(f"+ action('{root_index}', '{action_str}')")
            facts.append("")

        return "\n".join(facts)

    def _generate_proposition_facts(self) -> str:
        """Generate proposition truth facts (closed-world assumption)."""
        facts = []
        facts.append("# Proposition facts (closed-world: unlisted = false)")
        facts.append("")

        all_props = set(self.model.get_all_propositions())

        for history_name in self.history_to_cga.keys():
            result = self._find_result_for_history(history_name)
            if not result:
                continue

            successor_moment = result.moment_name if result.moment_name else "m1"
            succ_index = self._index_name(successor_moment, history_name)

            facts.append(f"# Propositions at {succ_index}")

            # Add facts for true propositions
            for prop in sorted(result.true_propositions):
                facts.append(f"+ prop('{succ_index}', '{prop}')")

            # Note false propositions (implicit, for documentation)
            false_props = all_props - set(result.true_propositions)
            if false_props:
                facts.append(f"# False (implicit): {', '.join(sorted(false_props))}")
            facts.append("")

        return "\n".join(facts)

    def _generate_opposing_rules(self) -> str:
        """
        Generate opposing relation predicates for FreeDoAction support.

        For each action X with opposings, creates:
            opposing_X(I) <= action(I, Y) for each Y that opposes X

        For actions with no opposings, no rule needed (closed-world = always false).
        """
        rules = []
        rules.append("# Opposing relations for FreeDoAction")
        rules.append("")

        # Group opposings by opposed action
        opposing_map: Dict[str, List[str]] = {}
        for opp in self.model.opposings:
            opposed_str = str(opp.opposed_action)
            if opposed_str not in opposing_map:
                opposing_map[opposed_str] = []
            opposing_map[opposed_str].append(str(opp.opposing_action))

        # Generate predicate for each opposed action
        for opposed_str, opposing_actions in sorted(opposing_map.items()):
            predicate_name = f"opposing_{opposed_str}"

            rules.append(f"# {predicate_name}: actions opposing {opposed_str}")
            for opposing_str in opposing_actions:
                rules.append(f"{predicate_name}(I) <= action(I, '{opposing_str}')")
            rules.append("")

        # Note: actions with no opposings don't need rules (closed-world)
        # The visitor checks ~opposing_X(I) which is always true if no rule exists

        return "\n".join(rules)

    def _generate_query_rules(self) -> str:
        """
        Generate Datalog rules for all queries using registry.

        Returns:
            String with rule definitions
        """
        # Check if we have a formula registry
        if not (hasattr(self.model, 'formula_registry') and self.model.formula_registry):
            return "# No formula registry - queries not expanded"

        registry = self.model.formula_registry
        visitor = DatalogFormulaVisitor(self.model, registry)

        rules = []
        rules.append("# Query predicate definitions (registry-based)")
        rules.append("")

        # Generate rule for each registered formula
        for owl_name, expansion_tree in sorted(registry.formulas.items()):
            # Skip primitive atoms (they're just facts)
            if isinstance(expansion_tree, (Prop, DoAction)):
                continue

            # Generate predicate definition
            predicate_name = visitor._owl_name_to_predicate(owl_name)

            try:
                rule_body = visitor.translate(expansion_tree, "I")

                # Add rule: predicate(I) <= rule_body
                rules.append(f"# {owl_name}")
                label = registry.labels.get(owl_name)
                if label:
                    rules.append(f"# Label: {label}")
                rules.append(f"{predicate_name}(I) <= {rule_body}")
                rules.append("")

            except Exception as e:
                rules.append(f"# ERROR translating {owl_name}: {e}")
                rules.append("")

        return "\n".join(rules)

    def _generate_evaluation_queries(self) -> str:
        """
        Generate query evaluation code for debugging/testing.

        Returns:
            String with print statements for query results
        """
        queries = []
        queries.append("# Query evaluation at root index")
        queries.append("")

        root_index = self._index_name('m', self.evaluation_history)
        visitor = DatalogFormulaVisitor(self.model)

        for query in self.model.queries:
            query_id = query.query_id or "unnamed"

            # Get predicate name
            if hasattr(self.model, 'formula_registry') and self.model.formula_registry:
                owl_name = query.expanded_ast.to_owl_name() if query.expanded_ast else query.formula_string
                predicate_name = visitor._owl_name_to_predicate(owl_name)
            else:
                predicate_name = visitor._owl_name_to_predicate(query_id)

            queries.append(f"# Query {query_id}: {query.formula_string}")
            queries.append(f"print('{query_id} at {root_index}:', {predicate_name}('{root_index}'))")
            queries.append(f"print('  All witnesses:', {predicate_name}(I))")
            queries.append("")

        return "\n".join(queries)

    def evaluate(self) -> Dict[str, Dict]:
        """
        Execute pyDatalog program and return evaluation results.

        Returns:
            Dict mapping query_id to:
                - 'result': bool (True/False for root index)
                - 'witnesses': List[str] (all indices satisfying query)
        """
        try:
            # Import pyDatalog (lazy import for optional dependency)
            from pyDatalog import pyDatalog as pdl
        except ImportError:
            raise ImportError(
                "pyDatalog is required for evaluation. "
                "Install with: pip install pyDatalog"
            )

        # Clear previous state
        pdl.clear()

        # Generate program without evaluation queries
        old_eval = self.enable_evaluation
        self.enable_evaluation = False
        program = self.serialize()
        self.enable_evaluation = old_eval

        # Execute the program
        exec(program, globals())

        # Evaluate each query
        results = {}
        root_index = self._index_name('m', self.evaluation_history)
        visitor = DatalogFormulaVisitor(self.model)

        for query in self.model.queries:
            query_id = query.query_id or f"q{len(results)+1:02d}"

            # Get predicate name
            if hasattr(self.model, 'formula_registry') and self.model.formula_registry:
                owl_name = query.expanded_ast.to_owl_name() if query.expanded_ast else query.formula_string
                predicate_name = visitor._owl_name_to_predicate(owl_name)
            else:
                predicate_name = visitor._owl_name_to_predicate(query_id)

            # Check if root index satisfies query
            try:
                # Use pyDatalog's ask() to query
                root_result = pdl.ask(f"{predicate_name}('{root_index}')")

                # Get all witnesses
                all_witnesses = pdl.ask(f"{predicate_name}(I)")
                witness_list = [str(w[0]) for w in all_witnesses] if all_witnesses else []

                results[query_id] = {
                    'result': bool(root_result),
                    'witnesses': witness_list,
                    'formula': query.formula_string
                }
            except Exception as e:
                results[query_id] = {
                    'result': False,
                    'witnesses': [],
                    'formula': query.formula_string,
                    'error': str(e)
                }

        return results
