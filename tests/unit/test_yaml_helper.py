"""
Test the YAML frontmatter parsing helper.
"""

from alo_translator.parsers.yaml_helper import frontmatter_to_partial_spec


def test_basic_frontmatter():
    """Test parsing basic YAML frontmatter matching 3.1_auto.toml structure."""

    yaml_string = """
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
"""

    partial_spec = frontmatter_to_partial_spec(yaml_string)

    print("Parsed partial_spec:")
    for key, value in partial_spec.items():
        print(f"  {key}: {value}")

    # Verify structure
    assert partial_spec["diagram_type"] == "DBT"
    assert partial_spec["actions"] == {1: ["sd", "ss"], 2: ["ss", "ha"]}
    assert partial_spec["opposings"] == {"sd1": ["ha2"]}
    assert partial_spec["result"] == "q"
    assert partial_spec["evaluation_point"] == "m/h1"

    print("\n✓ Basic frontmatter parsing works!")


def test_frontmatter_with_aliases():
    """Test parsing frontmatter with aliases."""

    yaml_string = """
type: DBT
actions:
  1:
    - sd
    - ss
  2:
    - ss
    - ha
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
