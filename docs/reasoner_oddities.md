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

**Change applied, scope NOT established -- do not call this "a confirmed fix" without further work:** `FormulaToOWL.next()` (`alo_translator/serializers/owl.py`) now emits `ObjectSomeValuesFrom(succ, ...)` instead of `ObjectAllValuesFrom(succ, ...)`, since the two are logically equivalent for this (functional) property. This substitution changed the result on ONE isolated test (a 2-rule file: `outcome_m_h1_q` alone converted to a `DLSafeRule`, `pres_1_q` failing before the swap, succeeding after). **But applying the identical substitution inside the real 19-query file produced a byte-for-byte IDENTICAL result before and after** -- confirmed via direct diff, not assumed. This is a real contradiction: if `AllValuesFrom` vs `SomeValuesFrom` in a rule body were a general, reusable fix, it should have changed *something* in the 19-query case too, even if not fully resolving it. It didn't. So the honest state is: an unexplained result on one small isolated test, whose generalization to the real case is directly contradicted by evidence, not confirmed by it. Do not describe this as "fixing a bug" in the DL-safe-rules approach -- it's an observation with unknown scope, on par with the other findings in this file, not a resolved fix. It remains logically neutral (verified harmless, not necessarily "correct" in any deeper sense) for the existing Konclude/plain-axiom pipeline.

**If revisiting:** if a similar anomaly is found with `box`/`same_moment` in a DL-safe rule body, do NOT apply the same `AllValuesFrom -> SomeValuesFrom` substitution there -- `same_moment` is not functional, so that substitution would silently change the model's semantics rather than being a safe equivalent rewrite.

## HermiT (via ROBOT): converting `outcome_m_h1_q`'s query specifically to a
## rule breaks OTHER, unrelated rules elsewhere in the ontology -- confirmed
## via clean bisection, independent of the AllValuesFrom/SomeValuesFrom choice
## above (2026-08-26)

**This supersedes the "compound body" working-hypothesis originally written in this section, which was based on a methodological error (stale test data) -- see below.**

**Clean bisection, on fresh post-`next()`-fix data (all `f`-class indirection removed via full inlining first, so there is no rule-to-rule dependency chain of any kind -- every one of the 19 query rules is a fully self-contained, primitive-only expression referencing no other class):**

Started with just `pres_1_q_m_h1_q` as a lone `DLSafeRule` (real ABox, no other rules) -- derives correctly. Added the other 17 non-`outcome` query rules **one at a time**, re-testing after each addition -- `pres_1_q` continued to derive correctly through all 18 additions. Added `outcome_m_h1_q`'s rule as the 19th and final addition -- `pres_1_q` immediately stopped deriving. This is a clean, ordered, one-variable-at-a-time bisection, not a guess: `outcome_m_h1_q`'s rule, specifically, is what breaks `pres_1_q`'s otherwise-correct rule, and no other one of the 18 rules does.

**The `ObjectAllValuesFrom` vs `ObjectSomeValuesFrom` question is now closed and was a dead end:** re-ran this exact bisection with `outcome_m_h1_q`'s rule body in its current, post-fix `ObjectSomeValuesFrom(succ, q)` form (not the original `ObjectAllValuesFrom` form) -- **still breaks `pres_1_q` identically.** The earlier claim that this substitution "fixed" anything was based on a methodological error: the isolated 2-rule test that appeared to show a fix was accidentally run against a stale pre-fix copy of the serialized ontology (`sparql_test.owl`, generated before the `next()` source change), while the "no difference" 19-rule re-test used a freshly-generated (post-fix) file -- an apples-to-oranges comparison, not a real contradiction in reasoner behavior. Once both sides of the comparison were regenerated fresh and consistently, the substitution makes **no difference at all** to this bug. It remains logically neutral for the existing Konclude/plain-axiom pipeline (verified separately, still true) but does not touch this rule-interaction issue.

**Ruled out along the way (still valid, not affected by the above correction):**
- Not caused by mixing rules and plain axioms: converting ALL 56 query-related `SubClassOf` axioms to `DLSafeRule`s (pure-rules ontology, zero plain query-definition axioms) gives the identical 4/14 failure.
- Not a general rule-chaining depth limit: a synthetic 4-hop chain (`sd1 -> hop1 -> hop2 -> hop3 -> hop4`, each rule body a single bare `ClassAtom`) derives correctly end to end.
- Not about compound-vs-simple rule bodies in general: the bisection above used fully-inlined (compound, often 4000+ character) bodies for all 19 rules, and 18 of them coexisted with each other and with `pres_1_q` without issue. Only `outcome_m_h1_q`'s presence specifically breaks things.
- Not about `outcome_m_h1_q`'s formula shape being `ObjectAllValuesFrom`/`ObjectSomeValuesFrom` over `succ`: a standalone rule with exactly that shape (`ObjectComplementOf(ObjectAllValuesFrom(same_moment, ObjectSomeValuesFrom(succ, q)))`, i.e. `~[]Xq`) alone, with no other rules present, correctly derives on all four moment/history individuals tested.

**What's actually different about `outcome_m_h1_q` specifically, not yet identified:** it's the only one of the 19 real queries whose body, even before inlining, was already a single, non-compound `ObjectSomeValuesFrom(succ, q)` -- every other query's body has at least the `do(...)` conjunct making it a compound `ObjectIntersectionOf`. Whether that "simplicity" (rather than anything about the modal operator, negation, or `succ`/`same_moment` specifically) is the actual trigger has NOT been tested -- e.g. has not yet been checked whether an artificially simple standalone rule for a DIFFERENT, non-`outcome` formula shape would have the same disruptive effect when added alongside others.

**Status: UNRESOLVED.** The DL-safe-rules approach does not currently produce correct results for the real query set. Do not consider `dlsafe_rules.py`/the HermiT rules path production-ready until this is actually understood or worked around, and re-verified against the full 14-query known-good baseline.

**Process lesson, worth remembering for future investigations:** re-verify that comparison inputs are actually generated from the same code state before drawing conclusions from a diff -- a stale scratch file (`sparql_test.owl`, generated before a source-level fix, reused across many later tests without regeneration) produced a real, reproducible, but ultimately spurious "the fix works on this test" result that took a full re-run of the bisection with freshly-generated data to catch and correct.
