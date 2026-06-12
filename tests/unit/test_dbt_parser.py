"""
Test the DBT Mermaid diagram parser.
"""

from alo_translator.parsers.dbt_parser import parse_dbt_diagram, parse_dbt_label


def test_parse_dbt_label():
    """Test parsing DBT transition labels."""

    def norm_hist(h):
        return h[0] if isinstance(h, list) else h

    def norm_actions(a):
        # Accept int or str agent keys
        return {int(k): v for k, v in a.items()}

    # Simple case
    hist_name, actions = parse_dbt_label("h1({sd1, ss2})")
    assert norm_hist(hist_name) == "h1"
    assert norm_actions(actions) == {1: "sd", 2: "ss"}

    # Multiple histories (take first)
    hist_name, actions = parse_dbt_label("h1/h2({iasd3})")
    assert norm_hist(hist_name) == "h1"
    assert norm_actions(actions) == {3: "iasd"}

    # Multi-character action types
    hist_name, actions = parse_dbt_label("h3({iasd1, run2, jump3})")
    assert norm_hist(hist_name) == "h3"
    assert norm_actions(actions) == {1: "iasd", 2: "run", 3: "jump"}


def test_parse_simple_dbt():
    """Test parsing a simple DBT diagram (partial specification)."""

    mermaid = """---
type: DBT
actions:
  1:
    - sd
    - ss
  2:
    - ss
    - ha
opposings:
  sd1:
    - ha2
result: q
evaluation_point: m/h1
---
classDiagram
direction BT
  class m {
  }
  m --> m1 : h1({sd1, ss2})
  m1: q
"""

    model, partial_spec = parse_dbt_diagram(mermaid)

    # Verify partial_spec
    assert partial_spec["diagram_type"] == "DBT"
    assert partial_spec["actions"] == {1: ["sd", "ss"], 2: ["ss", "ha"]}
    # Agent keys may be int or str depending on parser
    h1_hist = partial_spec["histories"]["h1"]
    assert h1_hist.get(1, h1_hist.get("1")) == "sd"
    assert h1_hist.get(2, h1_hist.get("2")) == "ss"
    assert partial_spec["opposings"] == {"sd1": ["ha2"]}

    # results dict now has shape {"h1": {"moment": ..., "props": [...]}}
    assert "h1" in partial_spec["results"]
    assert "q" in partial_spec["results"]["h1"]["props"]

    # Verify model has all histories generated (2x2 = 4)
    assert len(model.named_histories) == 4

    assert "h1" in model.named_histories
    h1 = model.named_histories["h1"]
    assert h1.actions == {"1": "sd", "2": "ss"}

    assert len(model.results) >= 1
    h1_result = next(r for r in model.results if r.history_name == "h1")
    assert "q" in h1_result.true_propositions


def test_parse_dbt_multiple_histories():
    """Test parsing DBT diagram with multiple histories."""

    mermaid = """---
type: DBT
actions:
  1:
    - sd
    - ss
  2:
    - ss
    - ha
---
classDiagram
direction BT
  class m {
  }
  m --> m1 : h1({sd1, ss2})
  m --> m2 : h2({sd1, ha2})
  m --> m3 : h3({ss1, ss2})
  m1: q
  m2: ~q
  m3: ~q
"""

    model, partial_spec = parse_dbt_diagram(mermaid)

    assert len(partial_spec["histories"]) == 3
    assert "h1" in partial_spec["histories"]
    assert "h2" in partial_spec["histories"]
    assert "h3" in partial_spec["histories"]

    assert len(partial_spec["results"]) == 3
    assert "q" in partial_spec["results"]["h1"]["props"]
    assert "~q" in partial_spec["results"]["h2"]["props"]
    assert "~q" in partial_spec["results"]["h3"]["props"]


if __name__ == "__main__":
    test_parse_dbt_label()
    test_parse_simple_dbt()
    test_parse_dbt_multiple_histories()
    print("\n All DBT parser tests passed!")
