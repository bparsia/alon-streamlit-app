# Konclude: known challenges, for whoever is building it for ARM

Short pointer document. Written 2026-08-30 for a parallel effort building
Konclude from source for native ARM (this project currently runs the
prebuilt x86_64 macOS binary via Rosetta 2 — see `bin/README.md`). Each
section below is a one-paragraph summary with a link to the full
investigation; don't re-derive what's already been isolated.

## 1. SPARQL: mostly works, but negation is broken and that's what killed it

Konclude's `sparqlfile` SPARQL execution mode was investigated as an
alternative reasoning backend. This is NOT a story of nothing working —
most of it genuinely worked, confirmed via direct testing:

**What worked:**
- **`SELECT` queries work correctly, including real multi-variable joins
  at scale** — a full `same_moment` closure query returned all 20
  correct pairs for 3.1.mmd's actual structure.
- Every non-negation ALOn primitive (`next`, `diamond`, `conjunction`,
  `do_action`, etc.) had a confirmed-working SPARQL translation.
- A **working decomposition for `box`** was found despite the negation
  bugs below: split into two plain `SELECT` queries (the full
  `same_moment` relation, and the inner formula's satisfying-individual
  set) plus a local Python set-complement check. Confirmed correct at
  real scale — safe specifically because every individual in this
  project's ontologies is named (no anonymous individuals anywhere), so
  there's no risk of SPARQL failing to enumerate something relevant.

**What's actually broken — two independent bugs, both confirmed via
direct testing, not assumed from docs:**
- **`FILTER NOT EXISTS` is rejected as a syntax error** by this build's
  underlying parser (Redland/Rasqal, per its own log output) — tested
  with multiple query shapes, all rejected identically. `FILTER NOT
  EXISTS` is a SPARQL 1.1 addition; this Rasqal version may simply
  predate it.
- **`MINUS` parses and starts real reasoning, but segfaults (exit 139)**
  partway through query answering — confirmed via process logs showing
  it progressed through classification and into "Computed first complex
  query result" before crashing. A real binary crash, not a query-syntax
  problem.
- (A third, separate, smaller bug: **`ASK` gives an incorrect `false`**
  on a joined pattern where the equivalent `SELECT` on the identical
  `WHERE` clause correctly returns results — confirmed with a concrete
  example. Not investigated further since `SELECT` works and is
  preferable anyway; just don't use `ASK` on this build.)

**Why it was still abandoned despite `box` having a workaround**: plain
`negation` itself has no decomposition trick the way `box` does — it's
needed inline, pervasively, throughout the real (fully expanded)
responsibility-operator query set, not confined to one isolated
construct. That's what actually killed the design, not the two bugs in
isolation. **If a from-source ARM build ever gets far enough to test
SPARQL, these are the two specific things to check first** — if the
build fixes/updates the SPARQL layer (e.g. a newer Rasqal), that could
reopen this whole thread, and most of the design work (everything except
negation) would carry over directly.

Full writeup: [`docs/sparql_serializer_ABANDONED.md`](sparql_serializer_ABANDONED.md)
(see "Conclusion: abandon this design" at the bottom for the final state
and what a viable alternative would need).

## 2. DL-safe rules via HermiT — the SPARQL replacement, also closed

After SPARQL, DL-safe rules (via HermiT + ROBOT, a second independent
OWL reasoner) were tried as a rules-based alternative. Real, working
wins came out of it (a correct `HermitAdapter`, a query→DLSafeRule
post-processor with one real correctness bug found and fixed), usable
today for smaller models (3.1/3.6/3.7/isabella-scale) — but a
3.5-scale (16-history) performance wall was never resolved despite
extensive isolation, and the whole thread was closed as dead-for-now.
**Not directly relevant to a Konclude ARM build** (this thread is about
HermiT, a different reasoner) except that it names Konclude's own
SPARQL/nominal-schema support as one of the future directions worth
revisiting once/if Konclude itself is buildable from source.

Full writeup: [`docs/reasoner_oddities.md`](reasoner_oddities.md) (top
section is the closure summary + five future directions, one of which —
"fix Konclude's SPARQL support directly" — is exactly what the ARM-build
effort would unblock). Fixtures/scripts: [`docs/future_work_on_reasoning/`](future_work_on_reasoning/).

## 3. Performance: real anomalies, all resolved as machine-load artifacts, not a bug in Konclude or this project's code

Two Konclude performance regressions were investigated at length — a
3-4x slowdown on the 3.5.mmd model (16 histories), and a ~500x blowup on
one specific isabella.mmd eval point. **Both were eventually ruled out
as content or code bugs**: canonicalized axiom-set comparisons showed
byte-for-byte-equivalent input across old and new code, and both
anomalies stopped reproducing once machine load dropped (repeated
measurements, same code/content each time). Conclusion: this machine's
CPU contention at the time, not Konclude or the serializer, explained
both. **Rosetta translation was explicitly checked and ruled out as an
explanation for the regression** — the historical fast baseline was
*also* recorded under Rosetta (same binary, unchanged), so Rosetta being
present doesn't explain why performance changed on a given day.

Separately, a real, confirmed, unrelated optimization: Konclude defaults
to single-threaded (`-w` flag missing) regardless of core count. Adding
`-w AUTO` gave an **~8-10x measured speedup** on an 11-core machine
(3.5.mmd, 16 histories: 600s+ single-threaded → 71-82s with `-w AUTO`). This is now wired
into `alo_translator/reasoners/konclude.py`. **Relevant to an ARM
build**: whatever the new binary's threading defaults are, explicitly
passing a thread-count flag matched to the target machine's core count
is worth doing regardless — this was leaving real performance on the
table even on the current x86_64/Rosetta binary.

**Found 2026-08-31, status: unresolved, load is the leading suspect but
NOT confirmed.** The real `papers/2026Fear/models/3.5.mmd` file,
generated exactly as `generate_tables.py` does it (its one `res_analyse`
eval point `m/h1, q`, `setup_layered_queries` run first, giving the real
91-query set, `EquivFullCardinalityStrategy`, 805947 bytes — matching
the historical ~805683-byte figure) was tested with `-w AUTO`:
**timed out at 180s and 900s on the new arm64 build, AND timed out at
300s on the existing x86_64 binary** — both architectures show the same
symptom on this exact file, so this is not an ARM-specific regression.

Machine load was checked immediately after (not during) these runs:
`uptime` showed load averages of 32-57 on an 11-core machine — well
above the 10-22 range this project's own prior investigation (see
above) already established as correlating with reproducible Konclude
slowdowns on this same 3.5.mmd model. That prior investigation is the
most likely explanation for these two timeouts too, but **this has NOT
been confirmed** — load wasn't measured *during* either run, and the
test hasn't been repeated under low load yet. Per this project's
standing rule against reasoner-performance speculation: do not treat
this as "explained by load" until it's actually retested under
confirmed-low load and the timeout goes away. The old 71-82s
isolated-eval-point figure is a real prior measurement but is not
directly comparable to this test (different scope — one extracted eval
point's serialization timing, not a full realization run on the
complete 91-query ontology) and should not be read as proof that the
full case is normally fast.

