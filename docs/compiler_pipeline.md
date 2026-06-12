# ALOn Compiler Pipeline Design

## Overview

The translation pipeline is a compiler with three phases:

```
mermaid/query text
    → parse()           → RawModel (AST, unchecked)
    → analyse()         → SemanticModel (typed, annotated, issues[])
    → generate(target)  → OWL / Datalog / ...
```

The "linter" IS semantic analysis, exposed as a standalone entry point.
Errors block generation. Warnings surface in UI alongside results.

---

## Phase 1: Parse (already implemented)

- Input: mermaid diagram text (with YAML front matter) + query strings
- Output: `RawModel` — AST with moments, transitions, proposition strings,
  action declarations, opposing relations, named histories, query formulas
- Parser is **liberal**: accepts anything syntactically valid
- No semantic validation here

---

## Phase 2: Semantic Analysis

### `analyse(raw_model, queries, eval_points) -> SemanticModel`

Computes model properties and validates everything. Returns a `SemanticModel`
with all derived facts attached plus an `issues` list.

### SemanticModel fields

```python
@dataclass
class SemanticModel:
    raw: RawModel                          # original parsed model
    td: int                                # temporal depth (max path length from root)
    signature: Set[str]                    # all propositional atoms in model + queries
    moment_roles: Dict[str, MomentRole]    # role of each moment
    cga_coverage: Dict[str, CGACoverage]   # per non-leaf moment
    issues: List[Issue]                    # errors + warnings
```

### MomentRole

```python
@dataclass
class MomentRole:
    name: str
    is_root: bool
    is_leaf: bool                          # no outgoing transitions
    is_intermediate: bool                  # both incoming and outgoing
    depth: int                             # steps from root
    max_depth_above: int                   # longest path from any root to here
    max_depth_below: int                   # longest path from here to any leaf
    histories_through: List[str]           # history names passing through
    same_moment_cardinality: int           # number of indices at this moment
```

### CGACoverage (non-leaf moments only)

```python
@dataclass
class CGACoverage:
    moment: str
    cgas: List[Dict[str, str]]             # list of {agent: action_type} dicts
    is_complete: bool                      # all agent×action combos covered
    missing_cgas: List[Dict[str, str]]     # CGAs implied by available_actions but absent
```

### Issue

```python
@dataclass
class Issue:
    severity: Literal['error', 'warning', 'info']
    code: str                              # e.g. 'E001', 'W003'
    message: str
    location: Optional[str]               # moment name, query id, or index
```

---

## Foundational principle: moment labels are sets of literals

A well-formed model's moment labels are **sets of literals** — each element is
either a bare atom `p` or its negation `~p`. Written in mermaid as comma-separated:

    m1: q, ~p, r

Grammar for a well-formed moment label:
```
label   ::= literal ("," literal)*
literal ::= "~"? atom
atom    ::= IDENTIFIER
```

Everything else — `do`, `X`, `[]`, `<>`, responsibility operators, disjunctions,
conjunctions — is *derived* from the model structure by the semantics, not directly
asserted. Derived facts belong in queries, not model labels.

The mermaid parser already splits on commas, so `m1: q, ~p` produces `{'q', '~p'}`
as the proposition set. The semantic analyser validates this; the parser stays liberal.

---

## Analysis checks

### Moment label checks
- **E001**: moment label element is not a literal (`~`? IDENTIFIER) — complex formula
- **E002**: action-modal formula (`do`, `[]do`, `Xdo`) at a leaf moment
- **W001**: leaf moment missing literal for a signature atom (underspecified valuation)
- **W002**: `[]do(a)` at non-leaf where some CGA lacks `a` — will cause OWL inconsistency

### Temporal depth checks
- **E003**: formula in moment label has modal depth > `max_depth_below` at that moment
  (e.g., `XXq` at a node with only 1 step below it — inconsistent in OWL)

### Signature checks
- **W003**: query atom not in model signature — result will always be structurally false
- **I001**: model signature atom never appears in any query — unused, informational

### Query × evaluation index compatibility
- **E004**: `Xφ` evaluated at a leaf index — no successors, structurally false
- **W004**: `[]φ` or `<>φ` at isolated index (same_moment cardinality=1) — vacuously true/false
- **W005**: responsibility operator (`but`, `ness`, `pres`, `sres`, `res`, `DXSTIT`,
  `XSTIT`) evaluated at a leaf index — meaningless (leaf has no CGA structure)
- **W006**: modal depth of query formula exceeds TD of model from eval index
- **W007**: `do(a)` evaluated at index where action `a` is not asserted

---

## Phase 3: Generate

### Target compatibility check

Each generation target declares what it requires from the `SemanticModel`.
Before generating, the target checks compatibility and may add further issues.

```python
class GenerationTarget(Protocol):
    def check_compatibility(self, sem: SemanticModel) -> List[Issue]: ...
    def generate(self, sem: SemanticModel) -> str: ...
```

**OWLTarget**
- Requires: no E-level issues
- Additional check: warns if any leaf lacks `¬∃succ.⊤` assertion (open-world
  successor problem — reasoner may invent successors making `Xφ` satisfiable)
- Additional check: warns if complex (non-literal) proposition labels present
  (will be serialized but may cause inconsistency)

**DatalogTarget**
- Requires: no E-level issues
- Additional check: errors if any moment label is not a literal — Datalog cannot
  express arbitrary propositional formulas as ground facts
- Additional check: errors if modal depth of any query > TD of model

---

## Two kinds of false (result metadata)

Query results carry provenance:

```python
@dataclass
class QueryResult:
    query_id: str
    result: bool
    structural: bool      # True = false due to model inadequacy, not semantics
    reason: Optional[str] # e.g. "evaluation index is a leaf; no successors"
```

The UI distinguishes:
- `true` — holds in the model
- `false` (semantic) — does not hold; model is adequate for this query
- `false` (structural) — model lacks required structure; result is an artifact

---

## Entry points

### As compiler (in pipeline)
```python
raw = parse(mermaid_text)
sem = analyse(raw, queries, eval_points)
if any(i.severity == 'error' for i in sem.issues):
    raise CompilationError(sem.issues)
owl = OWLTarget().generate(sem)
```

### As linter (standalone / UI widget)
```python
raw = parse(mermaid_text)
sem = analyse(raw, queries=[], eval_points=[])
# Returns SemanticModel with issues[] but no query-specific checks
# UI shows: TD, signature, moment roles, CGA coverage, issues
```

### As query advisor (UI "is this query valid here?")
```python
sem = analyse(raw, queries=[q], eval_points=[(moment, history, target)])
# Returns compatibility issues for that specific query×index pair
```

---

## Implementation order (suggested)

1. `MomentRole` computation — TD, leaf/root/intermediate, depth, cardinality
2. `signature()` — atom extraction from labels + queries
3. Moment label validation — E001, E002, W001
4. Query × index compatibility — E004, W004, W005, W006
5. `CGACoverage` — completeness check, W002
6. Target compatibility checks — OWLTarget, DatalogTarget
7. `QueryResult` provenance — structural vs semantic false
8. UI integration — surface issues, annotate results table
