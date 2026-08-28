"""
Tests for the `background` frontmatter key (GCI-style constraints holding
at every index, not anchored to any moment/history).

Covers:
1. A plain formula (inertia: q -> Xq) parses onto ALOModel.background and
   OWLSerializer emits it as SubClassOf(owl:Thing, <expr>).
2. DatalogIndexSerializer raises when model.background is non-empty --
   background theory has no Datalog representation, by design.
3. A formula needing a concrete evaluation index (pres, which looks up the
   actual action at the eval moment/history) is skipped with a warning
   rather than crashing the whole serialization.
4. (Konclude required) The inertia axiom has real semantic force under a
   full DL reasoner, not just axiom-text presence: a TD=2 model with q at
   the root moment and ~q at its direct successor is genuinely
   UNSATISFIABLE under q -> Xq, and satisfiable without it (control).

Run with:
  pytest tests/test_background_theory.py -v
"""

import re
import warnings
from pathlib import Path

import pytest

from alo_translator.parsers.dbt_parser import parse_dbt_diagram
from alo_translator.serializers.owl import OWLSerializer
from alo_translator.serializers.datalog import DatalogIndexSerializer


INERTIA_MMD = """---
title: Background theory test
background:
  - "q -> Xq"
---
classDiagram
direction BT
m --> m1 : h1({sd1})
m1: q
"""

PRES_BACKGROUND_MMD = """---
title: Background theory test (pres, requires eval context)
background:
  - "[1 pres]q"
---
classDiagram
direction BT
m --> m1 : h1({sd1})
m1: q
"""

NO_BACKGROUND_MMD = """---
title: No background key
---
classDiagram
direction BT
m --> m1 : h1({sd1})
m1: q
"""

# TD=2: q holds at the root moment m, ~q holds at m's direct successor mm.
# Under "q -> Xq" this is a direct, minimal contradiction (X resolves to the
# succ OWL object property, i.e. the actual next moment along the history --
# not the eval-moment-relative "next query step").
INERTIA_CONTRADICTION_MMD = """---
title: Inertia contradiction (TD=2)
background:
  - "q -> Xq"
---
classDiagram
direction BT
m --> mm : h1({sd1})
mm --> m1 : h1({ss2})
m: q
mm: ~q
"""

INERTIA_CONTRADICTION_NO_BACKGROUND_MMD = INERTIA_CONTRADICTION_MMD.replace(
    'background:\n  - "q -> Xq"\n', ""
)


def _find_konclude() -> Path | None:
    """Find Konclude binary via reasoner_config.toml, else None."""
    from alo_translator.reasoners.config import load_config
    root = Path(__file__).parent.parent
    for config_path in [root / "reasoner_config.toml", Path("reasoner_config.toml")]:
        try:
            config = load_config(config_path)
            p = Path(config.reasoners["konclude"].path)
            if not p.is_absolute():
                p = config_path.parent / p
            if p.exists():
                return p
        except Exception:
            continue
    return None


def _konclude_available() -> bool:
    return _find_konclude() is not None


def test_background_key_parses_onto_model():
    model = parse_dbt_diagram(INERTIA_MMD)
    assert model.background == ["q -> Xq"]


def test_background_defaults_to_empty():
    model = parse_dbt_diagram(NO_BACKGROUND_MMD)
    assert model.background == []


def test_owl_serializer_emits_subclassof_thing_for_background_formula():
    model = parse_dbt_diagram(INERTIA_MMD)
    owl_xml = OWLSerializer(model, evaluation_moment="m", evaluation_history="h1").serialize()

    subclassof_blocks = re.findall(r"<SubClassOf>.*?</SubClassOf>", owl_xml, re.DOTALL)
    thing_headed = [b for b in subclassof_blocks if "owl#Thing" in b]

    # The succ-totality axiom is also SubClassOf(Thing, ...) -- the background
    # axiom is a second, distinct one referencing q.
    background_axioms = [b for b in thing_headed if "alon#q" in b]
    assert len(background_axioms) == 1, (
        f"expected exactly one background SubClassOf(Thing, ...) axiom "
        f"referencing q, found {len(background_axioms)}"
    )


def test_datalog_serializer_raises_on_nonempty_background():
    model = parse_dbt_diagram(INERTIA_MMD)
    with pytest.raises(ValueError, match="background theory"):
        DatalogIndexSerializer(model, evaluation_history="h1", evaluation_moment="m")


def test_datalog_serializer_ok_without_background():
    model = parse_dbt_diagram(NO_BACKGROUND_MMD)
    # Should not raise.
    DatalogIndexSerializer(model, evaluation_history="h1", evaluation_moment="m")


def test_background_formula_needing_eval_context_warns_and_is_skipped():
    model = parse_dbt_diagram(PRES_BACKGROUND_MMD)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        owl_xml = OWLSerializer(model, evaluation_moment="m", evaluation_history="h1").serialize()

    matching = [w for w in caught if "pres" in str(w.message) and "Skipping background formula" in str(w.message)]
    assert len(matching) == 1, f"expected exactly one skip warning, got {len(caught)} warnings total"
    # Serialization must still complete successfully -- no crash, valid OWL/XML produced.
    assert "<Ontology" in owl_xml


@pytest.mark.skipif(not _konclude_available(), reason="Konclude binary not found")
def test_inertia_background_makes_contradictory_td2_model_unsatisfiable(tmp_path):
    """q -> Xq must have real semantic force under a full DL reasoner, not
    just be present as axiom text: a TD=2 model with q at the root moment
    and ~q at its direct successor is genuinely inconsistent.
    """
    from streamlit_app.utils import konclude_path
    from alo_translator.reasoners.konclude import KoncludeAdapter
    from alo_translator.reasoners.base import ReasoningMode

    model = parse_dbt_diagram(INERTIA_CONTRADICTION_MMD)
    assert model.background == ["q -> Xq"]

    owl_xml = OWLSerializer(model, evaluation_moment="m", evaluation_history="h1").serialize()
    owl_path = tmp_path / "inertia_contradiction.owl"
    owl_path.write_text(owl_xml)

    adapter = KoncludeAdapter(konclude_path())
    result = adapter.run(owl_path, ReasoningMode.REALISATION, timeout=60)

    assert result.success is False
    assert result.error_message is not None and "inconsistent" in result.error_message.lower()


@pytest.mark.skipif(not _konclude_available(), reason="Konclude binary not found")
def test_same_td2_model_without_background_is_satisfiable(tmp_path):
    """Control: the identical q/~q structure is consistent when the
    background axiom is absent -- confirms the axiom, not something else
    about the model shape, is what causes the inconsistency above.
    """
    from streamlit_app.utils import konclude_path
    from alo_translator.reasoners.konclude import KoncludeAdapter
    from alo_translator.reasoners.base import ReasoningMode

    model = parse_dbt_diagram(INERTIA_CONTRADICTION_NO_BACKGROUND_MMD)
    assert model.background == []

    owl_xml = OWLSerializer(model, evaluation_moment="m", evaluation_history="h1").serialize()
    owl_path = tmp_path / "inertia_contradiction_control.owl"
    owl_path.write_text(owl_xml)

    adapter = KoncludeAdapter(konclude_path())
    result = adapter.run(owl_path, ReasoningMode.REALISATION, timeout=60)

    assert result.success is True
    assert result.error_message is None
