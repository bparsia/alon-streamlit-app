"""
SPARQL serialization for ALOn formulas.

FormulaToSPARQL -- Lark Transformer that converts expanded ALOn formula
axioms (in `formula => name` syntax, produced by the ordinary
ExpanderTransformer -- no SPARQL-specific expander subclass needed, see
docs/sparql_serializer.md) into SPARQL WHERE-clause graph-pattern
fragments.

Every fragment is phrased in terms of a single canonical index variable
`?idx0`, mirroring FormulaToDatalog's use of a fixed `I` -- when a
construct (next/diamond/box) needs to talk about a different index, it
substitutes `?idx0` for a fresh `?idxN` in its child's already-transformed
fragment (same `_fresh_var`/`_substitute_var` technique FormulaToDatalog
already uses, ported to SPARQL variable syntax) rather than threading a
variable name top-down through the tree.

Negation (`negation`, and `box`'s internal double-negation) uses nested
`MINUS`, confirmed correct and stable on the fixed konclude/rasqal build
(alon_test_suite findings bug-003/bug-004, both independently
re-verified). The wrapping rule matters: negating a compound sub-pattern
means wrapping the ENTIRE already-computed inner fragment in one more
MINUS level, not reusing the inner fragment's own MINUS structure
directly -- getting this wrong silently computes something else, not an
error (see alon_test_suite findings/bug-005, a query-authoring mistake
made once already during this investigation, not a reasoner defect).
"""

from lark import Transformer


class _Disjunction:
    """Marks a not-yet-finalized disjunction: a list of un-UNIONed branch
    fragments. `conjunction` looks for this to distribute sibling
    conjuncts into each branch before finalizing the "{...} UNION {...}"
    string (see `conjunction`'s docstring for why finalizing eagerly, in
    `disjunction` itself, produces wrong results on this reasoner build).
    `expansion_axiom` finalizes any _Disjunction that reaches it directly
    (a formula whose top-level connective is disjunction, with no
    enclosing conjunction) the same way, distributing its own `owl:Thing`
    anchor into each branch.
    """

    def __init__(self, branches):
        self.branches = branches


