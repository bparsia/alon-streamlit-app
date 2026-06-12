# ALOn Model Library — Feature Matrix

Last updated: 2026-06-12

This document catalogues which structural and semantic features are exercised by each
existing model, identifies gaps, and maps the gaps to the legal causation cases from
`sep_data.md` that motivate filling them.

---

## Existing Models

### `streamlit_app/models/`

| Model | Title | TD | Agents | Histories |
|---|---|---|---|---|
| `3.1.mmd` | Example 3.1 — Alice shoots Dan | 1 | 2 (consec.) | 4 |
| `3.5.mmd` | Example 3.5 — 4-agent shooting | 1 | 4 (consec.) | 16 |
| `3.6.mmd` | Example 3.6 — overdetermination | 1 | 2 (non-consec: 1,3) | 4 |
| `3.7.mmd` | Example 3.7 — joint push | 1 | 2 (non-consec: 1,3) | 4 |
| `depth2_example.mmd` | Isabella manipulation (TD=2) | 2 | 3 | 6 |
| `depth2_example2.mmd` | Isabella manip. — Alice only shoots if manipulated | 2 | 3 | 4 |
| `depth2_example3.mmd` | Isabella manip. — rescindable (TD=3) | 3 | 3 | 4 |

### `docs/` (inline models, not in streamlit library)

| Location | Title | TD | Agents | Notes |
|---|---|---|---|---|
| `cornercases.md` | 1 agent, 1 action — degenerate | 1 | 1 | single CGA, q settled true |
| `cornercases.md` | 1 agent, 2 actions — settled true | 1 | 1 | both outcomes q |
| `cornercases.md` | 1 agent, 2 actions — standard | 1 | 1 | h1=q, h2=~q |
| `cornercases.md` | 2 agents, 1 action each — degenerate | 1 | 2 | both actions sufficient, overdetermination |
| `multistep.md` | 3.1 (complete) | 1 | 2 | same as 3.1.mmd |
| `multistep.md` | Single-moment opposing-based manipulation | 1 | 2 | ss1 opp masd3; classic overdetermination at m/h2 |
| `multistep.md` | Minimal TD=2 | 2 | 2 | (see file for details) |
| `estellec1.md` | Kenneka Jenkins case | 1 | 3 | real-world legal case; 8 histories; two opposing pairs |

---

## Feature Coverage Matrix

### Structural Features

| Feature | 3.1 | 3.5 | 3.6 | 3.7 | d2 | d2_2 | d2_3 | cc (various) | estellec1 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| TD=1 | ✓ | ✓ | ✓ | ✓ | | | | ✓ | ✓ |
| TD=2 | | | | | ✓ | ✓ | | | |
| TD=3 | | | | | | | ✓ | | |
| 1 agent | | | | | | | | ✓ | |
| 2 agents | ✓ | | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| 3 agents | | | | | ✓ | ✓ | ✓ | | ✓ |
| 4 agents | | ✓ | | | | | | | |
| Non-consecutive agent IDs | | | ✓ | ✓ | | | | | ✓ |
| Intermediate moment propositions | | | | | ✓ | ✓ | ✓ | | |

### Opposing Relations

| Feature | 3.1 | 3.5 | 3.6 | 3.7 | d2 | d2_2 | d2_3 | cc | estellec1 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| No opposings | | | ✓ | ✓ | | | | ✓ | |
| Single opposing pair | ✓ | | | | ✓ | ✓ | ✓ | | |
| Multiple opposing pairs | | ✓ | | | | | | | ✓ |
| Opposing used for manipulation (ss opp masd) | | | | | | | | ✓ (multistep) | |

### Outcome Structure

| Feature | 3.1 | 3.5 | 3.6 | 3.7 | d2 | d2_2 | d2_3 | cc | estellec1 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Single q history | ✓ | | | ✓ | | | | | |
| Multiple q histories | | ✓ | ✓ | | ✓ | ✓ | ✓ | | ✓ |
| q settled true (all histories → q) | | | | | | | | ✓ | |
| Individual sufficiency (each agent alone → q) | | | ✓ | | | | | ✓ (cc degenerate) | |
| Joint necessity (both required for q) | | | | ✓ | | | | | |
| k-of-n threshold | | | | | | | | | |

### Causal Structure

| Feature | 3.1 | 3.5 | 3.6 | 3.7 | d2 | d2_2 | d2_3 | cc | estellec1 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Single sufficient cause | ✓ | | | | | | | ✓ | |
| Symmetric overdetermination | | | ✓ | | | | | ✓ (cc degenerate) | |
| Asymmetric overdetermination | | ✓ | | | | | | | |
| Pre-emption | | | | | | | | | |
| Omission causation | | | | | | | | | |
| Double prevention | | | | | | | | | |
| Manipulation (temporal, masd) | | | | | ✓ | ✓ | ✓ | | |
| Manipulation (same-moment, via opposing) | | | | | | | | ✓ (multistep) | |
| Rescindable manipulation | | | | | | | ✓ | | |
| Thin skull / victim's prior condition | | | | | | | | | |
| Freakish route / coincidence | | | | | | | | | |

