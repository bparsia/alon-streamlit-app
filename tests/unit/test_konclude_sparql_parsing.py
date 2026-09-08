"""
Unit tests for KoncludeAdapter.parse_sparql_output -- parses Konclude's
SPARQL 1.1 XML Results Format output. No Konclude binary needed (pure
string parsing), unlike tests/test_konclude_sparql_baselines.py.
"""

from pathlib import Path

from alo_translator.reasoners.konclude import KoncludeAdapter

SAMPLE_RESULTS = """<?xml version="1.0" encoding="UTF-8"?>
<sparql xmlns="http://www.w3.org/2005/sparql-results#" xml:base="http://www.w3.org/2005/sparql-results#" xmlns:owl="http://www.w3.org/2002/07/owl#" xmlns:xsd="http://www.w3.org/2001/XMLSchema#">
<head>
  <variable name="idx0"/>
</head>
<results>
 <result>
  <binding name="idx0"><uri>http://www.semanticweb.org/alon#m_h1</uri></binding>
 </result>
 <result>
  <binding name="idx0"><uri>http://www.semanticweb.org/alon#m_h2</uri></binding>
 </result>
</results>
</sparql>
"""

EMPTY_RESULTS = """<?xml version="1.0" encoding="UTF-8"?>
<sparql xmlns="http://www.w3.org/2005/sparql-results#" xml:base="http://www.w3.org/2005/sparql-results#" xmlns:owl="http://www.w3.org/2002/07/owl#" xmlns:xsd="http://www.w3.org/2001/XMLSchema#">
<head>
  <variable name="idx0"/>
</head>
<results>
</results>
</sparql>
"""


def make_adapter() -> KoncludeAdapter:
    # KoncludeAdapter doesn't touch reasoner_path for parsing -- any path
    # is fine here, the binary itself is never invoked.
    return KoncludeAdapter(Path("/nonexistent/Konclude"))


def test_parse_sparql_output_extracts_bound_individuals():
    adapter = make_adapter()
    bound = adapter.parse_sparql_output(SAMPLE_RESULTS)
    assert bound == {"m_h1", "m_h2"}


def test_parse_sparql_output_empty_results():
    adapter = make_adapter()
    bound = adapter.parse_sparql_output(EMPTY_RESULTS)
    assert bound == set()


def test_parse_sparql_output_duplicate_bindings_collapse_to_set():
    """A UNION query legitimately produces one result row per matching
    branch -- the same individual can appear more than once if it
    satisfies multiple branches. Callers need membership, not row count,
    so duplicates must collapse (this is what Set[str] as the return type
    is for, not an incidental side effect)."""
    duplicated = SAMPLE_RESULTS.replace(
        "</results>",
        ' <result>\n  <binding name="idx0"><uri>http://www.semanticweb.org/alon#m_h1</uri></binding>\n </result>\n</results>',
    )
    adapter = make_adapter()
    bound = adapter.parse_sparql_output(duplicated)
    assert bound == {"m_h1", "m_h2"}


def test_parse_sparql_output_malformed_xml_returns_empty_set():
    adapter = make_adapter()
    bound = adapter.parse_sparql_output("not xml at all")
    assert bound == set()
