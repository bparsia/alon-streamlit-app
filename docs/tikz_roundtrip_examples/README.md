# TikZ round-trip examples

Hand-authored TikZ figures paired with their corresponding ALOn `.mmd` models,
for future round-trip work on thread 6b (TikZ as an *alternate* rendering of
ALOn models alongside Mermaid — not a fallback for anything Mermaid can't
express, and not gated on Mermaid's limitations).

## brainwashing_manipulation.tex — verified correspondence

TikZ source: `brainwashing_manipulation.tex` ("Brainwashing case", fig:2).
Model: `papers/2026Fear/models/complete_manipulation.mmd` (already existed,
already committed — not new).

Correspondence checked directly, not assumed:

| TikZ element | `.mmd` element |
|---|---|
| "Neil implants the chip" (solid box) | `ic2` |
| "Neil leaves Beth alone" (solid box) | `lb2` |
| "Beth sleeps" | `ss1` |
| "Beth watches TV" | `a1` |
| "Beth drinks tea" | `b1` |
| $h_1, h_2, h_3 \to v$ | `m1, m2, m3` → `v` |
| $h_4, h_5, h_6 \to \neg v$ | `m4, m5, m6` → `~v` |

6 histories, one 2-way choice (Neil) crossed with one 3-way choice (Beth) —
matches exactly. The model's `aliases` block only labels `a`/`b` generically
("a", "b") rather than "watches TV"/"drinks tea" as the figure names them;
worth tightening if this pair is used for anything paper-facing.

## poison_tea.tex — NOT yet matched to a model

TikZ source: `poison_tea.tex` (John/Alice/Matt/Sam poisoning scenario, fig:1).
Kept per the user's instruction ("worth extracting that for roundtrip
testing") but **no corresponding `.mmd` model has been found or built yet** —
searches across all three known prior session logs and the current `.mmd`
files in both `alon-streamlit-app` and `deontickit` came up empty. This is a
genuinely open task, not a done-and-verified pair like the one above:
3 agents (John/Alice/Matt), 2 actions each → 8 histories, with a
CGA-grid-plus-arc layout (John/Alice on the two rectangle axes, Matt's choice
as a circular arc dividing each quadrant) that's a materially different, more
complex shape than `complete_manipulation.mmd`'s simple 2×3 grid. Building
the model from the figure (or vice versa) is future work, not yet started.

## How to apply

When starting thread 6b (TikZ rendering) for real: `brainwashing_manipulation`
is the one ready-made verified pair to build/test a generator against first.
`poison_tea` is a second, harder test case (3-way branching, non-rectangular
layout) worth targeting once the simple case works, but its `.mmd` side needs
building from scratch.
