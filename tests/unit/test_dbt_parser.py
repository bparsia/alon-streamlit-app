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
    """Test parsing a simple DBT diagram."""

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

    model = parse_dbt_diagram(mermaid)

    # Model has h1 (the one explicitly declared in the diagram)
    assert len(model.histories) == 1
    assert "h1" in model.histories

    # h1 actions at root moment
    h1 = model.histories["h1"]
    acts = h1.complete_actions()
    assert acts.get("1") == "sd"
    assert acts.get("2") == "ss"

    # h1 leaf has q
    leaf = model.moments[h1.leaf_moment]
    assert "q" in leaf.propositions

    # Opposing relation present
    assert len(model.opposings) == 1


def test_parse_dbt_multiple_histories():
    """Test parsing DBT diagram with multiple explicit histories."""

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

    model = parse_dbt_diagram(mermaid)

    assert "h1" in model.histories
    assert "h2" in model.histories
    assert "h3" in model.histories

    # Check propositions on leaf moments
    assert "q" in model.moments[model.histories["h1"].leaf_moment].propositions
    assert "~q" in model.moments[model.histories["h2"].leaf_moment].propositions
    assert "~q" in model.moments[model.histories["h3"].leaf_moment].propositions


if __name__ == "__main__":
    test_parse_dbt_label()
    test_parse_simple_dbt()
    test_parse_dbt_multiple_histories()
    print("\n All DBT parser tests passed!")