### NESS / Empty-Set Semantics

| Feature | Models exercising it |
|---|---|
| `ness_empty_sufficient=true` (default) | all |
| `ness_empty_sufficient=false` variant | `cornercases.md` (explicit comparison) |
| Empty-set makes ness vacuously false | `cornercases.md` — 1-agent, 1-action |
| Empty-set makes ness non-vacuously correct | `cornercases.md` — 1-agent, 2-actions, settled true |

---

## Gaps and Priorities

### High priority — classically important causal cases

These are well-documented in legal philosophy (see `sep_data.md`, Moore 2024) and
currently have no ALOn model:

1. **Pre-emption** — Agent A fires first and kills Dan; Agent B also fires but the
   bullet arrives after Dan is dead. B is not a cause. Structurally: A's action
   makes B's action counterfactually irrelevant. Requires at least TD=2 (or careful
   TD=1 encoding with asymmetric outcomes).

2. **Pure omission causation** — No agent takes a killing action; Dan dies because
   nobody prevented it. Currently no model where `q` requires an agent *not* to act.

3. **Double prevention** — A prevents B from preventing Dan's death. A is liable even
   though A committed no positive harmful act. Structurally novel: requires a
   "prevention of prevention" outcome pattern.

4. **Thin skull** — Dan has a pre-existing condition that makes him especially
   vulnerable. A minor action (that would not normally cause death) does. The question
   is whether A is a cause of q. Structurally: q at an index where the action is
   "minor" but condition obtains.

5. **Freakish route** — A's action causes q but only via a highly abnormal causal
   chain. No liability even though counterfactual dependence holds. Requires a
   proposition representing the route, plus a model where the route proposition is
   true only in strange histories.

### Medium priority — refine existing coverage

6. **k-of-n threshold coalition** — q requires exactly k of n agents to act (k > 1,
   k < n). Currently we have k=1 (3.6, individual sufficiency) and k=n (3.7, joint
   necessity). k=2-of-3 is unexplored.

7. **Concurrent cause (garden variety)** — Two agents each necessary, only jointly
   sufficient. Covered by 3.7 for k=2-of-2 but not more generally.

8. **Mixed overdetermination** — Three or more factors, any two sufficient. Generalises
   3.5 but focuses on the causal structure rather than the scale.

9. **Acceleration** — A accelerates a harm that was going to happen anyway (e.g., Dan
   was terminally ill). Is A a cause? Structurally: q in all histories regardless of
   A's action, but A's action makes q occur sooner (multi-proposition or TD>1).

### Lower priority — edge cases and expressivity tests

10. **Multiple propositions** — All current models use only `q`. A model with at least
    two propositions (e.g., `q` and `r`) is needed to test conjunction/disjunction in
    results and queries.

11. **Voluntary intervening agent** — A sets events in motion; B independently and
    culpably intervenes to cause q. A is not liable. Structurally: TD=2 where B's
    action at the second stage determines q.

12. **Action unavailability at successor moment** — An action available at `m` is not
    available at a successor moment (e.g., once Dan is dead Alice cannot shoot him).
    Tests per-moment action availability (planned feature).

---

## Mapping to `sep_data.md` (Moore 2024 — 16 Legal Facts)

| Legal fact | ALOn case | Models covering it | Gap |
|---|---|---|---|
| 1. Causative verbs imply causation | Single cause | 3.1 | — |
| 2. No counterfactual dep. → no liability | But-for failure | 3.6 (ss1 not but-for) | — |
| 3. Probability-raising | (partially covered by NESS) | 3.6 | thin skull, freakish route |
| 4. Omission liability | Omission causation | — | **gap** |
| 5. Double prevention | Double prevention | — | **gap** |
| 6. Culpability-aspect dependence | (out of scope for ALOn) | — | — |
| 7. Multiple cause / actions | Overdet., pre-emption, mixed | 3.6 (overdet.) | pre-emption, mixed |
| 8. Multiple cause / omissions | Concurrent omissions | — | **gap** |
| 9. Multiple cause / double prevention | — | — | **gap** |
| 10. Thin skull | Thin skull | — | **gap** |
| 11. Vis major (intervening natural event) | (out of scope) | — | — |
| 12. Coincidence / freakish route | Freakish route | — | **gap** |
| 13. Intention extends causal reach | (out of scope / normative) | — | — |
| 14. Intervening human actor | Voluntary intervening agent | depth2 (partial) | clean model needed |
| 15. Scalar causation | Degree of contribution | 3.5 (partial) | no explicit scalar test |
| 16. Freakish route cases | Freakish route | — | **gap** |
