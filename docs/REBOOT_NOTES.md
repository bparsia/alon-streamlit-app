# Reboot notes (2026-08-31)

Read this first when resuming work in this repo after a restart.

## Repo status: this is now the canonical repo

`alon-streamlit-app` is the primary/active repo. `deontickit` (specifically its
`alon_experiments/alo_translator/` tree) is frozen legacy — don't make new changes
there unless explicitly asked to.

## What changed this session

- Added `pytest` as a proper dev dependency (`uv add --dev pytest`). This repo's
  own `.venv` (managed via `uv`) now has everything needed to run its test suite —
  no more reaching into `deontickit`'s venv.
- Run tests with `uv run pytest ...` from repo root. Example:
  `uv run pytest tests/test_konclude_baselines.py -k 3_5 -v -s`
- **Uncommitted as of this writing:** `pyproject.toml` and `uv.lock` carry the
  pytest addition but have not been committed yet. Check `git status` — if these
  are still modified/uncommitted, that's expected and intentional (left for the
  user to commit alongside other pending work, see below).

## Other pending working-tree state (not part of this session's work, don't clean up)

As of this session, `git status` shows:
- Modified: `alo_translator/serializers/index_strategies.py`,
  `tools/translation_table/build_ir.py`, `extract_primitives.py`,
  `extract_structural.py`, `render_latex.py`, `renderings.py`
- Untracked: `docs/konclude_challenges_summary.md`, `papers/mermaid_grammar.tex`
  (the latter is a deliberate WIP artifact, not accidental cruft)
- Local branch is 5 commits ahead of `origin/main`, not yet pushed.

None of this was touched or resolved this session — it's pre-existing in-progress
work. Don't commit/discard it reflexively; ask before touching.

## Why this matters: the actual goal was a Konclude performance check

The original ask this session was to run the Konclude baseline/table-generation
pipeline to check on "weirdly bad" performance, and specifically whether 3.5's
output still matches the known-good baseline
(`tests/fixtures/konclude_baselines.json`). **That check was never completed** —
runs kept getting derailed by tooling confusion (missing pytest in this repo's
venv, accidentally reaching for `deontickit`'s venv/binaries). That confusion is
now fixed (see above), but the actual performance/correctness check is still
outstanding. Next step on resume, if this is still the priority:

```
cd /Users/mbassbp2/Development/alon-streamlit-app
uv run pytest tests/test_konclude_baselines.py -k 3_5 -v -s
```

Compare the `satisfied_formulas` result against `tests/fixtures/konclude_baselines.json`
("3.5" entry). If it diverges, that's a real regression, not a tooling artifact.

Separately, there's an open unconfirmed hypothesis (see project memory
`project_konclude_performance.md` / `project_konclude_arm64_build.md`) that some
past 3.5/isabella slowness was machine-load-related rather than a code bug, and
that a native arm64 Konclude build exists and is faster than the x86_64 binary
currently referenced by `reasoner_config.toml` (`bin/Konclude`, confirmed x86_64
Mach-O). Whether the arm64 build is wired up here has not been checked this
session — don't assume either way.
