# Modal Context Translation Design

>>> BJP I think there are a number of subtle issues and confusions.
>>> One key aspect is that our encoding of models is slightly odd in that we use "successor moments" *both* to represent successor moments (where e.g., if Xq is  true at m, then q is true at a succ(m) (say m1)) and as a place to "hang" information (e.g., what actions led to that moment.)
>>> This is different than either hanging the "transition info" on the connecting property or using indexes (e.g., one individual per moment/history pair) or having some extra individual (e.g., in between a moment and it's success or hanging off either e.g., -actionleadingtome-> individual).
>>> We overload moments both with their current state and aspects of their history to reduce the number of individuals in total and which we'd need to "grab onto" in our queries.
>>> Thus if we look in our `sources/whatrespchapter3.pdf`, particularly the semantics in Definition 3.6, it's important to note the semantics of do(), X, and []. Only X involves the succ function thus only Xq requires q to be true at a successor
>>> However, because we're overloading successor moments to capture indexes based on the prior moment, things get tricky. So M, m/ h |= do(ai ) iff act(m/ h)(i )= ai...how do we check if ai is in the actions at m/h1? If we had an individual in our abox named m/h1, we'd look to see if it were a member of ai. As it stands, we check the "next" moment which is related to m by the h1 property for membership in that act. We have to *remember* that we have this indirect representation.
>>> It's related to this approach in the text: " But in order to avoid the introduction of further notation, here
we will label indices instead: every index m/ h will be labeled with the complete
group action that, intuitively, brings about the transition from m to its successor on
h (i.e., the moment succh (m)).18 If index m/ h is labeled with α ∈ Ag- Acts, then
α(i ) represents the action type that agent i instantiates at m/ h and, similarly, αI the
action type that group I instantiates at m/ h. Hence, every agent i instantiates one,
and only one, type of action at every index m/ h. " Except we put the group action on the second half of the succession pair.
>>> Similarly, M, m/ h |= ϕ iff for all h′ ∈ Hm , M, m/ h′ |= ϕ...we have the text "; ϕ means “ϕ is settled true” or “ϕ is historically necessary” and is true at an index m/ h whenever ϕ is true at m on all histories passing through it." Thus I think for things like propositions (e.g., `[]p`) that means m is a member of p. In our current restricted model any proposition true for individual m will be true for m on all histories. The *only* things we (currently) allow to vary between m/h1 and m/h2 are 1) actions (it's *common* that m/h1 |= do(a1) while m/h2 |\= do(a1), indeed, if there's more than one action availalbe at m to an agent we will need such divergent histories) and successors (thus it might be the case  that m/h1 |= Xq while m/h2 |/= Xq because at m1/h1 is an instance of q while m2/h2 is an instance of ~q).
>>> Thus when nesting boxes e.g., [][]q, I don't think for plain propositions that this pushes things to the next moment. I.e., []X[]q gives us different results than [][]q. Similarly []do(ai) will be false at m/anyhistory if i has more than one action available. [][]do(ai) will similarly be false. Contrariwise, in our current models []q will be true for *any* propsotion true at m/anyhistory since we don't allow propostions at m to vary by history. (We might want to in the future but we're dealing with very restricted models at the moment.) I do think it's probably the case that if m/h1 |= []\phi that  m/h2 |= []\phi and (consequentially) m/h1 |= [][]\phi. I think [] is an S5 operator where all indicies with a common moment are accessble to each other.
>>> I guess the open question is whether to kill this overloading of successor individuals and move to an index based scheme with an equivalence relation over the shared moment indicies.

## Problem

The serializer must correctly translate nested modal operators (Box, Diamond, Next) to OWL. The key challenge is understanding what `X` (Next) means in different contexts.

## Model Structure

Our model has:
- **Moments**: m, m1, m2, m3, m4, ...
- **succ**: General successor relation (union of all histories)
- **h1, h2, h3, h4**: Specific history properties (functional subproperties of succ)
- **Evaluation point**: m/h1 (moment m on actual history h1)

```
m --h1--> m1
  --h2--> m2
  --h3--> m3
  --h4--> m4

succ = h1 ∪ h2 ∪ h3 ∪ h4
```

## Modal Operators

- `[]φ` (Box): "For all successor moments, φ holds" → `∀succ.φ`
- `<>φ` (Diamond): "For some successor moment, φ holds" → `∃succ.φ`
>>> BJP thus these confuses successor *individuals* with successor *moments*. We need to know what sort of φ we're looking at to determine where the relevant information is held.
- `Xφ` (Next): "At the next moment on the actual history, φ holds" → ???
>>> BJP I don't know why you are confused about this...this is the easy one :)

## The Question: What does `X` mean in different contexts?

### Case 1: Top Level `Xφ`
**Context**: Evaluating at m/h1, not inside any modal operator

**Semantics**: Follow h1 to the next moment (m1) and check φ there

**Translation**: `∀h1.φ`

**Example**: `Xq` at m/h1 → `∀h1.q` → "Follow h1 to m1, check if m1 is of type q"

---

### Case 2: `[]Xφ`
**Context**: X inside Box

**Semantics**:
- Outer `[]` quantifies over ALL successors (m1, m2, m3, m4)
- For each successor mi, what does `Xφ` mean?

**Option A (WRONG)**: "Follow h1 from mi"
- Translation: `∀succ.(∀h1.φ)`
- Problem: h1 is only defined from m, not from mi
- In depth-1 models, mi has no h1 edge
- Semantically wrong: we're not trying to follow h1 from arbitrary successors

**Option B (CORRECT)**: "We're already at the next moment"
- Translation: `∀succ.φ`
- The `[]` already brought us to successor moments
- `X` inside `[]` is identity (no additional quantification needed)
- This matches the OLD serializer's output!

**Example**: `[]Xq` at m/h1
- Semantics: "For all immediate successors, q holds there"
- Translation: `∀succ.q`
- NOT: `∀succ.(∀h1.q)`

---

### Case 3: `~[]Xφ`
**Context**: Negation of Box-Next

**Semantics**: "There exists a successor where φ doesn't hold"

**Translation**: `∃succ.¬φ` (equivalently: `¬∀succ.φ`)

**NOT**: `¬∀succ.(∀h1.φ)`

**Example**: `~[]Xq` at m/h1
- Translation: `∃succ.¬q`
- Means: "Some successor is not of type q"

---

### Case 4: Nested Boxes `[][]XXp`
**Context**: Deep nesting with multiple Next operators

**Step-by-step**:
1. Outer `[]`: quantify over immediate successors → we're now at depth 1
2. Inner `[]`: quantify over successors of successors → we're now at depth 2
3. First `X`: we're already at depth 2, so this is identity
4. Second `X`: still at depth 2, identity again
5. Result: `∀succ.∀succ.p`

**Rule**: Inside any modal context, `X` is identity

---

### Case 5: `X[]φ`
**Context**: Next then Box

**Step-by-step**:
1. Top-level `X`: Follow h1 to next moment → `∀h1.(...)`
2. Now at m1, inside modal context (created by X)
3. Inner `[]`: Quantify over all successors of m1 → `∀h1.∀succ.φ`

**Translation**: `∀h1.∀succ.φ`

**Semantics**: "Follow h1 to m1, then check φ holds in all successors of m1"

---

### Case 6: Expected Result `[]( free_do(a) → Xφ )`
**Context**: The actual pattern we need to translate correctly

**Step-by-step**:
1. Outer `[]`: `∀succ.(...)`
2. Implication: `¬A ∨ B`
3. Left side: `free_do(a)` inside modal context → just the class (no h1 wrapping)
4. Right side: `Xφ` inside modal context → identity, just φ
5. Result: `∀succ.(¬(a ∧ ¬Opp2a) ∨ φ)`

**NOT**: `∀succ.(¬(a ∧ ¬Opp2a) ∨ ∀h1.φ)` ← WRONG!

---

## The General Rule

**Modal Context Flag**: Track whether we're inside a Box/Diamond/Next operator

- **in_modal_context = False** (top level):
  - `Xφ` → `∀actual_history.φ`
  - `do(a)` → `∃actual_history.a`
  - `free_do(a)` → `∃actual_history.(a ∧ ¬Opp2a)`
  - `φ` (proposition) → `Class(φ)` ← already plain!

- **in_modal_context = True** (inside modal operators):
  - `Xφ` → `φ` (identity - we're already at the next moment)
  - `do(a)` → `Class(a)` (plain class, no history wrapping)
  - `free_do(a)` → `a ∧ ¬Opp2a` (plain classes)
  - `φ` (proposition) → `Class(φ)` (same as top level)

---

## Implementation Strategy

1. **Track modal context**: `self.in_modal_context` flag in visitor

2. **Set context when entering modals**: Box, Diamond, Next set `in_modal_context = True` for their children

3. **Check context in translators**:
   - `_visit_next`: If `in_modal_context`, return inner formula without wrapping
   - `_visit_do_action`: If `in_modal_context`, return plain class
   - `_visit_free_do_action`: If `in_modal_context`, return plain intersection
   - `_visit_prop`: Always returns plain class (propositions are never wrapped!)

4. **Restore context**: Save and restore `in_modal_context` when visiting children

---

## Test Cases

### Simple Next
- Input: `Xq`
- Context: top level
- Expected: `∀h1.q`

### Box-Next
- Input: `[]Xq`
- Context: X inside Box
- Expected: `∀succ.q`
- NOT: `∀succ.(∀h1.q)`

### Negated Box-Next
- Input: `~[]Xq`
- Context: X inside negated Box
- Expected: `∃succ.¬q`
- NOT: `¬∀succ.(∀h1.q)`

### Nested Boxes
- Input: `[][]XXp`
- Context: Multiple nesting levels
- Expected: `∀succ.∀succ.p`

### Next-then-Box
- Input: `X[]p`
- Context: Box inside Next
- Expected: `∀h1.∀succ.p`

### Expected Result (real-world)
- Input: `[](free_do(sd1) → Xq)`
- Context: Implication inside Box
- Expected: `∀succ.(¬(sd1 ∧ ¬Opp2sd1) ∨ q)`
- NOT: `∀succ.(¬(sd1 ∧ ¬Opp2sd1) ∨ ∀h1.q)`

---

## Why This Matters

The difference between `∀succ.(∀h1.q)` and `∀succ.q` is critical:

- `∀succ.(∀h1.q)`: "For all successors mi, if you follow h1 from mi, you get q"
  - But h1 doesn't exist from mi (only from root m)
  - Wrong modal depth
  - Semantically nonsensical

- `∀succ.q`: "For all successors mi, q holds at mi"
  - Correct
  - Matches OLD serializer
  - Konclude can reason about it properly

---

## Current Bug

In `formula_to_owl.py`, `_visit_next()` always wraps with actual_history, even when `in_modal_context = True`.

The fix: Check `in_modal_context` and return inner formula directly if True.

```python
def _visit_next(self, node: Next) -> Element:
    # Inside modal operators, X is identity
    if self.in_modal_context:
        return self.visit(node.formula)

    # At top level, wrap with actual_history
    restriction = Element("ObjectAllValuesFrom")
    SubElement(restriction, "ObjectProperty", {"IRI": self._iri(self.actual_history)})
    # ... set context and visit inner formula
```
