"""
Datalog serialization for ALOn models.

Two classes:

  FormulaToDatalog  — Lark Transformer that converts expanded ALOn formula axioms
                      (in `name => formula` syntax) into pyDatalog rule strings.
                      Used internally by DatalogIndexSerializer to build the TBox.

  DatalogIndexSerializer — Serializes an ALOModel to a complete pyDatalog program.
                      ABox: facts for indices, succ chains, same_moment, per-moment
                            actions, per-moment propositions, opposing rules.
                      TBox: responsibility query rules via PyDatalogExpanderTransformer
                            + FormulaToDatalog, with evaluation_moment context.
"""

import re
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path

from lark import Lark, Transformer

from ..model.core import ALOModel


# ---------------------------------------------------------------------------
# FormulaToDatalog — formula-level Lark transformer (TBox helper)
# ---------------------------------------------------------------------------

class FormulaToDatalog(Transformer):
    """Serializes expanded ALOn formulas to pyDatalog syntax.

    Input:  axioms in `formula => name` syntax produced by PyDatalogExpanderTransformer
    Output: pyDatalog rule strings accumulated in self.rules
    """

    def __init__(self, name_to_formula=None):
        self.predicates = set()
        self.rules = []
        self.name_to_formula = name_to_formula or {}
        self.var_counter = 0
        self.helper_counter = 0
        self._do_group_map: dict = {}
        self._free_do_group_map: dict = {}

    def _sanitize_predicate(self, name):
        name_str = str(name)
        if name_str and name_str[0].isdigit():
            name_str = f"agent{name_str}"
        for old, new in {'{': '_', '}': '_', ':': '_', ',': '_', ' ': '_',
                         '(': '_', ')': '_', '~': '_', '&': '_', 'v': '_',
                         '|': '_', '>': '_', '<': '_', '-': '_', '[': '_',
                         ']': '_'}.items():
            name_str = name_str.replace(old, new)
        if name_str:
            name_str = name_str[0].lower() + name_str[1:]
        return name_str

    def _fresh_var(self):
        if self.var_counter < 17:
            var_name = chr(ord('J') + self.var_counter)
        else:
            base_letter = chr(ord('J') + ((self.var_counter - 17) % 17))
            number = ((self.var_counter - 17) // 17) + 1
            var_name = f"{base_letter}{number}"
        self.var_counter += 1
        return var_name

    # ---- top-level axiom ----

    def expansion_axiom(self, items):
        formula_datalog, name = items
        name_str = str(name)
        predicate = self._sanitize_predicate(name_str)
        self.predicates.add(predicate)
        comment = ""
        if name_str in self.name_to_formula:
            comment = f"# {self.name_to_formula[name_str]}\n"
        rule = f"{comment}{predicate}(I) <= {formula_datalog}"
        self.rules.append(rule)
        return rule

    # ---- propositional ----

    def biconditional(self, items):
        if len(items) == 1:
            return items[0]
        result = items[-1]
        for item in reversed(items[:-1]):
            result = f"(({item} | {result}) & ({result} | {item}))"  # unused but kept
        return result

    def implication(self, items):
        if len(items) == 1:
            return items[0]
        raise ValueError(
            "Implication (->) should not appear in pyDatalog axioms. "
            "Use PyDatalogExpanderTransformer which eliminates implications."
        )

    def disjunction(self, items):
        if len(items) == 1:
            return items[0]
        raise ValueError(
            "Disjunction (v) should not appear in pyDatalog axioms. "
            "Use PyDatalogExpanderTransformer which splits disjunctions."
        )

    def conjunction(self, items):
        if len(items) == 1:
            return items[0]
        result = items[0]
        for item in items[1:]:
            result = f"({result} & {item})"
        return result

    def negation(self, items):
        return f"~({items[0]})"

    # ---- modal ----

    def box(self, items):
        j_var = self._fresh_var()
        formula_with_j = self._substitute_var(items[0], 'I', j_var)
        self.helper_counter += 1
        helper_name = f"box_violation_{self.helper_counter}"
        self.predicates.add(helper_name)
        self.rules.append(
            f"{helper_name}(I) <= (same_moment(I, {j_var}) & ~({formula_with_j}))"
        )
        return f"~{helper_name}(I)"

    def diamond(self, items):
        j_var = self._fresh_var()
        formula_with_j = self._substitute_var(items[0], 'I', j_var)
        return f"(same_moment(I, {j_var}) & {formula_with_j})"

    def next(self, items):
        j_var = self._fresh_var()
        formula_with_j = self._substitute_var(items[1], 'I', j_var)
        return f"(succ(I, {j_var}) & {formula_with_j})"

    def _substitute_var(self, formula_str, old_var, new_var):
        result = formula_str
        for pattern, repl in [
            (f'({old_var},', f'({new_var},'),
            (f'({old_var})', f'({new_var})'),
            (f' {old_var},', f' {new_var},'),
            (f' {old_var})', f' {new_var})'),
            (f'({old_var} ', f'({new_var} '),
        ]:
            result = result.replace(pattern, repl)
        return result

    # ---- action predicates ----

    def do_action(self, items):
        action = items[0]
        if isinstance(action, str) and action.startswith("action(I,"):
            return action
        if not (isinstance(action, str) and ('&' in action or '|' in action)):
            return f"action(I, '{action}')"
        if action not in self._do_group_map:
            self.helper_counter += 1
            helper_name = f"do_group_{self.helper_counter}"
            self._do_group_map[action] = helper_name
            self.predicates.add(helper_name)
            self.rules.append(f"{helper_name}(I) <= {action}")
        return f"{self._do_group_map[action]}(I)"

    def free_do_action(self, items):
        action = items[0]
        if isinstance(action, str) and action.startswith("action(I,") and '&' not in action:
            match = re.search(r"action\(I, '(\w+)'\)", action)
            if match:
                action = match.group(1)
        if not (isinstance(action, str) and ('&' in action or '|' in action)):
            helper_name = f"free_do_{action}"
            if helper_name not in self.predicates:
                opp_pred = f"opposing_{action}"
                self.predicates.add(helper_name)
                self.predicates.add(opp_pred)
                self.rules.append(
                    f"{helper_name}(I) <= (action(I, '{action}') & ~{opp_pred}(I))"
                )
            return f"{helper_name}(I)"
        action_names = re.findall(r"action\(I, '(\w+)'\)", action)
        if action not in self._free_do_group_map:
            self.helper_counter += 1
            helper_name = f"free_do_group_{self.helper_counter}"
            self._free_do_group_map[action] = helper_name
            self.predicates.add(helper_name)
            parts = [f"action(I, '{a}')" for a in action_names]
            for a in action_names:
                ind_opp_pred = f"opposing_{a}"
                self.predicates.add(ind_opp_pred)
                parts.append(f"~{ind_opp_pred}(I)")
            group_opp_pred = 'opposing_' + '_'.join(sorted(action_names))
            self.predicates.add(group_opp_pred)
            self.rules.append(f"+ {group_opp_pred}('__never__')")
            self.rules.append(f"{helper_name}(I) <= ({' & '.join(parts)})")
        return f"{self._free_do_group_map[action]}(I)"

    # ---- atoms ----

    def prop(self, items):
        prop_name = str(items[0])
        if re.match(r'^f\d+$', prop_name):
            predicate = self._sanitize_predicate(prop_name)
            self.predicates.add(predicate)
            return f"{predicate}(I)"
        return f"prop(I, '{prop_name}')"

    def top(self, items):
        return "top(I)"

    def bottom(self, items):
        return "bottom(I)"

    def parens(self, items):
        return items[0]

    # ---- action/agent expressions ----

    def individual_action(self, items):
        return str(items[0])

    def group_action(self, items):
        action_predicates = []
        for mapping in items:
            if ':' in mapping:
                agent, action = mapping.split(':', 1)
                action_predicates.append(f"action(I, '{action}{agent}')")
            else:
                action_predicates.append(f"action(I, '{mapping}')")
        if len(action_predicates) == 1:
            return action_predicates[0]
        result = action_predicates[0]
        for pred in action_predicates[1:]:
            result = f"({result} & {pred})"
        return result

    def action_mapping(self, items):
        return f"{items[0]}:{items[1]}" if len(items) == 2 else str(items[0])

    def action_id(self, items):
        return str(items[0])

    def individual_agent(self, items):
        return str(items[0])

    def agent_group(self, items):
        return '{' + ', '.join(str(n) for n in items) + '}'

    def named_agent_group(self, items):
        return str(items[0])

    # ---- operators that must not appear after expansion ----

    def _must_not_appear(self, name, items):
        raise ValueError(f"{name} should not appear in expanded formulas: {items}")

    def pdl_box(self, items):       self._must_not_appear("pdl_box", items)
    def pdl_diamond(self, items):   self._must_not_appear("pdl_diamond", items)
    def expected_result(self, items): self._must_not_appear("expected_result", items)
    def but_for(self, items):       self._must_not_appear("but_for", items)
    def ness(self, items):          self._must_not_appear("ness", items)
    def xstit(self, items):         self._must_not_appear("xstit", items)
    def dxstit(self, items):        self._must_not_appear("dxstit", items)
    def pres(self, items):          self._must_not_appear("pres", items)
    def sres(self, items):          self._must_not_appear("sres", items)
    def res(self, items):           self._must_not_appear("res", items)
    def opposing(self, items):      self._must_not_appear("opposing", items)

    def generate_rules(self):
        return '\n\n'.join(self.rules)


# ---------------------------------------------------------------------------
# DatalogIndexSerializer — complete pyDatalog program generator
# ---------------------------------------------------------------------------

class DatalogIndexSerializer:
    """Serializes an ALOModel to a complete pyDatalog program.

    ABox: facts for indices, succ chains, same_moment, per-moment actions,
          per-moment propositions, opposing rules.
    TBox: responsibility query rules via PyDatalogExpanderTransformer +
          FormulaToDatalog, with evaluation_moment context.
    """

    def __init__(self, model: ALOModel, evaluation_history: Optional[str] = None,
                 evaluation_moment: Optional[str] = None, ness_empty_sufficient: bool = True):
        self.model = model
        self.evaluation_history = evaluation_history or model.evaluation_history
        self.evaluation_moment = evaluation_moment or model.evaluation_moment
        self.ness_empty_sufficient = ness_empty_sufficient

        grammar_path = Path(__file__).parent.parent / "parsers" / "alon_grammar_clean.lark"
        with open(grammar_path) as f:
            grammar = f.read()
        self.parser = Lark(grammar, start='start', parser='lalr')

        self.expander = None
        self.formula_serializer: Optional[FormulaToDatalog] = None
        self._query_predicate_map: Dict[str, str] = {}

    # ---- index helpers ----

    def _idx(self, moment: str, history: str) -> str:
        return f"{moment}_{history}"

    def _all_indices(self) -> List[Tuple[str, str]]:
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
        groups: Dict[str, List[str]] = {}
        for hp in self.model.histories.values():
            for moment in hp.path:
                groups.setdefault(moment, [])
                if hp.name not in groups[moment]:
                    groups[moment].append(hp.name)
        for v in groups.values():
            v.sort()
        return groups

    # ---- do(X) helper ----

    def _do_prop_action(self, prop: str) -> Optional[str]:
        m = re.match(r'^do\((.+)\)$', prop.strip())
        return m.group(1) if m else None

    # ---- fact generators ----

    def _generate_imports(self) -> str:
        return "from pyDatalog import pyDatalog"

    def _generate_structural_facts(self) -> str:
        lines = ["# Structural facts"]
        groups = self._group_by_moment()
        for hp in self.model.histories.values():
            for i in range(len(hp.path) - 1):
                from_idx = self._idx(hp.path[i], hp.name)
                to_idx   = self._idx(hp.path[i + 1], hp.name)
                lines.append(f"+ succ('{from_idx}', '{to_idx}')")
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
        lines = ["# Action facts (per-moment, per-history)"]
        for hp in self.model.histories.values():
            for moment_name, acts in hp.actions_at.items():
                idx = self._idx(moment_name, hp.name)
                for agent, action_type in sorted(acts.items()):
                    lines.append(f"+ action('{idx}', '{action_type}{agent}')")
        return '\n'.join(lines)

    def _generate_proposition_facts(self) -> str:
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
        names: Set[str] = set()
        for hp in self.model.histories.values():
            for acts in hp.actions_at.values():
                for agent, action_type in acts.items():
                    names.add(f"{action_type}{agent}")
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
            opposing_actions = [
                str(opp.opposing_action)
                for opp in self.model.opposings
                if str(opp.opposed_action) == action_name
            ]
            if opposing_actions:
                for opp in opposing_actions:
                    lines.append(f"opposing_{action_name}(I) <= action(I, '{opp}')")
            else:
                lines.append(f"+ opposing_{action_name}('__never__')")
        return '\n'.join(lines)

    def _generate_term_declarations(self) -> str:
        terms: Set[str] = set()
        terms.update(['I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R',
                      'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'])
        max_counter = self.formula_serializer.var_counter if self.formula_serializer else 0
        max_num = ((max_counter - 17) // 17) + 2 if max_counter >= 17 else 2
        for letter in ['J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R',
                       'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']:
            for num in range(1, max_num + 1):
                terms.add(f"{letter}{num}")
        terms.update(['succ', 'same_moment', 'same_moment_base',
                      'action', 'prop', 'top', 'bottom'])
        for action_name in self._collect_all_action_names():
            terms.add(f"opposing_{action_name}")
        if self.formula_serializer:
            terms.update(self.formula_serializer.predicates)
        return f"pyDatalog.create_terms('{', '.join(sorted(terms))}')"

    # ---- TBox (query rules) ----

    def _generate_query_rules(self) -> str:
        lines = ["# Query predicate definitions"]
        from ..parsers.pydatalog_expander_transformer import PyDatalogExpanderTransformer
        self.expander = PyDatalogExpanderTransformer(
            self.parser, self.model,
            evaluation_moment=self.evaluation_moment,
            ness_empty_sufficient=self.ness_empty_sufficient,
        )
        self._query_predicate_map = {}

        for query in self.model.queries:
            try:
                tree = self.parser.parse(query.formula_string)
                predicate_name = self.expander.transform(tree)
                if query.query_id and isinstance(predicate_name, str):
                    self._query_predicate_map[query.query_id] = predicate_name
            except Exception as e:
                lines.append(f"# ERROR expanding {query.query_id}: {str(e).replace(chr(10), ' | ')}")

        self.formula_serializer = FormulaToDatalog(
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
                self.formula_serializer.transform(self.parser.parse(axiom_str))
            except Exception as e:
                lines.append(f"# ERROR serializing axiom: {str(e).replace(chr(10), ' | ')}")

        for false_pred in sorted(self.expander.always_false_names):
            self.formula_serializer.predicates.add(false_pred)
            self.formula_serializer.rules.append(f"{false_pred}(I) <= bottom(I)")

        lines.append(self.formula_serializer.generate_rules())
        return '\n'.join(lines)

    # ---- serialize + evaluate ----

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
        preamble = program.split("# Query predicate definitions")[0]
        try:
            exec(preamble, globals())
        except Exception as e:
            lines = preamble.split("\n")
            m = re.search(r'line (\d+)', str(e))
            lineno = int(m.group(1)) if m else None
            offending = lines[lineno - 1] if lineno and lineno <= len(lines) else "(unknown)"
            raise RuntimeError(
                f"pyDatalog exec failed: {e}\n  -> line {lineno}: {offending}"
            ) from e
        try:
            exec(program.split("# Query predicate definitions")[1], globals())
        except Exception as e:
            raise RuntimeError(f"pyDatalog query rule exec failed: {e}") from e

        root_idx = self._idx(self.evaluation_moment, self.evaluation_history)
        results = {}
        for query in self.model.queries:
            query_id = query.query_id or f"q{len(results)}"
            if query_id in self._query_predicate_map:
                pred = self.formula_serializer._sanitize_predicate(
                    self._query_predicate_map[query_id]
                )
            elif self.expander and query.formula_string in self.expander.formula_to_name:
                pred = self.formula_serializer._sanitize_predicate(
                    self.expander.formula_to_name[query.formula_string]
                )
            else:
                pred = query_id
            try:
                root_result = pdl.ask(f"{pred}('{root_idx}')")
                results[query_id] = {'result': bool(root_result), 'witnesses': []}
            except Exception as e:
                results[query_id] = {'result': False, 'witnesses': [], 'error': str(e)}
        return results