class FormulaToSPARQL(Transformer):
    """Converts expanded ALOn formula axioms to SPARQL WHERE-clause fragments.

    Input:  axioms in `formula => name` syntax produced by ExpanderTransformer
    Output: SPARQL query strings accumulated in self.queries
    """

    BASE_VAR = "?idx0"

    def __init__(self, base_iri="http://www.semanticweb.org/alon#", name_to_formula=None):
        self.base_iri = base_iri
        self.classes = set()
        self.queries = {}  # name -> full "SELECT ?idx0 WHERE {...}" query string
        self.name_to_formula = name_to_formula or {}
        self.var_counter = 0

    def _sanitize_name(self, name):
        # Same punctuation set FormulaToOWL._sanitize_name strips, for the
        # same reason (group-action notation isn't valid in an IRI
        # fragment/local name) -- see that method's comment for why v/&/~
        # etc. are deliberately NOT stripped here.
        result = str(name)
        for ch in '{}:, ()[]':
            result = result.replace(ch, '_')
        return result

    def _class_iri(self, name):
        sanitized = self._sanitize_name(name)
        self.classes.add(sanitized)
        return f"alon:{sanitized}"

    def _fresh_var(self):
        self.var_counter += 1
        return f"?idx{self.var_counter}"

    def _substitute_var(self, fragment, old_var, new_var):
        """Rename every occurrence of old_var to new_var in an
        already-transformed fragment. SPARQL variables are whole tokens
        (?idx0, ?idx1, ...), so a straight substring replace is safe --
        unlike Datalog's bare `I`, there's no risk of matching inside a
        longer identifier. Finalizes a _Disjunction first (see
        `_finalize`) since substitution needs a plain string."""
        return self._finalize(fragment).replace(old_var, new_var)

    def _finalize(self, fragment, extra_prefix=""):
        """Turn a _Disjunction into a plain "{...} UNION {...}" string.
        No-op for already-plain strings.

        Every branch gets its own `?idx a owl:Thing .` anchor (plus
        `extra_prefix`, for callers distributing a sibling conjunct --
        see `conjunction`) placed BEFORE its own content, unconditionally
        -- confirmed empirically (not a documented SPARQL/Rasqal
        limitation) that omitting a per-branch anchor, even when the
        whole UNION already has some anchor elsewhere in an enclosing
        scope, gives wrong results on this Konclude/rasqal build whenever
        any branch contains a MINUS. Repeating a redundant `owl:Thing`
        triple inside every branch is the only shape confirmed safe;
        tried and rejected: anchor once before the whole union (wrong),
        anchor once inside the union but outside branches (invalid/empty
        MINUS per alon_test_suite findings/bug-006), anchor omitted
        entirely when a branch already has its own MINUS's owl:Thing
        (wrong -- see the ness_sd1_q investigation this was found from).
        """
        if isinstance(fragment, _Disjunction):
            branches = " UNION ".join(
                f"{{\n  {self.BASE_VAR} a owl:Thing .\n  {extra_prefix}{b}  }}"
                for b in fragment.branches
            )
            return f"  {branches}\n"
        return fragment

    # ---- top-level axiom ----

    def expansion_axiom(self, items):
        """formula => name  ->  a full SELECT query computing name's
        satisfying-individual set, stored in self.queries[name]."""
        formula_pattern, name = items
        name_str = str(name)
        if isinstance(formula_pattern, _Disjunction):
            where_body = self._finalize(formula_pattern)
        else:
            where_body = f"  {self.BASE_VAR} a owl:Thing .\n  {formula_pattern}"
        query = (
            f"SELECT {self.BASE_VAR} WHERE {{\n"
            f"{where_body}"
            f"}}"
        )
        self.queries[name_str] = query
        return query

    # ---- propositional ----

    def biconditional(self, items):
        if len(items) == 1:
            return items[0]
        result = items[-1]
        for item in reversed(items[:-1]):
            fwd = self.implication([item, result])
            back = self.implication([result, item])
            result = self.conjunction([fwd, back])
        return result

    def implication(self, items):
        """p -> q  ==  ~p v q, but NOT built via the generic
        negation()+disjunction() composition -- that produces a UNION
        branch whose entire content is `negation`'s own `MINUS {...}`
        output with nothing preceding it in that branch's own `{ }`
        group, which is a degenerate/invalid MINUS use (previously
        silently returned wrong empty results; a real Rasqal/Konclude
        fix now makes this loudly error instead of silently miscomputing
        -- see alon_test_suite findings/bug-006).

        Instead, compile directly to `q UNION (owl:Thing MINUS p)`: the
        antecedent's negation is expressed as one MINUS block anchored
        by its OWN `?idx a owl:Thing .` triple placed BEFORE the MINUS
        keyword (not inside it) in that branch -- this is the same shape
        bug-006's corrected fixture uses and confirmed correct, and it
        sidesteps the bare-negation-as-a-branch problem entirely by
        construction, not by relying on branch ordering (per user
        direction: special-casing implication here is in-keeping with
        this codebase's existing per-backend override pattern, e.g.
        PyDatalogExpanderTransformer.pdl_box avoiding disjunction for
        pyDatalog's sake).
        """
        if len(items) == 1:
            return items[0]
        result = items[-1]
        for item in reversed(items[:-1]):
            antecedent = self._finalize(item)
            not_antecedent_branch = (
                f"{self.BASE_VAR} a owl:Thing .\n"
                f"    MINUS {{\n"
                f"      {antecedent}    }}\n"
            )
            result_branch = self._finalize(result)
            result = _Disjunction([not_antecedent_branch, result_branch])
        return result

    def disjunction(self, items):
        if len(items) == 1:
            return items[0]
        return _Disjunction(items)

    def conjunction(self, items):
        """SPARQL AND is juxtaposition -- concatenate fragments as-is,
        EXCEPT when a conjunct is itself a disjunction (an item built by
        `disjunction`, still a list of un-UNIONed branches at this point,
        not yet a "{...} UNION {...}" string -- see _Disjunction).

        `a & (b v c)` == `(a & b) v (a & c)` -- distribute any other
        conjuncts into each branch (via `_finalize`'s extra_prefix) rather
        than leaving them as siblings of the union. Confirmed necessary
        (not just tidy): see `_finalize`'s docstring for why every UNION
        branch needs its own `owl:Thing` anchor regardless.

        Single-item passthrough (checked FIRST, before scanning for
        _Disjunction items): the grammar wraps every operator level even
        when there's exactly one operand (conjunction/disjunction/
        implication/biconditional all have this shape), so a bare
        `disjunction(...)` result reaching here as `conjunction`'s ONLY
        item must stay an un-finalized _Disjunction and be passed straight
        through -- eagerly finalizing it here (as an earlier version of
        this method did) finalizes one tree level too early, before the
        real top-level consumer (expansion_axiom) ever sees it, causing a
        doubled/redundant owl:Thing anchor once expansion_axiom adds its
        own on top of an already-plain-string formula_pattern. Confirmed
        by tracing a real query (ness's `f7`) where this exact double-
        anchor construction produced wrong results.
        """
        if len(items) == 1:
            return items[0]
        disjunctions = [i for i in items if isinstance(i, _Disjunction)]
        if not disjunctions:
            return "".join(items)
        if len(disjunctions) > 1:
            raise NotImplementedError(
                "conjunction of two or more disjunctions -- distribution "
                "here would need a full cross-product of branches, not "
                "yet implemented (not yet seen in real expanded axioms)"
            )
        disj = disjunctions[0]
        others = [i for i in items if i is not disj]
        prefix = "".join(others)
        # Return an UNFINALIZED _Disjunction (prefix distributed into
        # each branch's raw text, no owl:Thing anchors or { } wrapping
        # yet) -- NOT a call to _finalize here. Finalizing eagerly at
        # this tree level, rather than passing the marker up to whichever
        # caller is the real top-level consumer (expansion_axiom, or an
        # enclosing negation/conjunction), reintroduces exactly the
        # doubled-anchor bug this method's docstring above describes for
        # the single-item-passthrough case, just one level deeper: a
        # conjunction nested inside another conjunction/negation (e.g.
        # res's `do(sd1) & f2 & (branch1 v branch2) & ~[]Xq & ~[]do(sd1)`
        # once f2/branch1/branch2 are fully inlined -- see
        # streamlit_app/utils.py's _inline_fN_references) still needs its
        # _Disjunction-ness visible to ITS enclosing caller, not silently
        # collapsed to a string here.
        return _Disjunction([f"{prefix}{branch}" for branch in disj.branches])

    def negation(self, items):
        """~phi  ->  idx does NOT satisfy phi.

        Wraps the ENTIRE inner fragment (whatever it is, including its
        own nested MINUS blocks if it's itself a box/negation) in one
        more outer MINUS layer against the base variable -- confirmed
        this exact wrapping is required (not "reuse the inner MINUS body
        directly"), see alon_test_suite findings/bug-005. The `?idx a
        owl:Thing` triple is structurally required here (not just
        belt-and-suspenders): a MINUS block needs at least one positive
        triple pattern binding the variable being compared, or there's
        nothing for MINUS's compatibility check to act on -- confirmed
        by testing box(implication(...)) with this triple removed, which
        produced a degenerate empty-bodied outer MINUS and wrong results.

        If `inner` is a _Disjunction (e.g. negating an implication's
        `~A v B` form directly), `_finalize` gives each branch its own
        `owl:Thing` anchor -- see that method's docstring.
        """
        inner = items[0]
        if isinstance(inner, _Disjunction):
            inner_str = self._finalize(inner)
        else:
            inner_str = f"    {self.BASE_VAR} a owl:Thing .\n    {inner}"
        return (
            f"  MINUS {{\n"
            f"    {inner_str}"
            f"  }}\n"
        )

    # ---- modal ----

    def box(self, items):
        """[]phi  ->  every same-moment index satisfies phi.

        Same double-negation shape as FormulaToDatalog.box
        (same_moment(I,J) & ~phi(J), then box = ~violation) but expressed
        as nested MINUS directly, in one query, rather than a named
        helper predicate -- SPARQL has no rule/predicate-definition
        mechanism the way Datalog does, so each box occurrence is written
        inline at its own position (confirmed acceptable: post-expansion
        formulas don't nest box more than a few levels deep, per
        docs/sparql_serializer_ABANDONED.md's original analysis, still
        true here).
        """
        j_var = self._fresh_var()
        inner_at_j = self._substitute_var(items[0], self.BASE_VAR, j_var)
        return (
            f"  MINUS {{\n"
            f"    {self.BASE_VAR} alon:same_moment {j_var} .\n"
            f"    MINUS {{\n"
            f"      {inner_at_j}    }}\n"
            f"  }}\n"
        )

    def diamond(self, items):
        """<>phi  ->  some same-moment index satisfies phi. Plain
        existential, no negation needed."""
        j_var = self._fresh_var()
        inner_at_j = self._substitute_var(items[0], self.BASE_VAR, j_var)
        return (
            f"  {self.BASE_VAR} alon:same_moment {j_var} .\n"
            f"  {inner_at_j}"
        )

    def next(self, items):
        """Xphi  ->  phi holds at the (unique) successor index. No
        negation needed -- succ is FunctionalObjectProperty, so there's
        exactly one successor per index (see FormulaToOWL.next's comment
        for the same fact and why it matters for the OWL side)."""
        j_var = self._fresh_var()
        inner_at_j = self._substitute_var(items[1], self.BASE_VAR, j_var)
        return (
            f"  {self.BASE_VAR} alon:succ {j_var} .\n"
            f"  {inner_at_j}"
        )

    # ---- action predicates ----

    def _intersect(self, exprs):
        return "".join(exprs)

    def do_action(self, items):
        action = items[0]
        if isinstance(action, list):
            return self._intersect([f"  {self.BASE_VAR} a {self._class_iri(a)} .\n" for a in action])
        return f"  {self.BASE_VAR} a {self._class_iri(action)} .\n"

    def free_do_action(self, items):
        """free_do(a)  ->  do(a) & ~Opp2a -- negation of a single class-
        membership atom, same MINUS-wrapping shape as `negation` above
        (see that method's docstring for why the MINUS body needs the
        `?idx a owl:Thing` anchor) but specialized to a single triple
        pattern rather than an arbitrary compiled inner fragment (there's
        no recursively-compiled sub-formula here, just one class check to
        negate)."""
        action = items[0]
        if isinstance(action, list):
            actions = action
        else:
            actions = [action]
        parts = []
        for a in actions:
            parts.append(f"  {self.BASE_VAR} a {self._class_iri(a)} .\n")
            opp_class = self._class_iri(f"Opp2{a}")
            parts.append(
                f"  MINUS {{\n"
                f"    {self.BASE_VAR} a owl:Thing .\n"
                f"    {self.BASE_VAR} a {opp_class} .\n"
                f"  }}\n"
            )
        return "".join(parts)

    # ---- atoms ----

    def prop(self, items):
        return f"  {self.BASE_VAR} a {self._class_iri(str(items[0]))} .\n"

    def top(self, items):
        return f"  {self.BASE_VAR} a owl:Thing .\n"

    def bottom(self, items):
        # Always-false: an unsatisfiable triple pattern rather than a
        # SPARQL-level FILTER(false), so it composes the same way as
        # every other fragment (plain WHERE-clause text, no special
        # top-level-only syntax) when nested inside conjunction/box/etc.
        return f"  {self.BASE_VAR} a alon:__unsatisfiable_bottom__ .\n"

    def parens(self, items):
        return items[0]

    # ---- action/agent expressions ----
    # Same grammar rules FormulaToOWL handles (alon_grammar_clean.lark's
    # action_expr chain runs individual_action/group_action/
    # action_mapping/action_id before do_action/free_do_action ever see a
    # value) -- without these, do_action receives a raw Lark Tree, not a
    # string.

    def individual_action(self, items):
        return self._sanitize_name(str(items[0]))

    def group_action(self, items):
        composed = []
        for mapping in items:
            if ':' in mapping:
                agent, action = mapping.split(':', 1)
                composed.append(f"{action}{agent}")
            else:
                composed.append(mapping)
        return composed

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
    # Same guard FormulaToOWL has: these operators are expanded away by
    # ExpanderTransformer before FormulaToSPARQL ever sees an axiom
    # string, so seeing one here means expansion is broken -- fail loudly
    # rather than silently mishandle it.

    def _must_not_appear(self, name, items):
        raise ValueError(f"{name} should not appear in expanded formulas: {items}")

    def pdl_box(self, items):       self._must_not_appear("pdl_box", items)
    def pdl_diamond(self, items):   self._must_not_appear("pdl_diamond", items)
    def expected_result(self, items): self._must_not_appear("expected_result", items)
    def but_for(self, items):       self._must_not_appear("but_for", items)
    def ness(self, items):          self._must_not_appear("ness", items)
    def msc(self, items):           self._must_not_appear("msc", items)
    def ness_via_msc(self, items):  self._must_not_appear("ness_via_msc", items)
    def xstit(self, items):         self._must_not_appear("xstit", items)
    def dxstit(self, items):        self._must_not_appear("dxstit", items)
    def pres(self, items):          self._must_not_appear("pres", items)
    def sres(self, items):          self._must_not_appear("sres", items)
    def res(self, items):           self._must_not_appear("res", items)
    def res_msc(self, items):       self._must_not_appear("res_msc", items)
    def res_candidate(self, items): self._must_not_appear("res_candidate", items)
    def opposing(self, items):      self._must_not_appear("opposing", items)
