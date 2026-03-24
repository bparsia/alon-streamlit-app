"""
Datalog Index serializer - generates complete pyDatalog programs from ALOn models.

Uses the new transformer approach (ExpanderTransformer + DatalogSerializer) for TBox.
Generates ABox facts directly from the model.
"""

from typing import Dict, List, Set, Tuple, Optional
from pathlib import Path
from lark import Lark

from .base import Serializer
from ..model.core import ALOModel, GroupAction, Result
from .datalog_serializer import DatalogSerializer
from ..parsers.pydatalog_expander_transformer import PyDatalogExpanderTransformer


class DatalogIndexSerializer(Serializer):
    """
    Serializes ALOn models to complete pyDatalog programs.

    Architecture:
    - ABox: Generates facts for indices, actions, propositions, structural relations
    - TBox: Uses ExpanderTransformer + DatalogSerializer for query rules
    - Combines into executable pyDatalog program
    """

    def __init__(self, model: ALOModel, evaluation_history: str = "h1",
                 enable_evaluation: bool = True):
        """
        Initialize serializer.

        Args:
            model: The ALOn model to serialize
            evaluation_history: History to evaluate queries at (default: "h1")
            enable_evaluation: Whether to include evaluation code in output
        """
        super().__init__(model)
        self.evaluation_history = evaluation_history
        self.enable_evaluation = enable_evaluation

        # Build CGA mappings (history name -> GroupAction)
        self._build_cga_mappings()

        # Load grammar for expander (resolved relative to this file so it works
        # regardless of the working directory)
        grammar_path = Path(__file__).parent.parent / "parsers" / "alon_grammar_clean.lark"
        with open(grammar_path) as f:
            grammar = f.read()
        self.parser = Lark(grammar, start='start', parser='lalr')

        # Will be created during serialization
        self.expander = None
        self.datalog_serializer = None

        # Track all terms for create_terms()
        self._terms: Set[str] = set()

    def _build_cga_mappings(self):
        """Build mappings between CGAs and history names."""
        self.cga_to_history: Dict[tuple, str] = {}
        self.history_to_cga: Dict[str, GroupAction] = {}

        # Get all complete group actions
        complete_gas = self.model.generate_complete_group_actions()
        history_counter = 1

        for cga in complete_gas:
            # Create hashable key
            cga_key = tuple(sorted(cga.actions.items()))

            # Check if this CGA has a named history
            hist_name = None
            for name, named_cga in self.model.named_histories.items():
                if named_cga.actions == cga.actions:
                    hist_name = name
                    break

            # If no named history, generate h2, h3, etc.
            if hist_name is None:
                while f"h{history_counter}" in self.model.named_histories:
                    history_counter += 1
                hist_name = f"h{history_counter}"
                history_counter += 1

            self.cga_to_history[cga_key] = hist_name
            self.history_to_cga[hist_name] = cga

    def _index_name(self, moment: str, history: str) -> str:
        """Generate index name: m_h1, m1_h1, etc."""
        return f"{moment}_{history}"

    def _get_all_indices(self) -> List[Tuple[str, str]]:
        """
        Get all indices (moment, history) pairs.

        Returns list of (moment, history) tuples.
        Uses result.moment_name to get actual moment names (not enumeration).
        """
        indices = []
        history_names = sorted(self.history_to_cga.keys())

        # Root indices (one per history)
        for history_name in history_names:
            indices.append(('m', history_name))

        # Successor indices - one per history, always (even without an explicit Result)
        for history_name in history_names:
            successor_moment = self._get_successor_moment(history_name)
            indices.append((successor_moment, history_name))

        return indices

    def _find_result_for_history(self, history_name: str) -> Optional[Result]:
        """Find the Result associated with a history."""
        for result in self.model.results:
            if result.history_name == history_name:
                return result
        return None

    def _get_successor_moment(self, history_name: str) -> str:
        """
        Return the successor moment name for a history.

        Uses result.moment_name if present, otherwise falls back to a
        deterministic enumeration based on sorted history order.  This must
        agree with the logic in _get_all_indices() so that succ facts and
        same_moment groupings are consistent.
        """
        result = self._find_result_for_history(history_name)
        if result and result.moment_name:
            return result.moment_name
        history_names = sorted(self.history_to_cga.keys())
        rank = len([h for h in history_names if h <= history_name])
        return f"m{rank}"

    def _group_by_moment(self, indices: List[Tuple[str, str]]) -> Dict[str, List[str]]:
        """Group indices by moment, returning {moment: [histories]}."""
        moments: Dict[str, List[str]] = {}
        for moment, history in indices:
            if moment not in moments:
                moments[moment] = []
            moments[moment].append(history)
        return moments

    def serialize(self) -> str:
        """Generate complete pyDatalog program."""
        # Generate query rules first so we can collect all predicates
        query_rules = self._generate_query_rules()

        # Now generate term declarations with all tracked predicates
        sections = [
            self._generate_imports(),
            self._generate_term_declarations(),
            self._generate_structural_facts(),
            self._generate_structural_rules(),
            self._generate_action_facts(),
            self._generate_proposition_facts(),
            self._generate_opposing_rules(),
            query_rules,  # Use pre-generated query rules
        ]

        if self.enable_evaluation:
            sections.append(self._generate_evaluation_code())

        return "\n\n".join(sections)

    def _generate_imports(self) -> str:
        """Generate import statements."""
        return "from pyDatalog import pyDatalog"

    def _generate_term_declarations(self) -> str:
        """Generate pyDatalog.create_terms() call with all terms."""
        # Collect all terms
        terms = set()

        # Variables - declare exactly what _fresh_var() will generate
        terms.update(['I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'])
        # Generate all numbered variables up to the serializer's counter
        max_counter = self.datalog_serializer.var_counter if self.datalog_serializer else 0
        max_num = ((max_counter - 17) // 17) + 2 if max_counter >= 17 else 2
        for letter in ['J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']:
            for num in range(1, max_num + 1):
                terms.add(f"{letter}{num}")

        # Base predicates
        terms.update(['succ', 'same_moment', 'same_moment_base', 'action', 'prop', 'top', 'bottom'])

        # Action names (for opposing predicates)
        for cga in self.history_to_cga.values():
            for agent, action_type in cga.actions.items():
                action_name = f"{action_type}{agent}"
                terms.add(f"opposing_{action_name}")

        # Predicates from query rules (will be populated by DatalogSerializer)
        if self.datalog_serializer:
            terms.update(self.datalog_serializer.predicates)

        term_list = ', '.join(sorted(terms))
        return f"pyDatalog.create_terms('{term_list}')"

    def _generate_structural_facts(self) -> str:
        """Generate structural facts (succ, same_moment)."""
        facts = ["# Structural facts"]
        indices = self._get_all_indices()
        moments = self._group_by_moment(indices)

        # Successor facts: one succ edge per history (ALOnModel generates all
        # histories, so every root moment needs an explicit successor even when
        # no propositions are true there — this is required for correct NAF)
        for history_name in sorted(self.history_to_cga.keys()):
            root_idx = self._index_name('m', history_name)
            successor_moment = self._get_successor_moment(history_name)
            succ_idx = self._index_name(successor_moment, history_name)
            facts.append(f"+ succ('{root_idx}', '{succ_idx}')")

        # Same-moment base facts (before transitive closure)
        for moment, histories in moments.items():
            # Generate minimal same_moment_base facts
            for i, hist in enumerate(sorted(histories)):
                idx = self._index_name(moment, hist)
                # Reflexive
                facts.append(f"+ same_moment_base('{idx}', '{idx}')")
                # Chain to next (ensures transitivity will work)
                if i < len(histories) - 1:
                    next_hist = sorted(histories)[i + 1]
                    next_idx = self._index_name(moment, next_hist)
                    facts.append(f"+ same_moment_base('{idx}', '{next_idx}')")
                    facts.append(f"+ same_moment_base('{next_idx}', '{idx}')")

        return '\n'.join(facts)

    def _generate_structural_rules(self) -> str:
        """Generate structural rules (same_moment transitive closure)."""
        rules = ["# Structural rules - transitive closure for same_moment"]
        rules.append("same_moment(I, J) <= same_moment_base(I, J)")
        rules.append("same_moment(I, K) <= same_moment(I, J) & same_moment(J, K)")
        # Define top/bottom so NAF works if they appear in rule bodies
        rules.append("top(I) <= same_moment(I, I)")
        rules.append("+ bottom('__never__')")
        return '\n'.join(rules)

    def _generate_action_facts(self) -> str:
        """Generate action membership facts."""
        facts = ["# Action facts"]

        for history_name, cga in self.history_to_cga.items():
            root_idx = self._index_name('m', history_name)
            for agent, action_type in sorted(cga.actions.items()):
                action_name = f"{action_type}{agent}"
                facts.append(f"+ action('{root_idx}', '{action_name}')")

        return '\n'.join(facts)

    def _generate_proposition_facts(self) -> str:
        """Generate proposition truth facts (closed-world)."""
        facts = ["# Proposition facts (closed-world: unlisted props are false)"]

        for history_name in self.history_to_cga.keys():
            result = self._find_result_for_history(history_name)
            if result:
                successor_moment = self._get_successor_moment(history_name)
                successor_idx = self._index_name(successor_moment, history_name)
                for prop in result.true_propositions:
                    facts.append(f"+ prop('{successor_idx}', '{prop}')")

        return '\n'.join(facts)

    def _generate_opposing_rules(self) -> str:
        """Generate opposing predicates for FreeDoAction."""
        rules = ["# Opposing action rules"]

        # Collect all actions used in the model
        all_actions = set()
        for cga in self.history_to_cga.values():
            for agent, action_type in cga.actions.items():
                all_actions.add(f"{action_type}{agent}")

        # For each action, generate opposing rules
        for action_name in sorted(all_actions):
            # Find which actions oppose this one
            opposing_actions = []

            # Check model's opposing relations
            for opp_rel in self.model.opposings:
                # OpposingRelation: opposing_action opposes opposed_action
                # If action_name is the opposed_action, then opposing_action opposes it
                if str(opp_rel.opposed_action) == action_name:
                    opposing_actions.append(str(opp_rel.opposing_action))

            if opposing_actions:
                # Generate rule for each opposing action
                for opp_action_name in opposing_actions:
                    rules.append(f"opposing_{action_name}(I) <= action(I, '{opp_action_name}')")
            else:
                # No opposing actions - must still declare predicate so NAF works.
                # pyDatalog throws "Predicate without definition" if ~opposing_X(I)
                # is evaluated and opposing_X has never been asserted.
                # A dummy fact on a sentinel index defines the predicate as always-false
                # for real indices (closed-world assumption).
                rules.append(f"+ opposing_{action_name}('__never__')")

        return '\n'.join(rules)

    def _generate_query_rules(self) -> str:
        """Generate query rules using PyDatalogExpanderTransformer + DatalogSerializer."""
        rules = ["# Query predicate definitions"]

        # Create pyDatalog-compatible expander (shared across all queries)
        self.expander = PyDatalogExpanderTransformer(self.parser, self.model)

        # Expand all queries
        for query in self.model.queries:
            query_id = query.query_id or f"q{len(rules)}"
            formula_str = query.formula_string

            try:
                tree = self.parser.parse(formula_str)
                result_name = self.expander.transform(tree)
            except Exception as e:
                rules.append(f"# ERROR expanding {query_id}: {e}")

        # Create Datalog serializer with name_to_formula mapping
        self.datalog_serializer = DatalogSerializer(
            name_to_formula=self.expander.name_to_formula
        )

        # Serialize all expansion axioms
        for axiom_str in self.expander.axioms:
            try:
                # Skip trivial axioms
                if '=>' in axiom_str:
                    parts = axiom_str.split('=>')
                    if len(parts) == 2:
                        lhs = parts[0].strip()
                        rhs = parts[1].strip()
                        if not lhs or not rhs or lhs == rhs or lhs == '()':
                            continue

                axiom_tree = self.parser.parse(axiom_str)
                self.datalog_serializer.transform(axiom_tree)
            except Exception as e:
                rules.append(f"# ERROR serializing axiom: {e}")

        # Get generated rules
        rules.append(self.datalog_serializer.generate_rules())

        return '\n'.join(rules)

    def _generate_evaluation_code(self) -> str:
        """Generate code to evaluate queries at evaluation_history."""
        code = ["# Evaluation code"]
        code.append("if __name__ == '__main__':")
        code.append("    # Evaluate queries")

        root_idx = self._index_name('m', self.evaluation_history)

        for query in self.model.queries:
            query_id = query.query_id or "unknown"
            # Get the predicate name from the expander
            if self.expander and query.formula_string in self.expander.formula_to_name:
                predicate_name = self.expander.formula_to_name[query.formula_string]
                # Convert to Datalog predicate name
                predicate_name = self.datalog_serializer._sanitize_predicate(predicate_name)
            else:
                predicate_name = query_id

            code.append(f"    result = {predicate_name}('{root_idx}')")
            code.append(f"    print(f'{query_id}: {{bool(result)}}')")

        return '\n'.join(code)

    def evaluate(self) -> Dict[str, Dict]:
        """
        Execute pyDatalog program and return query results.

        Returns:
            Dict mapping query_id to {'result': bool, 'witnesses': List[str]}
        """
        # Generate program
        program = self.serialize()

        # Clear pyDatalog state
        from pyDatalog import pyDatalog as pdl
        pdl.clear()

        # Execute program (excluding evaluation code).
        # Must exec into globals() so pyDatalog Terms created by create_terms()
        # persist in the module-level namespace — without this they are
        # garbage-collected when the exec local scope is discarded and all
        # subsequent pdl.ask() calls return None.
        sections = program.split("# Evaluation code")[0]
        try:
            exec(sections, globals())
        except Exception as e:
            # Re-raise with the offending line so the caller can display it
            lines = sections.split("\n")
            import re as _re
            m = _re.search(r'line (\d+)', str(e))
            if m:
                lineno = int(m.group(1))
                offending = lines[lineno - 1] if lineno <= len(lines) else "(out of range)"
            else:
                offending = "(unknown)"
            raise type(e)(f"{e}\n  → line {m.group(1) if m else '?'}: {offending}") from None

        # Evaluate each query
        results = {}
        root_idx = self._index_name('m', self.evaluation_history)

        for query in self.model.queries:
            query_id = query.query_id or f"q{len(results)}"

            # Get predicate name
            if self.expander and query.formula_string in self.expander.formula_to_name:
                predicate_name = self.expander.formula_to_name[query.formula_string]
                predicate_name = self.datalog_serializer._sanitize_predicate(predicate_name)
            else:
                predicate_name = query_id

            try:
                root_result = pdl.ask(f"{predicate_name}('{root_idx}')")
                results[query_id] = {
                    'result': bool(root_result),
                    'witnesses': []
                }
            except Exception as e:
                results[query_id] = {
                    'result': False,
                    'witnesses': [],
                    'error': str(e)
                }

        return results
