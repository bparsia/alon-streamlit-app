"""
ALOn query pipeline (Pass 3, 4).

Provides helpers for parsing and expanding queries on an ALOModel produced
by parse_dbt_diagram().

Pipeline:
- Pass 1 (dbt_parser.py): Parse Mermaid diagram → ALOModel
- Pass 3 (this module): Parse query strings → FormulaNode AST
- Pass 4 (this module): Expand defined forms → primitive operators

Usage:
    from alo_translator.parsers.dbt_parser import parse_dbt_diagram
    from alo_translator.parsers.builder import parse_queries

    model = parse_dbt_diagram("...")
    model = parse_queries(model)
"""

from ..model.core import ALOModel
from .formula_parser import parse_formula  # re-exported for convenience
from .formula_registry import FormulaRegistry
from .hierarchical_expander import HierarchicalExpander


def parse_queries(model: ALOModel) -> ALOModel:
    """
    Parse all query strings to FormulaNode AST (Pass 3).

    Updates model.queries[i].formula_ast for each query.
    If responsibility_config is present, generates responsibility queries first.
    """
    if model.responsibility_config is not None:
        from ..query_generation import generate_queries as gen_resp_queries
        model.queries.extend(gen_resp_queries(model))

    for query in model.queries:
        if query.formula_ast is None:
            query.formula_ast = parse_formula(query.formula_string)
    return model


def expand_queries(model: ALOModel, expand_standard: bool = False,
                   evaluation_history: str = "h1",
                   evaluation_moment: str = None) -> ALOModel:
    """
    Expand all defined forms in queries (Pass 4) using HierarchicalExpander.
    """
    registry = FormulaRegistry()
    expander = HierarchicalExpander(model, registry,
                                     evaluation_history=evaluation_history,
                                     evaluation_moment=evaluation_moment)

    query_owl_names = {}
    for query in model.queries:
        if query.formula_ast is None:
            raise ValueError(
                f"Cannot expand query '{query.formula_string}': "
                f"not yet parsed (call parse_queries first)"
            )
        owl_name = registry.register(query.formula_ast, label=query.formula_string)
        if query.query_id:
            query_owl_names[query.query_id] = owl_name
        else:
            query.query_id = owl_name

    expander.expand_all()
    model.formula_registry = registry

    for query in model.queries:
        if query.formula_ast:
            owl_name = query_owl_names.get(query.query_id) or query.formula_ast.to_owl_name()
            if owl_name in registry.formulas:
                query.expanded_ast = registry.formulas[owl_name]

    return model
