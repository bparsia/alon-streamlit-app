"""
Hand-maintained, human-polished translation renderings for the ALOn
logic-syntax primitive table (Table 2 -- the paper's own formal grammar,
see extract_primitives.py's module docstring).

This is NOT auto-derived from extract_primitives.py's extracted Python
source -- it's a curated companion, edited directly by a human (per
explicit design decision: code listings stay as auditable ground truth,
polished math/logic notation is a separate hand-written layer, not
mechanically generated). build_ir.py cross-checks that every row
extract_primitives.py finds has an entry here (fails loudly if not), so
this file can't silently drift out of sync by omission -- but its CONTENT
is not verified against the code automatically; a human is responsible
for keeping the notation actually correct when the underlying method
changes shape.

Each entry: {method_name: {"owl": "<LaTeX-ish math for the OWL rendering>",
                            "sparql": "<LaTeX-ish for the SPARQL rendering>",
                            "datalog": "<LaTeX-ish math for the Datalog rendering>"}}

SPARQL renderings describe alo_translator/serializers/sparql.py's
FormulaToSPARQL output -- confirmed against real generated queries and
cross-checked against the Konclude baselines (tests/test_konclude_sparql_baselines.py),
not hand-guessed. See docs/sparql_serializer.md for the design and the
$\\rm MINUS$-shape pitfalls that make box/negation's rendering below not
simply "the OWL rendering with SPARQL keywords swapped in" -- the
double-negation shape for box, and the anchor-placement rule for
negation, were both the site of real bugs before landing on the rendering
described here (alon_test_suite findings bug-005/bug-006).
"""

PRIMITIVE_RENDERINGS = {
    "prop": {
        "owl": r"the proposition's own OWL class",
        "sparql": r"$\mathtt{?idx\ a\ alon}{:}p\,.$",
        "datalog": r"$\mathit{prop}(I, p)$",
    },
    "do_action": {
        "owl": r"$\alpha$ (the action's own OWL class; \texttt{ObjectIntersectionOf} if $\alpha$ is a group action)",
        "sparql": (
            r"$\mathtt{?idx\ a\ alon}{:}\alpha\,.$ for an individual action; "
            r"for a group action, one such triple per conjunct action"
        ),
        "datalog": (
            r"$\mathit{action}(I, \alpha)$ for an individual action; for a group action, a helper "
            r"predicate $h$ with $h(I) \Leftarrow \mathit{action}(I,\alpha_1) \mathbin{\&} \cdots$"
        ),
    },
    "conjunction": {
        "owl": r"$\phi \sqcap \psi$ (\texttt{ObjectIntersectionOf})",
        "sparql": (
            r"pattern juxtaposition (SPARQL \texttt{AND} is implicit) -- "
            r"EXCEPT when a conjunct is itself a disjunction: "
            r"$\phi \wedge (\psi \vee \chi) \equiv (\phi\wedge\psi) \vee (\phi\wedge\chi)$ "
            r"is applied first, distributing $\phi$ into each \texttt{UNION} branch "
            r"(confirmed required on the target Konclude/Rasqal build, not just tidy -- "
            r"see module docstring)"
        ),
        "datalog": r"$\phi(I) \mathbin{\&} \psi(I)$",
    },
    "negation": {
        "owl": r"$\neg\phi$ (\texttt{ObjectComplementOf})",
        "sparql": (
            r"$\mathtt{?idx\ a\ owl}{:}\mathtt{Thing\ .\ MINUS\ \{\ }\phi\mathtt{\ \}}$ -- "
            r"the anchor triple MUST precede \texttt{MINUS} (not be nested inside it); "
            r"getting this backwards was a real, silently-wrong-answer bug during development"
        ),
        "datalog": r"$\sim\!\phi(I)$",
    },
    "next": {
        "owl": (
            r"$\exists\, \mathit{succ}.\, \phi$ (\texttt{ObjectSomeValuesFrom}; $\mathit{succ}$ "
            r"is \texttt{FunctionalObjectProperty}, so $\exists$/$\forall$ are equivalent here)"
        ),
        "sparql": r"$\mathtt{?idx\ alon}{:}\mathtt{succ\ ?idx'\ .}$ then $\phi$ on $\mathtt{?idx'}$",
        "datalog": r"$\mathit{succ}(I,J) \mathbin{\&} \phi(J)$",
    },
    "box": {
        "owl": r"$\forall\, \mathit{same\_moment}.\, \phi$ (\texttt{ObjectAllValuesFrom})",
        "sparql": (
            r"double-negation via nested \texttt{MINUS}: "
            r"$\mathtt{MINUS\ \{\ ?idx\ alon}{:}\mathtt{same\_moment\ ?idx'\ .\ MINUS\ \{\ }\phi\mathtt{\ \}\ \}}$ "
            r"on $\mathtt{?idx'}$ -- written inline at each occurrence (SPARQL has no named/"
            r"reusable rule mechanism the way Datalog's helper predicates do)"
        ),
        "datalog": (
            r"helper predicate $h$: $h(I) \Leftarrow \mathit{same\_moment}(I,J) \mathbin{\&} "
            r"{\sim}\phi(J)$; box itself is $\sim\! h(I)$ "
            r"(box holds iff no same-moment violation exists)"
        ),
    },
}
