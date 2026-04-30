# OWL Rules / DL-Safe Rules Investigation

## Goal

Add an alternative OWL serializer using DL-safe rules (and/or SPARQL) for responsibility
operator encoding, primarily to compare performance against the existing SubClassOf/TBox approach.

## Findings

### Konclude rule support

Konclude **parses** DL-safe rules but does not reason with them. In `COWL2QtXMLOntologyParser.cpp`:

```cpp
mParseFunctionJumpHash.insert("DLSafeRule",
    &COWL2QtXMLOntologyParser::jumpFunctionParseIgnoredNode);
mParseFunctionJumpHash.insert("owl:DLSafeRule",
    &COWL2QtXMLOntologyParser::jumpFunctionParseIgnoredNode);
```

Rule data structures exist in the parser (`CParseRuleAtom`, `CRuleClassAtomTermExpression`,
`CRulePropertyAtomTermExpression`, etc.) but there is no corresponding reasoner component
that consumes them. DL-safe rules are silently dropped.

**Nominal schemas** (OWL 2 extension) may be a different story — to be checked.

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

- Does Konclude support **nominal schemas** for rule-like reasoning, and how close is
  that to the existing SubClassOf+nominal translation?
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
