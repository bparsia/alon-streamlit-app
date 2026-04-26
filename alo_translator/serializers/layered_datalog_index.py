"""
Datalog Index serializer for LayeredALOModel (TD>1).

Generates complete pyDatalog programs from multi-step ALOn models.
Architecture mirrors DatalogIndexSerializer but traverses a moment tree
rather than a flat root+leaves structure.
"""

import re
from typing import Dict, List, Set, Tuple, Optional
from pathlib import Path
from lark import Lark

from ..model.core import LayeredALOModel
from .datalog_serializer import DatalogSerializer
from ..parsers.pydatalog_expander_transformer import PyDatalogExpanderTransformer


class LayeredDatalogIndexSerializer:
    """
    Serializes a LayeredALOModel to a complete pyDatalog program.

    ABox: facts for indices, succ chains, same_moment, per-moment actions,
          per-moment propositions.
    TBox: responsibility query rules via PyDatalogExpanderTransformer +
          DatalogSerializer, with evaluation_moment context.
    """

    def __init__(self, model: LayeredALOModel, evaluation_history: Optional[str] = None,
                 evaluation_moment: Optional[str] = None):
        self.model = model
        self.evaluation_history = evaluation_history or model.evaluation_history
        self.evaluation_moment = evaluation_moment or model.evaluation_moment

        grammar_path = Path(__file__).parent.parent / "parsers" / "alon_grammar_clean.lark"
        with open(grammar_path) as f:
            grammar = f.read()
        self.parser = Lark(grammar, start='start', parser='lalr')

        self.expander: Optional[PyDatalogExpanderTransformer] = None
        self.datalog_serializer: Optional[DatalogSerializer] = None
        self._terms: Set[str] = set()

    # ------------------------------------------------------------------
    # Index helpers
    # ------------------------------------------------------------------

    def _idx(self, moment: str, history: str) -> str:
        return f"{moment}_{history}"

    def _all_indices(self) -> List[Tuple[str, str]]:
        """All (moment, history) pairs across every history's path."""
        seen = set()
        indices = []
        for hp in self.model.histories.values():
            for moment in hp.path:
                key = (moment, hp.name)
                if key not in seen:
                    seen.add(key)
                    indices.append(key)
        return indices

    def _group_by_moment(self) -> Dict[str, List[str]]:
        """moment_name -> sorted list of history names that pass through it."""
        groups: Dict[str, List[str]] = {}
        for hp in self.model.histories.values():
            for moment in hp.path:
                groups.setdefault(moment, [])
                if hp.name not in groups[moment]:
                    groups[moment].append(hp.name)
        for v in groups.values():
            v.sort()
        return groups

    # ------------------------------------------------------------------
    # do(X) helper
    # ------------------------------------------------------------------

    def _do_prop_action(self, prop: str) -> Optional[str]:
        """If prop is do(X), return X; else None."""
        m = re.match(r'^do\((.+)\)$', prop.strip())
        return m.group(1) if m else None

    # ------------------------------------------------------------------
    # Fact generators
    # ------------------------------------------------------------------

    def _generate_imports(self) -> str:
        return "from pyDatalog import pyDatalog"

    def _generate_structural_facts(self) -> str:
        lines = ["# Structural facts"]
        groups = self._group_by_moment()

        # succ: one edge per consecutive moment pair on each history's path
        for hp in self.model.histories.values():
            for i in range(len(hp.path) - 1):
                from_idx = self._idx(hp.path[i], hp.name)
                to_idx   = self._idx(hp.path[i + 1], hp.name)
                lines.append(f"+ succ('{from_idx}', '{to_idx}')")

        # same_moment_base: chain within each moment's history group
        for moment, histories in groups.items():
            for i, hist in enumerate(histories):
                idx = self._idx(moment, hist)
                lines.append(f"+ same_moment_base('{idx}', '{idx}')")
                if i < len(histories) - 1:
                    next_idx = self._idx(moment, histories[i + 1])
                    lines.append(f"+ same_moment_base('{idx}', '{next_idx}')")
                    lines.append(f"+ same_moment_base('{next_idx}', '{idx}')")

        return '\n'.join(lines)

    def _generate_structural_rules(self) -> str:
        lines = ["# Structural rules"]
        lines.append("same_moment(I, J) <= same_moment_base(I, J)")
        lines.append("same_moment(I, K) <= same_moment(I, J) & same_moment(J, K)")
        lines.append("top(I) <= same_moment(I, I)")
        lines.append("+ bottom('__never__')")
        return '\n'.join(lines)

    def _generate_action_facts(self) -> str:
        """Assert actions only at the moment where each agent chose."""
        lines = ["# Action facts (per-moment, per-history)"]
        for hp in self.model.histories.values():
            for moment_name, acts in hp.actions_at.items():
                idx = self._idx(moment_name, hp.name)
                for agent, action_type in sorted(acts.items()):
                    lines.append(f"+ action('{idx}', '{action_type}{agent}')")
        return '\n'.join(lines)

    def _generate_proposition_facts(self) -> str:
        """
        Assert proposition/action facts for non-default labels on every moment.

        Intermediate moment propositions are emitted at all indices for
        histories that pass through that moment.
        Leaf propositions are emitted only at the single history's index.
        """
        lines = ["# Proposition facts"]
        for moment_name, node in self.model.moments.items():
            for prop in sorted(node.propositions):
                action_name = self._do_prop_action(prop)
                for hist_name in self.model.histories_through(moment_name):
                    idx = self._idx(moment_name, hist_name)
                    if action_name:
                        lines.append(f"+ action('{idx}', '{action_name}')")
                    else:
                        lines.append(f"+ prop('{idx}', '{prop}')")
        return '\n'.join(lines)

    def _collect_all_action_names(self) -> Set[str]:
        """All concrete action names (typeN) in the model."""
        names: Set[str] = set()
        for hp in self.model.histories.values():
            for acts in hp.actions_at.values():
                for agent, action_type in acts.items():
                    names.add(f"{action_type}{agent}")
        # Also any do(X) proposition labels
        for node in self.model.moments.values():
            for prop in node.propositions:
                a = self._do_prop_action(prop)
                if a:
                    names.add(a)
        return names

    def _generate_opposing_rules(self) -> str:
        lines = ["# Opposing action rules"]
        all_actions = self._collect_all_action_names()

        for action_name in sorted(all_actions):
            opposing_actions = []
            for opp_rel in self.model.opposings:
                if str(opp_rel.opposed_action) == action_name:
                    opposing_actions.append(str(opp_rel.opposing_action))

            if opposing_actions:
                for opp in opposing_actions:
                    lines.append(f"opposing_{action_name}(I) <= action(I, '{opp}')")
            else:
                lines.append(f"+ opposing_{action_name}('__never__')")

        return '\n'.join(lines)

    def _generate_term_declarations(self) -> str:
        terms: Set[str] = set()

        # Variables
        terms.update(['I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R',
                      'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'])
        max_counter = self.datalog_serializer.var_counter if self.datalog_serializer else 0
        max_num = ((max_counter - 17) // 17) + 2 if max_counter >= 17 else 2
        for letter in ['J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R',
                       'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']:
            for num in range(1, max_num + 1):
                terms.add(f"{letter}{num}")

        # Base predicates
        terms.update(['succ', 'same_moment', 'same_moment_base',
                      'action', 'prop', 'top', 'bottom'])

        # opposing_ predicates for every action
        for action_name in self._collect_all_action_names():
            terms.add(f"opposing_{action_name}")

        # Predicates from query rules
        if self.datalog_serializer:
            terms.update(self.datalog_serializer.predicates)

        term_list = ', '.join(sorted(terms))
        return f"pyDatalog.create_terms('{term_list}')"

    # ------------------------------------------------------------------
    # TBox (query rules)
    # ------------------------------------------------------------------

    def _generate_query_rules(self) -> str:
        lines = ["# Query predicate definitions"]

        # Build expander with evaluation_moment context
        self.expander = PyDatalogExpanderTransformer(
            self.parser, self.model,
            evaluation_moment=self.evaluation_moment,
        )
        self._query_predicate_map: Dict[str, str] = {}  # query_id -> predicate_name

        for query in self.model.queries:
            formula_str = query.formula_string
            try:
                tree = self.parser.parse(formula_str)
                predicate_name = self.expander.transform(tree)
                if query.query_id and isinstance(predicate_name, str):
                    self._query_predicate_map[query.query_id] = predicate_name
            except Exception as e:
                err_msg = str(e).replace('\n', ' | ')
                lines.append(f"# ERROR expanding {query.query_id}: {err_msg}")

        self.datalog_serializer = DatalogSerializer(
            name_to_formula=self.expander.name_to_formula
        )

        for axiom_str in self.expander.axioms:
            try:
                if '=>' in axiom_str:
                    parts = axiom_str.split('=>')
                    if len(parts) == 2:
                        lhs, rhs = parts[0].strip(), parts[1].strip()
                        if not lhs or not rhs or lhs == rhs or lhs == '()':
                            continue
                axiom_tree = self.parser.parse(axiom_str)
                self.datalog_serializer.transform(axiom_tree)
            except Exception as e:
                err_msg = str(e).replace('\n', ' | ')
                lines.append(f"# ERROR serializing axiom: {err_msg}")

        # Emit always-false predicates (agents not acting at eval moment)
        for false_pred in sorted(self.expander.always_false_names):
            self.datalog_serializer.predicates.add(false_pred)
            self.datalog_serializer.rules.append(f"{false_pred}(I) <= bottom(I)")

        lines.append(self.datalog_serializer.generate_rules())
        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Serialize + evaluate
    # ------------------------------------------------------------------

    def serialize(self) -> str:
        query_rules = self._generate_query_rules()

        sections = [
            self._generate_imports(),
            self._generate_term_declarations(),
            self._generate_structural_facts(),
            self._generate_structural_rules(),
            self._generate_action_facts(),
            self._generate_proposition_facts(),
            self._generate_opposing_rules(),
            query_rules,
        ]
        return "\n\n".join(sections)

    def evaluate(self) -> Dict[str, Dict]:
        """Execute pyDatalog program and return {query_id: {result, witnesses}}."""
        program = self.serialize()

        from pyDatalog import pyDatalog as pdl
        pdl.clear()

        sections = program.split("# Query predicate definitions")[0]
        self._last_sections = sections
        try:
            exec(sections, globals())
        except Exception as e:
            lines = sections.split("\n")
            m = re.search(r'line (\d+)', str(e))
            lineno = int(m.group(1)) if m else None
            offending = lines[lineno - 1] if lineno and lineno <= len(lines) else "(unknown)"
            raise RuntimeError(
                f"pyDatalog exec failed: {e}\n  → line {lineno}: {offending}"
            ) from e

        # Re-exec query rules (they were not included above)
        try:
            exec(program.split("# Query predicate definitions")[1], globals())
        except Exception as e:
            raise RuntimeError(f"pyDatalog query rule exec failed: {e}") from e

        root_idx = self._idx(self.evaluation_moment, self.evaluation_history)
        results = {}

        for query in self.model.queries:
            query_id = query.query_id or f"q{len(results)}"

            if query_id in self._query_predicate_map:
                predicate_name = self.datalog_serializer._sanitize_predicate(
                    self._query_predicate_map[query_id]
                )
            elif self.expander and query.formula_string in self.expander.formula_to_name:
                predicate_name = self.expander.formula_to_name[query.formula_string]
                predicate_name = self.datalog_serializer._sanitize_predicate(predicate_name)
            else:
                predicate_name = query_id

            try:
                root_result = pdl.ask(f"{predicate_name}('{root_idx}')")
                results[query_id] = {'result': bool(root_result), 'witnesses': []}
            except Exception as e:
                results[query_id] = {'result': False, 'witnesses': [], 'error': str(e)}

        return results
