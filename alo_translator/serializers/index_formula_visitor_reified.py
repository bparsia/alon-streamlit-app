"""
Formula visitor for reified moment semantics.

Uses moment individuals with has_index/index_of properties instead of
equivalence relation on same_moment.
"""

from xml.etree.ElementTree import Element, SubElement
from typing import Optional, Dict

from .index_formula_visitor import IndexFormulaToOWLVisitor
from ..model.formula import Box, Diamond


class IndexFormulaToOWLVisitorReified(IndexFormulaToOWLVisitor):
    """
    Visitor for translating ALOn formulas to OWL using reified moment semantics.

    Overrides Box and Diamond translations to use:
    - Box: []φ → index_of only (has_index only φ)
    - Diamond: <>φ → index_of only (has_index some φ)

    The moment access is uniform (index_of only) for both operators.
    Only difference is quantification over indices (only vs some).
    """

    def _visit_box(self, node: Box) -> Element:
        """
        Translate box: []φ → index_of some (has_index only φ)

        "There exists a moment this index belongs to (exactly one by functionality)
        such that all its indices satisfy φ"

        Note: index_of is functional, so 'some' vs 'only' should be semantically
        equivalent, but Konclude requires 'some' to work correctly.
        """
        # Build: index_of some (has_index only φ)
        outer_restriction = Element("ObjectSomeValuesFrom")
        SubElement(outer_restriction, "ObjectProperty", {"IRI": self._iri("index_of")})

        # Build inner: has_index only φ
        inner_restriction = SubElement(outer_restriction, "ObjectAllValuesFrom")
        SubElement(inner_restriction, "ObjectProperty", {"IRI": self._iri("has_index")})
        inner_restriction.append(self.visit(node.formula))

        return outer_restriction

    def _visit_diamond(self, node: Diamond) -> Element:
        """
        Translate diamond: <>φ → index_of some (has_index some φ)

        "There exists a moment this index belongs to (exactly one by functionality)
        that has at least one index satisfying φ"

        Note: index_of is functional, so 'some' vs 'only' should be semantically
        equivalent, but Konclude requires 'some' to work correctly.
        """
        # Build: index_of some (has_index some φ)
        outer_restriction = Element("ObjectSomeValuesFrom")
        SubElement(outer_restriction, "ObjectProperty", {"IRI": self._iri("index_of")})

        # Build inner: has_index some φ
        inner_restriction = SubElement(outer_restriction, "ObjectSomeValuesFrom")
        SubElement(inner_restriction, "ObjectProperty", {"IRI": self._iri("has_index")})
        inner_restriction.append(self.visit(node.formula))

        return outer_restriction
