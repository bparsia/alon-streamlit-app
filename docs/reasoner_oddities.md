# Reasoners be weird

Empirically confirmed, reproducible reasoner behaviors that don't have a
known root cause. Not speculation -- each entry here was isolated via a
minimal or near-minimal reproduction on real project data, not guessed at.
Per the standing no-reasoner-hypothesizing rule, do not explain *why* these
happen without further real investigation; record what was tested and
what happened.

## HermiT (via ROBOT): a DL-safe rule whose entire body is a standalone
## `ObjectAllValuesFrom(succ, φ)` atom breaks unrelated rules elsewhere
## in the same ontology (2026-08-26)

**Setup:** `robot reason -r HermiT -i <in.owl> -n true -A ClassAssertion -d true convert --format owx -o <out.owx>` (the command used by `HermitAdapter`, `alo_translator/reasoners/hermit.py`) against a real serialized ALOn ontology (3.1.mmd's `m/h1/q` eval point), converting some `SubClassOf` query-definition axioms to `DLSafeRule`s (see `alo_translator/serializers/dlsafe_rules.py`).

**Symptom:** converting `outcome_m_h1_q`'s axiom -- `SubClassOf(ObjectAllValuesFrom(succ, q), outcome_m_h1_q)` -- into a `DLSafeRule` whose body is `ClassAtom(ObjectAllValuesFrom(succ, q), Variable(x))` causes *other, logically unrelated* rules (e.g. `pres_1_q_m_h1_q`, and an internal helper class `f1`) to stop deriving correctly on the same individual, even when those other rules/axioms share no classes with `outcome_m_h1_q` at all.

**Isolation, in order:**
- Not a depth/chain-length issue: a synthetic 4-hop rule chain (`sd1 -> hop1 -> hop2 -> hop3 -> hop4`, each a separate `DLSafeRule`) derives correctly end to end.
- Not about referencing a rule-derived class by name vs. inline duplication: rewriting the referencing rule (`f1`) to name `outcome_m_h1_q` explicitly instead of duplicating its body expression made no difference -- still failed.
- Is specifically about `outcome_m_h1_q`'s rule form: same class, same body content, works correctly whenever it's a plain `SubClassOf` axiom OR a ground `ClassAssertion` fact; only fails when it's a `DLSafeRule`.
- Fix confirmed: swapping `outcome_m_h1_q`'s body from `ObjectAllValuesFrom(succ, q)` to `ObjectSomeValuesFrom(succ, q)` (logically equivalent here since `succ` is `FunctionalObjectProperty` -- exactly one successor per index, confirmed via the OWL serializer's own `FunctionalObjectProperty` declaration) makes the previously-broken `pres_1_q_m_h1_q` derive correctly again, with nothing else changed.
- The `ObjectSomeValuesFrom(succ, q)` substitution was independently verified correct via Konclude too (plain `SubClassOf` axiom form, not a rule) -- same 14-query-class result as the original `ObjectAllValuesFrom` version, not just "doesn't trigger the HermiT bug."

**What this does NOT explain:** why a standalone `ObjectAllValuesFrom(succ, φ)` rule body specifically triggers this, why it only affects *other* rules rather than itself, or whether `box`/`same_moment`'s `ObjectAllValuesFrom` (NOT functional -- multiple same-moment individuals exist) would have the same issue. `same_moment`'s `ObjectAllValuesFrom` was NOT touched by the fix below, since substituting `ObjectSomeValuesFrom` there would NOT be logically equivalent (same_moment is not functional) -- if a similar HermiT anomaly is ever found for `box`, it cannot be fixed the same way.

**Resolution applied:** fixed at the source, not as a DL-safe-rules-specific post-processing step -- `FormulaToOWL.next()` (`alo_translator/serializers/owl.py`) now emits `ObjectSomeValuesFrom(succ, ...)` instead of `ObjectAllValuesFrom(succ, ...)` unconditionally, since the two are logically equivalent for this property everywhere in the codebase. This fixes the OWL serializer's output for every consumer (Konclude realization, HermiT/ROBOT, and the DL-safe-rules post-processor), not just the rules path where the bug was found.

**If revisiting:** if a similar anomaly is found with `box`/`same_moment` in a DL-safe rule body, do NOT apply the same `AllValuesFrom -> SomeValuesFrom` substitution there -- `same_moment` is not functional, so that substitution would silently change the model's semantics rather than being a safe equivalent rewrite.

## HermiT (via ROBOT): a SECOND, separate anomaly -- rules whose body is a
## compound expression referencing another rule-derived class fail to fire,
## even with the ObjectAllValuesFrom(succ,...) fix above applied and even
## with ALL SubClassOf axioms converted to rules (no mixing at all) (2026-08-26)

**This is a distinct bug from the one above, found while checking whether that fix fully resolved the original problem. It does not.**

**Symptom:** after applying the `next()` -> `ObjectSomeValuesFrom` fix (source-level, `FormulaToOWL.next()`), the original 19-query real-file test (3.1.mmd `m/h1/q`) still only derives 4 of 14 expected query classes. The internal helper class `f1` -- whose body is `ObjectIntersectionOf(ObjectIntersectionOf(sd1, f2), ObjectComplementOf(...))` referencing `f2` (itself rule-derived) -- fails to derive, while `f2` and `outcome_m_h1_q` (whose bodies are each a single, non-compound `ClassAtom`) derive correctly.

**Ruled out:**
- Not caused by mixing rules and plain axioms: converted ALL 56 query-related `SubClassOf` axioms to `DLSafeRule`s (only the one non-query totality axiom left untouched) -- same failure, same 4/14 result. Mixing is not the trigger.
- Not a general rule-chaining depth limit: a synthetic 4-hop chain (`sd1 -> hop1 -> hop2 -> hop3 -> hop4`, each rule body a single bare `ClassAtom`) derives correctly end to end.

**Working hypothesis, NOT yet confirmed by a targeted test:** the difference between the working synthetic chain and the failing real case is that the synthetic chain's rule bodies were each a single, non-compound `ClassAtom`, whereas the real failing rules (`f1`, and by the same pattern `f3`, `f6`, `f7`, `f22`, `f26`, `f28`, `f30`, `f31`, `f32`, and the corresponding `pres`/`sres`/`res`/`dxstit`/`ness` query classes that depend on them) have a **compound body** (`ObjectIntersectionOf` of several conjuncts) where one conjunct is a bare reference to a rule-derived class. This has NOT been isolated with a dedicated minimal test yet -- do that before assuming it's the real mechanism.

**Status: UNRESOLVED.** The DL-safe-rules approach does not currently produce correct results for the real query set, only for single-hop-dependency cases. Do not consider `dlsafe_rules.py`/the HermiT rules path production-ready until this is actually fixed and re-verified against the full 14-query known-good baseline.
