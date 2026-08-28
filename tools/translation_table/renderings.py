"""
Hand-maintained, human-polished translation renderings for the primitive
formula-operator table.

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
                            "datalog": "<LaTeX-ish math for the Datalog rendering>"}}

First-pass drafts below were written by directly reading the extracted
source (not guessed) -- still worth a human review pass, especially for
the "helper"-shaped rows (box, disjunction, do_action, free_do_action on
the Datalog side), which need a two-part notation (helper rule + reference)
that has no single settled convention yet.
"""

PRIMITIVE_RENDERINGS = {
    "biconditional": {
        "owl": r"$(\neg\phi \sqcup \psi) \sqcap (\neg\psi \sqcup \phi)$",
        "datalog": r"$(\phi \to \psi)$ and $(\psi \to \phi)$, each per the implication rendering below",
    },
    "implication": {
        "owl": r"$\neg\phi \sqcup \psi$",
        "datalog": r"delegates to disjunction: $\neg\phi \vee \psi$ (see below)",
    },
    "disjunction": {
        "owl": r"$\phi \sqcup \psi$ (\texttt{ObjectUnionOf})",
        "datalog": (
            r"helper predicate $h$, one rule per disjunct: "
            r"$h(I) \Leftarrow \phi(I)$, \quad $h(I) \Leftarrow \psi(I)$ "
            r"-- pyDatalog has no direct OR between rule-body terms"
        ),
    },
    "conjunction": {
        "owl": r"$\phi \sqcap \psi$ (\texttt{ObjectIntersectionOf})",
        "datalog": r"$\phi(I) \mathbin{\&} \psi(I)$",
    },
    "negation": {
        "owl": r"$\neg\phi$ (\texttt{ObjectComplementOf})",
        "datalog": r"$\sim\!\phi(I)$",
    },
    "box": {
        "owl": r"$\forall\, \mathit{same\_moment}.\, \phi$ (\texttt{ObjectAllValuesFrom})",
        "datalog": (
            r"helper predicate $h$: $h(I) \Leftarrow \mathit{same\_moment}(I,J) \mathbin{\&} "
            r"{\sim}\phi(J)$; box itself is $\sim\! h(I)$ "
            r"(box holds iff no same-moment violation exists)"
        ),
    },
    "diamond": {
        "owl": r"$\exists\, \mathit{same\_moment}.\, \phi$ (\texttt{ObjectSomeValuesFrom})",
        "datalog": r"$\mathit{same\_moment}(I,J) \mathbin{\&} \phi(J)$",
    },
    "next": {
        "owl": (
            r"$\exists\, \mathit{succ}.\, \phi$ (\texttt{ObjectSomeValuesFrom}; $\mathit{succ}$ "
            r"is \texttt{FunctionalObjectProperty}, so $\exists$/$\forall$ are equivalent here)"
        ),
        "datalog": r"$\mathit{succ}(I,J) \mathbin{\&} \phi(J)$",
    },
    "do_action": {
        "owl": r"$\alpha$ (the action's own OWL class; \texttt{ObjectIntersectionOf} if $\alpha$ is a group action)",
        "datalog": (
            r"$\mathit{action}(I, \alpha)$ for an individual action; for a group action, a helper "
            r"predicate $h$ with $h(I) \Leftarrow \mathit{action}(I,\alpha_1) \mathbin{\&} \cdots$"
        ),
    },
    "free_do_action": {
        "owl": r"$\alpha \sqcap \neg\mathit{Opp2}\alpha$ (action class minus its opposing class)",
        "datalog": (
            r"helper predicate: $h(I) \Leftarrow \mathit{action}(I,\alpha) \mathbin{\&} "
            r"{\sim}\mathit{opposing}_\alpha(I)$"
        ),
    },
    "prop": {
        "owl": r"the proposition's own OWL class",
        "datalog": r"$\mathit{prop}(I, p)$",
    },
    "top": {
        "owl": r"$\top$ (\texttt{owl:Thing})",
        "datalog": r"$\mathit{top}(I)$",
    },
    "bottom": {
        "owl": r"$\bot$ (\texttt{owl:Nothing})",
        "datalog": r"$\mathit{bottom}(I)$",
    },
}
