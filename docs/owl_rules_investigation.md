# OWL Rules / DL-Safe Rules Investigation

## Goal

Add an alternative OWL serializer using DL-safe rules (and/or SPARQL) for responsibility
operator encoding, primarily to compare performance against the existing SubClassOf/TBox approach.

## Findings

### Konclude rule support

**CORRECTED 2026-09-02** (was: "Konclude parses DL-safe rules but does not
reason with them... DL-safe rules are silently dropped," citing
`COWL2QtXMLOntologyParser.cpp`'s `jumpFunctionParseIgnoredNode` handler).
Directly tested against the real ALOn OWL output (3.1-scale, 19 queries,
and 3.5-scale, 91 queries), using the existing `dlsafe_rules.py`
post-processor to convert query-definition axioms into `DLSafeRule` form:
**Konclude does reason over `DLSafeRule` axioms correctly** — exact match
to the plain-`SubClassOf` baseline at both scales, confirmed via a
negative-control test (deleting one rule removed exactly its derived class
and nothing else). See
`/Users/mbassbp2/Development/reasoners/Konclude/alon_test_suite/findings/perf-002-dlsafe-rules-no-faster-than-realization/`
for full details. Whatever the cited parser code does/did, it does not
describe the behavior of the Konclude build currently in use here.

However, realization via `DLSafeRule` is **not faster** than plain
`SubClassOf` axioms at either scale tested (3.1: 0.81s vs 0.24s; 3.5:
42.77s vs 49.41s — same order of magnitude, no win) — so this is a
correctness/robustness option, not a performance one. The original
`jumpFunctionParseIgnoredNode` citation below is left in place for
reference/history, not as a current claim about Konclude's behavior.

```cpp
mParseFunctionJumpHash.insert("DLSafeRule",
    &COWL2QtXMLOntologyParser::jumpFunctionParseIgnoredNode);
mParseFunctionJumpHash.insert("owl:DLSafeRule",
    &COWL2QtXMLOntologyParser::jumpFunctionParseIgnoredNode);
```

**Nominal schemas** (OWL 2 extension) — not yet tested; `DLSafeRule` (plain
SWRL-style rule syntax) is a different construct and is the one confirmed
working above.

### HermiT

Supports SWRL rules natively via the OWL API. Rules are embedded in OWL/XML as
`<DLSafeRule>` elements and reasoned over together with the TBox/ABox.

Key constraint: SWRL is **Horn-only** — no NAF in rule bodies. Negative conditions
like `¬inevitable(φ)` would need to be pre-asserted in the ABox rather than derived.

### SPARQL

Orthogonal to the rule question. After reasoning (HermiT/Pellet/Konclude), SPARQL can
query the classified ontology. Responsibility operators would become SPARQL SELECT patterns
("which individuals are in query class X?") rather than rule heads.

## Open questions (to verify)

- Does Konclude support **nominal schemas** specifically (distinct from the
  plain `DLSafeRule` syntax confirmed working above) for rule-like
  reasoning, and how close is that to the existing SubClassOf+nominal
  translation? Not yet tested.
- What is the exact SWRL/DL-safe rule format HermiT expects in OWL/XML?
  (Reference: https://www.cs.ox.ac.uk/files/2445/rulesyntaxTR.pdf)
- Is HermiT available in the target environment (jar / owlready2 / CLI)?
- Are DL-safe rules and SPARQL queries equivalent in expressivity for our use case,
  or does one cover cases the other doesn't?
- Can negative ABox pre-computation (for ¬inevitable, ¬opposition) be reused from
  the existing serializer without modification?

## Possible approaches

1. **SWRL + HermiT**: Rules in OWL/XML, negative conditions pre-asserted, HermiT reasons.
2. **SPARQL over reasoned ontology**: Generate OWL (existing serializer), run reasoner,
   query results via SPARQL SELECT.
3. **Nominal schemas + Konclude**: Stay within OWL 2 DL, use nominal schemas instead of
   rules — may be close to what the current serializer already does.
4. **Hybrid**: SWRL rules for positive operator conditions, SPARQL for result extraction.
