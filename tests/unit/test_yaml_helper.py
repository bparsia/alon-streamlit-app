"""
Test the YAML frontmatter parsing helper.
"""

from alo_translator.parsers.yaml_helper import frontmatter_to_partial_spec


def test_basic_frontmatter():
    """Test parsing basic YAML frontmatter (opposings, res_analyse)."""

    yaml_string = """
type: DBT
opposings:
  sd1:
    - ha2
res_analyse:
  - [m/h1, q]
"""

    partial_spec = frontmatter_to_partial_spec(yaml_string)

    print("Parsed partial_spec:")
    for key, value in partial_spec.items():
        print(f"  {key}: {value}")

    # Verify structure
    assert "diagram_type" not in partial_spec
    assert partial_spec["opposings"] == {"sd1": ["ha2"]}
    assert partial_spec["res_analyse"] == [["m/h1", "q"]]

    print("\n✓ Basic frontmatter parsing works!")


def test_frontmatter_with_aliases():
    """Test parsing frontmatter with aliases."""

    yaml_string = """
type: DBT
aliases:
  1: Alice
  2: Beth
  sd: shoots Dan
  ss: stands still
  ha: hits Alice
  q: Dan dies
"""

    partial_spec = frontmatter_to_partial_spec(yaml_string)

    print("\nParsed partial_spec with aliases:")
    for key, value in partial_spec.items():
        print(f"  {key}: {value}")

    assert partial_spec["aliases"]["sd"] == "shoots Dan"
    # PyYAML parses numeric YAML keys as ints; accept either int or str key
    aliases = partial_spec["aliases"]
    assert aliases.get("1", aliases.get(1)) == "Alice"

    print("\n✓ Frontmatter with aliases works!")


def test_empty_frontmatter():
    """Test handling of empty or missing frontmatter."""

    partial_spec = frontmatter_to_partial_spec(None)
    assert partial_spec == {}

    partial_spec = frontmatter_to_partial_spec("")
    assert partial_spec == {}

    print("\n✓ Empty frontmatter handling works!")


if __name__ == "__main__":
    test_basic_frontmatter()
    test_frontmatter_with_aliases()
    test_empty_frontmatter()
    print("\n✅ All YAML helper tests passed!")
