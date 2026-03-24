"""Datalog Serializer - outputs expanded formulas as pyDatalog rules.

Handles only the "directly translated" constructs that remain after expansion.
Requires PyDatalogExpanderTransformer to eliminate implications and disjunctions.
"""

from lark import Transformer


class DatalogSerializer(Transformer):
    """Serializes expanded ALOn formulas to pyDatalog syntax.

    Converts `=>` expansion axioms to Datalog rules.
    Tracks predicates and terms for declaration generation.
    """

    def __init__(self, name_to_formula=None):
        """Initialize serializer.

        Args:
            name_to_formula: Optional dict mapping q-names to formula strings for comments
        """
        self.predicates = set()  # Track all predicate names
        self.rules = []  # Accumulate Datalog rules
        self.name_to_formula = name_to_formula or {}
        self.var_counter = 0  # For generating fresh variables
        self.helper_counter = 0  # For generating unique helper predicate names
        self._do_group_map: dict = {}  # conjunction string -> helper predicate name
        self._free_do_group_map: dict = {}  # conjunction string -> helper predicate name

    def _sanitize_predicate(self, name):
        """Sanitize name for Datalog by replacing special chars with underscores.

        Also handles numeric prefixes: "1_pres_q" -> "agent1_pres_q"
        """
        name_str = str(name)

        # Handle numeric prefix
        if name_str and name_str[0].isdigit():
            name_str = f"agent{name_str}"

        # Replace special characters
        replacements = {
            '{': '_', '}': '_', ':': '_', ',': '_', ' ': '_',
            '(': '_', ')': '_', '~': '_', '&': '_', 'v': '_',
            '|': '_', '>': '_', '<': '_', '-': '_', '[': '_',
            ']': '_',
        }
        result = name_str
        for old, new in replacements.items():
            result = result.replace(old, new)

        # Lowercase first letter if uppercase
        if result:
            result = result[0].lower() + result[1:]

        return result

    def _fresh_var(self):
        """Generate fresh variable name (J, K, L, ..., Z, J1, K1, ...)."""
        if self.var_counter < 17:  # J through Z (17 letters)
            var_name = chr(ord('J') + self.var_counter)
        else:
            # After Z, use J1, K1, L1, etc.
            base_letter = chr(ord('J') + ((self.var_counter - 17) % 17))
            number = ((self.var_counter - 17) // 17) + 1
            var_name = f"{base_letter}{number}"
        self.var_counter += 1
        return var_name

    # ========== Top-level expansion axiom ==========

    def expansion_axiom(self, items):
        """formula => name  →  name(I) <= formula_datalog

        Also adds comment with formula string if available.
        Expects PyDatalogExpanderTransformer to have eliminated all implications and disjunctions.
        """
        formula_datalog, name = items
        name_str = str(name)
        predicate = self._sanitize_predicate(name_str)
        self.predicates.add(predicate)

        # Generate comment
        comment = ""
        if name_str in self.name_to_formula:
            formula_string = self.name_to_formula[name_str]
            comment = f"# {formula_string}\n"

        # Generate single rule (no DNF conversion needed)
        rule = f"{comment}{predicate}(I) <= {formula_datalog}"
        self.rules.append(rule)
        return rule

    # ========== Propositional Logic ==========

    def biconditional(self, items):
        """φ <-> ψ  →  ((~φ | ψ) & (~ψ | φ))"""
        if len(items) == 1:
            return items[0]
        # Build right-associatively
        result = items[-1]
        for item in reversed(items[:-1]):
            left_implies_right = f"(~({item}) | {result})"
            right_implies_left = f"(~({result}) | {item})"
            result = f"({left_implies_right} & {right_implies_left})"
        return result

    def implication(self, items):
        """φ -> ψ  →  ERROR (should not appear in pyDatalog-compatible axioms)

        PyDatalog does NOT support the | operator, so implications cannot be
        converted to (~φ | ψ). Use PyDatalogExpanderTransformer instead, which
        names implications and generates multiple rules.
        """
        # Grammar always passes through this rule, even with no '->'
        if len(items) == 1:
            return items[0]

        # If we get here, there's an actual implication operator
        raise ValueError(
            "Implication operator (->) should not appear in pyDatalog axioms. "
            "PyDatalogExpanderTransformer eliminates implications by naming them "
            "and generating multiple rules. Use PyDatalogExpanderTransformer instead "
            "of ExpanderTransformer for pyDatalog serialization."
        )

    def disjunction(self, items):
        """φ v ψ  →  ERROR (should not appear in pyDatalog-compatible axioms)

        PyDatalog does NOT support the | operator. Use PyDatalogExpanderTransformer
        instead, which splits disjunctions into multiple axioms.
        """
        # Grammar always passes through this rule, even with no 'v'
        if len(items) == 1:
            return items[0]

        # If we get here, there's an actual disjunction operator
        raise ValueError(
            "Disjunction operator (v) should not appear in pyDatalog axioms. "
            "PyDatalogExpanderTransformer eliminates disjunctions by splitting them "
            "into multiple axioms. Use PyDatalogExpanderTransformer instead of "
            "ExpanderTransformer for pyDatalog serialization."
        )

    def conjunction(self, items):
        """φ & ψ  →  (φ & ψ)"""
        if len(items) == 1:
            return items[0]
        # Build left-associatively
        result = items[0]
        for item in items[1:]:
            result = f"({result} & {item})"
        return result

    def negation(self, items):
        """~φ  →  ~(φ)"""
        return f"~({items[0]})"

    # ========== Modal Operators ==========

    def box(self, items):
        """[]φ  →  ~box_violation_N(I)

        Universal quantification over same-moment alternatives.

        PyDatalog cannot handle nested negation with free variables like:
            ~(same_moment(I, J) & ~φ(J))

        Instead, we generate a helper predicate:
            box_violation_N(I) <= same_moment(I, J) & ~φ(J)

        And return:
            ~box_violation_N(I)
        """
        j_var = self._fresh_var()
        # Replace all occurrences of I with J in the formula
        try:
            formula_with_j = self._substitute_var(items[0], 'I', j_var)
        except Exception as e:
            # Debug: print what's causing the issue
            print(f"DEBUG: Error in _substitute_var with formula: {items[0][:100]}")
            raise

        # Generate unique helper predicate name
        self.helper_counter += 1
        helper_name = f"box_violation_{self.helper_counter}"
        self.predicates.add(helper_name)

        # Generate helper rule: box_violation_N(I) <= same_moment(I, J) & ~φ(J)
        helper_rule = f"{helper_name}(I) <= (same_moment(I, {j_var}) & ~({formula_with_j}))"
        self.rules.append(helper_rule)

        # Return negation of helper predicate
        return f"~{helper_name}(I)"

    def diamond(self, items):
        """<>φ  →  same_moment(I,J) & φ(J)

        Existential quantification over same-moment alternatives.
        """
        j_var = self._fresh_var()
        formula_with_j = self._substitute_var(items[0], 'I', j_var)
        return f"(same_moment(I, {j_var}) & {formula_with_j})"

    def next(self, items):
        """Xφ  →  succ(I,J) & φ(J)

        Existential quantification over successor indices.
        """
        # items[0] is X_OP token, items[1] is the formula
        j_var = self._fresh_var()
        formula_with_j = self._substitute_var(items[1], 'I', j_var)
        return f"(succ(I, {j_var}) & {formula_with_j})"

    def _substitute_var(self, formula_str, old_var, new_var):
        """Substitute variable in formula string.

        Replaces occurrences of old_var with new_var in predicates.
        For example: prop(I, 'q') → prop(J, 'q')

        We need to be careful to only replace standalone variable names,
        not ones that are part of other identifiers.
        """
        # Simple approach: replace patterns like "var," "var)" "var " etc.
        # This handles most cases in our Datalog syntax
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

    # ========== Action Predicates ==========

    def do_action(self, items):
        """do(a)  →  action(I, 'a') or do_group_N(I) for group actions

        For individual actions: do(sd1) → action(I, 'sd1')
        For group actions: creates a named helper to avoid nested negation.
            do_group_N(I) <= (action(I, 'sd1') & action(I, 'ha2'))
        Group actions must be wrapped in a helper so that ~do(group) becomes
        simple NAF (~do_group_N(I)) rather than ~(conjunction), which pyDatalog
        cannot handle correctly.

        For single-agent group actions like {1:ss}, group_action() returns
        "action(I, 'ss1')" directly (no '&'). We must detect and pass this
        through rather than re-wrapping it.
        """
        action = items[0]
        # Single-agent group action: group_action already returned "action(I, 'ss1')"
        if isinstance(action, str) and action.startswith("action(I,"):
            return action
        if not (isinstance(action, str) and ('&' in action or '|' in action)):
            return f"action(I, '{action}')"

        # Group action — create helper predicate once per unique conjunction
        if action not in self._do_group_map:
            self.helper_counter += 1
            helper_name = f"do_group_{self.helper_counter}"
            self._do_group_map[action] = helper_name
            self.predicates.add(helper_name)
            self.rules.append(f"{helper_name}(I) <= {action}")
        return f"{self._do_group_map[action]}(I)"

    def free_do_action(self, items):
        """free_do(a)  →  free_do_a(I)  (via helper predicate)

        Creates a named helper so that negating free_do remains simple NAF:
            free_do_a(I) <= action(I, 'a') & ~opposing_a(I)

        Without this, ~free_do(a) would produce ~(action(...) & ~opposing(...)),
        which is nested negation that pyDatalog cannot handle correctly.

        For group actions like free_do({2:ss,4:rb}), each agent's individual
        free_do helper is created, then combined:
            free_do_ss2(I) <= action(I, 'ss2') & ~opposing_ss2(I)
            free_do_rb4(I) <= action(I, 'rb4') & ~opposing_rb4(I)
            free_do_group_N(I) <= free_do_ss2(I) & free_do_rb4(I)
        """
        import re
        action = items[0]

        # Single-agent group action: group_action returned "action(I, 'ss1')" directly.
        # Extract the action name so we can use the individual-action path below.
        if isinstance(action, str) and action.startswith("action(I,") and '&' not in action:
            match = re.search(r"action\(I, '(\w+)'\)", action)
            if match:
                action = match.group(1)  # e.g., "ss1"

        # Individual action — generate helper predicate once
        if not (isinstance(action, str) and ('&' in action or '|' in action)):
            helper_name = f"free_do_{action}"
            if helper_name not in self.predicates:
                opp_pred = f"opposing_{action}"
                self.predicates.add(helper_name)
                self.predicates.add(opp_pred)
                helper_rule = f"{helper_name}(I) <= (action(I, '{action}') & ~{opp_pred}(I))"
                self.rules.append(helper_rule)
            return f"{helper_name}(I)"

        # Group action — extract individual action names and create combined helper
        # action is a conjunction like "(action(I, 'ss2') & action(I, 'rb4'))"
        action_names = re.findall(r"action\(I, '(\w+)'\)", action)

        # Ensure individual free_do helpers exist for each action in the group
        for action_name in action_names:
            ind_helper = f"free_do_{action_name}"
            if ind_helper not in self.predicates:
                opp_pred = f"opposing_{action_name}"
                self.predicates.add(ind_helper)
                self.predicates.add(opp_pred)
                self.rules.append(f"{ind_helper}(I) <= (action(I, '{action_name}') & ~{opp_pred}(I))")

        # Create combined group helper (deduped by conjunction string)
        if action not in self._free_do_group_map:
            self.helper_counter += 1
            helper_name = f"free_do_group_{self.helper_counter}"
            self._free_do_group_map[action] = helper_name
            self.predicates.add(helper_name)
            combined = ' & '.join(f"free_do_{a}(I)" for a in action_names)
            self.rules.append(f"{helper_name}(I) <= ({combined})")

        return f"{self._free_do_group_map[action]}(I)"

    # ========== Atoms ==========

    def prop(self, items):
        """p  →  prop(I, 'p') for actual propositions, or f(I) for named formulas

        Named formulas (generated by expander) start with 'f' followed by digits.
        Actual propositions are anything else.
        """
        prop_name = str(items[0])

        # Check if this is a named formula reference (f1, f2, f3, etc.)
        import re
        if re.match(r'^f\d+$', prop_name):
            # This is a named formula - reference it as a predicate
            predicate = self._sanitize_predicate(prop_name)
            self.predicates.add(predicate)
            return f"{predicate}(I)"
        else:
            # This is an actual proposition - wrap in prop(...)
            return f"prop(I, '{prop_name}')"

    def top(self, items):
        """T  →  'T' (always true)"""
        # In Datalog, we could use a tautology or special predicate
        # For now, return a simple true marker
        return "top(I)"

    def bottom(self, items):
        """_L  →  'F' (always false)"""
        return "bottom(I)"

    def parens(self, items):
        """(φ)  →  φ (just return inner)"""
        return items[0]

    # ========== Action Expressions ==========

    def individual_action(self, items):
        """action_id → action string"""
        return str(items[0])

    def group_action(self, items):
        """{mappings} → conjunction of individual actions

        Group actions like {1:sd, 2:ha} expand to:
        (action(I, 'sd1') & action(I, 'ha2'))
        """
        action_predicates = []
        for mapping in items:
            # mapping is a string like "1:sd" or "2:ha"
            if ':' in mapping:
                agent, action = mapping.split(':', 1)
                # Create composed action (e.g., sd1, ha2)
                composed_action = f"{action}{agent}"
                action_predicates.append(f"action(I, '{composed_action}')")
            else:
                # Single action without agent
                action_predicates.append(f"action(I, '{mapping}')")

        # If only one action, return it directly
        if len(action_predicates) == 1:
            return action_predicates[0]

        # Multiple actions - create conjunction
        result = action_predicates[0]
        for pred in action_predicates[1:]:
            result = f"({result} & {pred})"
        return result

    def action_mapping(self, items):
        """num:action or action → mapping string"""
        if len(items) == 2:
            return f"{items[0]}:{items[1]}"
        return str(items[0])

    def action_id(self, items):
        """action without agent → action string"""
        return str(items[0])

    # ========== Agent Expressions ==========

    def individual_agent(self, items):
        """agent_num → agent string"""
        return str(items[0])

    def agent_group(self, items):
        """{nums} → agent group string"""
        nums = ', '.join(str(n) for n in items)
        return f'{{{nums}}}'

    def named_agent_group(self, items):
        """agent_name → agent name string"""
        return str(items[0])

    # ========== PDL-style Modalities (should not appear in expanded formulas) ==========

    def pdl_box(self, items):
        """[action]φ - should not appear after expansion"""
        raise ValueError(f"pdl_box should not appear in expanded formulas: {items}")

    def pdl_diamond(self, items):
        """<action>φ - should not appear after expansion"""
        raise ValueError(f"pdl_diamond should not appear in expanded formulas: {items}")

    # ========== Causal Operators (should not appear in expanded formulas) ==========

    def expected_result(self, items):
        """do(a) [+]-> φ - should not appear after expansion"""
        raise ValueError(f"expected_result should not appear in expanded formulas: {items}")

    def but_for(self, items):
        """but(a, φ) - should not appear after expansion"""
        raise ValueError(f"but_for should not appear in expanded formulas: {items}")

    def ness(self, items):
        """ness(a, φ) - should not appear after expansion"""
        raise ValueError(f"ness should not appear in expanded formulas: {items}")

    # ========== STIT Operators (should not appear in expanded formulas) ==========

    def xstit(self, items):
        """[agent XSTIT]φ - should not appear after expansion"""
        raise ValueError(f"xstit should not appear in expanded formulas: {items}")

    def dxstit(self, items):
        """[agent DXSTIT]φ - should not appear after expansion"""
        raise ValueError(f"dxstit should not appear in expanded formulas: {items}")

    # ========== Responsibility Operators (should not appear in expanded formulas) ==========

    def pres(self, items):
        """[agent pres]φ - should not appear after expansion"""
        raise ValueError(f"pres should not appear in expanded formulas: {items}")

    def sres(self, items):
        """[agent sres]φ - should not appear after expansion"""
        raise ValueError(f"sres should not appear in expanded formulas: {items}")

    def res(self, items):
        """[agent res]φ - should not appear after expansion"""
        raise ValueError(f"res should not appear in expanded formulas: {items}")

    def opposing(self, items):
        """action1 |> action2 - should not appear after expansion"""
        raise ValueError(f"opposing should not appear in expanded formulas: {items}")

    # ========== Program Generation ==========

    def generate_rules(self):
        """Generate all Datalog rules as string."""
        return '\n\n'.join(self.rules)
