# Testing & Result Registry

## Test suite

```
pytest                            # run everything
pytest tests/test_registry.py -v # registry regression tests only
pytest tests/test_datalog_baselines.py -v
pytest tests/test_konclude_baselines.py -v  # skipped if Konclude not configured
```

All tests live under `tests/`. Unit tests are under `tests/unit/`.

---

## Result registry

`tests/registry.py` maintains a versioned, append-only record of reasoning
results in `tests/fixtures/result_registry.json`. It is a **change detector**,
not a correctness oracle — any translation/reasoner system whose results have
been captured and verified will be regression-tested on every `pytest` run.

### Structure of a registry entry

```json
{
  "model": "3.1",
  "model_hash": "c349343801a6",
  "commit": "f5b458c",
  "tag": null,
  "date": "2026-06-15",
  "variants_run": ["datalog", "owl_full_cardinality"],
  "cross_check": {"datalog_vs_owl_full_cardinality": "agree"},
  "verified": true,
  "source": "hand-checked against book example",
  "results": [
    {"formula": "[1 pres]q", "datalog": true, "owl_full_cardinality": true},
    {"formula": "[1 sres]q", "datalog": true, "owl_full_cardinality": true},
    ...
  ]
}
```

- **`model_hash`** — SHA-256 of the `.mmd` file content (first 12 hex chars). Changes if the model changes.
- **`variants_run`** — which pipeline(s) produced results in this entry.
- **`cross_check`** — automatic agreement check between every pair of variants.
- **`verified`** — human sign-off. Only verified entries are used as regression baselines.

### Variants

A variant is a string naming a complete translation+reasoner pipeline:

| Variant | Translation | Reasoner |
|---|---|---|
| `datalog` | pyDatalog serializer | pyDatalog (in-process) |
| `owl_full_cardinality` | OWL EquivFullCardinalityStrategy | Konclude |
| `owl_chained_nominal` | OWL EquivChainedNominalStrategy | Konclude |

OWL variants are skipped automatically in tests if the Konclude binary is not
configured (see `reasoner_config.toml`).

### Adding a new model

```bash
# 1. Add the model file
cp my_model.mmd streamlit_app/models/4.1.mmd

# 2. Capture results (datalog always available; OWL needs Konclude)
python -m tests.registry capture --models 4.1

# 3. Review the printed formula list, then verify
python -m tests.registry verify \
    --model 4.1 \
    --commit $(git rev-parse --short HEAD) \
    --source "hand-checked"

# 4. Done — pytest picks it up automatically
pytest tests/test_registry.py
```

### Adding a new reasoner or OWL strategy

1. Add a runner in `tests/registry.py`:
   - For a new OWL strategy, add it to `_run_owl`'s `strategy_map`.
   - For a wholly new reasoner (e.g. HermiT, SPARQL), add a new `_run_X` function and a branch in `capture()`.
2. Capture results: `python -m tests.registry capture --models 3.1 3.5 3.6 3.7 --variants your_variant`
3. Verify as above.

No changes to `test_registry.py` are needed — tests auto-discover all verified (model, variant) pairs from the registry.

### After changing pipeline code

If your change is expected to preserve results:
```bash
pytest tests/test_registry.py   # should all pass
```

If your change intentionally changes results (e.g. a semantics fix):
```bash
# Run a new capture and verify — this becomes the new baseline
python -m tests.registry capture --models 3.1 3.5 3.6 3.7
python -m tests.registry verify --model 3.1 --commit $(git rev-parse --short HEAD) --source "fixed X"
# repeat for each model
```

The old verified entries are preserved (append-only); only the most recent
verified entry per (model, variant) is used as the regression baseline.

### CLI reference

```
python -m tests.registry capture --models 3.1 3.5 --variants datalog owl_full_cardinality
python -m tests.registry verify  --model 3.1 --commit f5b458c --source "book example"
python -m tests.registry show
python -m tests.registry show --model 3.1 --verified-only
```

---

## Konclude baselines (`tests/fixtures/konclude_baselines.json`)

A separate, static fixture produced with Konclude + `EquivFullCardinalityStrategy`.
Used by `test_konclude_baselines.py` and `test_datalog_baselines.py` to check
correctness of the datalog pipeline against an independent reasoner.

These baselines are **fixed reference points**, not regenerated automatically.
Update them only when a deliberate semantics change is made and independently verified.