**Next step if picked up again**: rerun this exact file (or regenerate
it fresh from `papers/2026Fear/models/3.5.mmd` — see
`alon_test_suite/fixtures/alon_3.5.owl`) on both binaries under
confirmed-low load (check `uptime` immediately before, not after) with
a generous timeout (900s+), and report the actual result — don't assume
it will be fast or slow.

This is a currently open, unresolved, reproduced-today finding, not
something this document previously captured correctly — an earlier
version of this document (and an earlier version of the fixture in
`alon_test_suite/`) mistakenly used a bare/query-free structural
serialization of 3.5.mmd, which is small and fast and gave a false
impression that this case was fine. **Do not trust a fast 3.5.mmd result
unless you've confirmed it used the real 91-query file, not a bare
structural one** — check the file size (should be ~806KB) or query
count (91) before trusting a timing number for this model.

Full writeup lives in Claude's cross-session memory (not in this repo, so
no link resolves here) — key facts inlined above are the load-bearing
ones. If you have access to an assistant with memory for this project,
the relevant file is `project_konclude_performance`.

## 4. Current binary situation

`bin/Konclude` (gitignored) expects the prebuilt x86_64 macOS binary from
derivo.de (v0.6.2 tested), run via Rosetta 2 on Apple Silicon — see
[`bin/README.md`](../bin/README.md).

**Update 2026-08-31: a genuinely native arm64 build now exists**, built
from source at `/Users/mbassbp2/Development/reasoners/Konclude/release/
Konclude.app/Contents/MacOS/Konclude` (confirmed `Mach-O 64-bit
executable arm64` via `file`, version string `v0.7.0-1138`, newer than
the prebuilt x86_64 binary's `v0.7.0-1135`). Directly verified (not
taken on the builder's word):

- **Realization results are byte-identical** to the x86_64 binary on
  3.1.mmd (small model, `EquivFullCardinalityStrategy`), and meaningfully
  faster (0.13s vs 2.0s with `-w AUTO` on both). The equivalent check on
  the REAL 3.5.mmd (91-query, ~806KB file) has NOT been done yet — see
  the section-3 update above, that file currently times out at 900s on
  this build, so there's no fast arm64 result to compare against x86_64
  for this model yet.
- **A real single-threaded deadlock exists and was reproduced directly**:
  running `realization` on this build with no `-w` flag hangs
  indefinitely (confirmed via a 30s-timeout test, which timed out with
  no output). **Always pass `-w AUTO` (or an explicit thread count) with
  this build** — this is a different, more serious failure mode than the
  x86_64 binary's single-threaded behavior, which was merely slow, not
  hung.
- **`MINUS`'s failure mode changed from segfault to a clean syntax
  error** — still doesn't work, but no longer crashes the process. A
  real (if partial) improvement.
- `FILTER NOT EXISTS` and the `ASK`-vs-`SELECT` bug (see section 1) are
  both still present, unchanged, on this build.

A real, runnable test suite covering all of the above (plus a
`--compare` mode against a second binary) now exists at
`/Users/mbassbp2/Development/reasoners/Konclude/alon_test_suite/` on
this machine — run `./run_tests.sh /path/to/Konclude` before trusting
any new build. Once a build passes it cleanly, the natural next step is
re-running `tests/test_konclude_baselines.py` (this repo's real
regression suite against canonical baselines) against the new binary to
confirm identical results before switching `bin/Konclude` over.

## How to use this document

Each section links to the real investigation — read that before assuming
you already know the shape of the problem. Per this project's standing
rule, do not speculate about reasoner internals/performance; test
directly and compare against what's already documented here.
