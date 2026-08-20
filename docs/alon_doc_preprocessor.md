# ALOn Document Preprocessor — Revised Design

## Authoring philosophy

During development, **shared context is fine** — define aliases and common metadata once
in an `alon-context` block, keep model front matters lean. Self-containedness is a
*derived artifact*, not the primary authoring constraint.

**Extraction** (CLI command or copy button in HTML) resolves context into each model's
front matter on demand, producing a fully self-contained mermaid block you can drop
anywhere. You never have to manually synchronise.

---

## Two modes

### Document mode (authoring)

`alon-context` blocks define shared metadata. Models inherit and can partially override.
Scope: from the block until the next one.

````
```alon-context
aliases:
  1: Alice
  2: Beth
  3: Isabella
  sd: shoots Dan
  ss: stands still
  ha: hits Alice
  masd: manipulates Alice into shooting Dan
  q: Dan dies
opposings:
  sd1: [ha2]
default_backend: datalog
```
````

Model front matters only carry what varies:

````
```mermaid
---
title: Baseline (no manipulation)
type: DBT
res_analyse:
  - [m/h1, q]
---
...
```
````

### Portable mode (extracted)

Extraction merges context into the model's front matter. The output is a fully
self-contained mermaid block. This is what you copy into another document, the
streamlit app, a paper appendix, etc.

---

## Extraction

**CLI:**
```
alo_docs extract input.md --model "Baseline"       # stdout
alo_docs extract input.md --all --output models/   # one .mmd per model
```

**HTML copy button:** each rendered model block has a copy button that puts the
fully-resolved mermaid source on the clipboard. No manual merging.

---

## Shortcodes

Pandoc fenced-div syntax where pandoc is in the pipeline; `{{}}` otherwise.
Both supported — preprocessor detects which form is used.

```
{{alias_table}}                         ← nearest model (resolved with context)
{{alias_table scope="section"}}         ← merged + deduplicated across all models
                                           under the current heading
{{alias_table scope="doc"}}             ← merged across whole document
{{action_table}}
{{model_overview}}
{{results eval="mm1/h1"}}
{{results eval="mm1/h1" backend="konclude"}}
{{results model="Baseline" eval="mm1/h1" backend="datalog"}}
```

`scope="section"` / `scope="doc"` collect aliases from all models in range,
deduplicate, and flag any conflicts.

---

## Output formats

| Format | Mechanism | Notes |
|--------|-----------|-------|
| `markdown` | shortcodes → tables, mermaid untouched | GitHub rendering |
| `html` (self-rendering) | markdeep wrapper | Single `.html`, no server needed; copy buttons per model |
| `html` (full) | pandoc + mermaid-cli → inline SVG | Full pipeline control |
| `pdf` | pandoc + CSS (`break-inside: avoid` on model blocks) | Good pagination |
| `latex` | mermaid-cli → PNG/EPS + `\figure`, tables → LaTeX macros | Generic article |

Self-rendering HTML via markdeep is the primary sharing format for drafts.
Copy buttons in the HTML use the fully-resolved (portable) model source.

---

## Results caching

Sidecar `.alon-cache.json`, keyed by `(model_title, eval_point, backend, source_hash)`.
Cache invalidated when the mermaid block or inherited context changes.

Backend pluggable from the start: `datalog`, `konclude`, future TBox-constrained
reasoners all go through the same interface.

---

## Where it lives

- **CLI**: `python -m alo_docs [build|extract] ...`
- **Streamlit**: "Document" page — upload `.md`, pick formats, download or preview
- Both share the same preprocessor/resolver core

---

## Summary of operations

| Operation | Input | Output |
|-----------|-------|--------|
| `build` | `.md` with context + shortcodes | rendered formats |
| `extract` | `.md` + model name/`--all` | self-contained `.mmd` block(s) |
| `generate` *(later)* | template spec in `.md` | expanded mermaid blocks |

---

## Open items

- Conflict resolution for `scope="section"` alias merging (same key, different value).
- Markdeep copy-button implementation (custom JS in the markdeep template).
- Generator feature scope and priority.
