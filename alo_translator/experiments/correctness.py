"""Correctness checking for ALOn experiment results."""

try:
    import tomllib as tomli
except ImportError:
    import tomli
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Set


class CorrectnessChecker:
    """Check ALOn reasoning results against expected query results.

    This class loads query definitions from TOML files and validates
    that reasoner results match expected outcomes.
    """

    def __init__(self, theory_toml_path: Optional[Path] = None, owl_file_path: Optional[Path] = None):
        """Initialize correctness checker.

        Args:
            theory_toml_path: Path to theory TOML file with query definitions
            owl_file_path: Path to generated OWL file with query class labels
        """
        self.theory_toml_path = theory_toml_path
        self.owl_file_path = owl_file_path
        self.queries: Dict[str, List[str]] = {}
        self.designated_individual: Optional[str] = None
        self.query_class_map: Dict[str, str] = {}  # query_expr -> class_name

        if theory_toml_path and theory_toml_path.exists():
            self._load_queries()

        if owl_file_path and owl_file_path.exists():
            self._load_query_class_mapping()

    def _load_queries(self) -> None:
        """Load query definitions from TOML file."""
        if not self.theory_toml_path:
            return

        with open(self.theory_toml_path, 'rb') as f:
            data = tomli.load(f)

        # Load query categories from [Queries] section
        self.queries = data.get('Queries', {})

        # If there's a responsibility_analysis section, generate those queries too
        resp_config = data.get('responsibility_analysis')
        if resp_config:
            # Generate queries from responsibility_analysis config
            auto_queries = self._generate_responsibility_queries(data, resp_config)
            if auto_queries:
                # Add generated queries to a new category
                self.queries['Auto-generated'] = auto_queries

        # In ALOn translations, queries are evaluated at the modal individual 'm'
        # which represents the model/history at which formulas are evaluated
        # The history h1 is part of the context, but queries check membership at 'm'
        self.designated_individual = 'm'

    def _generate_responsibility_queries(self, model_data: dict, resp_config: dict) -> List[str]:
        """Generate responsibility queries from config.

        This mirrors the logic in query_generation.py but just returns the query expressions
        as strings for correctness checking.
        """
        from itertools import combinations

        queries = []

        # Get agents
        agents_actions = model_data.get('Actions', {})
        if resp_config.get('agents') == 'all':
            agents = sorted(agents_actions.keys())
        else:
            agents = sorted(resp_config.get('agents', []))

        # Generate agent sets based on groups config
        groups_spec = resp_config.get('groups', 'singletons')
        agent_sets = []

        if groups_spec == 'singletons':
            agent_sets = [[a] for a in agents]
        elif groups_spec == 'all':
            for r in range(1, len(agents) + 1):
                agent_sets.extend([list(s) for s in combinations(agents, r)])
        elif isinstance(groups_spec, str) and groups_spec.startswith('size<='):
            max_size = int(groups_spec.split('<=')[1])
            for r in range(1, min(max_size + 1, len(agents) + 1)):
                agent_sets.extend([list(s) for s in combinations(agents, r)])
        else:
            agent_sets = groups_spec  # Explicit list

        # Get history for but/ness lookups
        history_name = resp_config.get('history', 'h1')
        histories = model_data.get('Histories', {})
        history_action = histories.get(history_name, {})

        prop = resp_config.get('target_proposition', 'q')
        resp_types = resp_config.get('responsibility_types', [])

        # Generate queries
        for agent_set in agent_sets:
            if len(agent_set) == 1:
                agent_expr = agent_set[0]
            else:
                agent_expr = "{" + ", ".join(agent_set) + "}"

            for resp_type in resp_types:
                if resp_type in ["pres", "sres", "res", "dsxtit"]:
                    queries.append(f"[{agent_expr} {resp_type}]{prop}")
                elif resp_type in ["but", "ness"]:
                    if len(agent_set) == 1:
                        # Individual agent
                        agent_id = agent_set[0]
                        if agent_id in history_action:
                            action_type = history_action[agent_id]
                            action_id = f"{action_type}{agent_id}"
                            queries.append(f"{resp_type}({action_id}, {prop})")
                    else:
                        # Group/coalition - generate joint action query
                        if all(agent_id in history_action for agent_id in agent_set):
                            action_ids = [f"{history_action[agent_id]}{agent_id}"
                                         for agent_id in agent_set]
                            joint_action = "{" + ", ".join(action_ids) + "}"
                            queries.append(f"{resp_type}({joint_action}, {prop})")

        return queries

    def _load_query_class_mapping(self) -> None:
        """Load mapping from query expressions to OWL class names from OWL file.

        The generated OWL file contains AnnotationAssertion elements that map
        query class IRIs to their query expression labels using rdfs:label.
        """
        if not self.owl_file_path:
            return

        try:
            tree = ET.parse(self.owl_file_path)
            root = tree.getroot()

            # OWL namespace - handle both with and without namespace prefix
            ns = {'owl': 'http://www.w3.org/2002/07/owl#'}

            # Find all annotation assertions
            # Try both namespaced and non-namespaced queries
            for annotation_assertion in root.iter():
                if annotation_assertion.tag.endswith('AnnotationAssertion'):
                    # Find AnnotationProperty - check for rdfs:label IRI
                    prop_elem = None
                    for child in annotation_assertion:
                        if child.tag.endswith('AnnotationProperty'):
                            prop_iri = child.get('IRI', '')
                            if 'label' in prop_iri:
                                prop_elem = child
                                break

                    if prop_elem is not None:
                        # Find the IRI element (subject of annotation)
                        iri_text = None
                        literal_text = None

                        for child in annotation_assertion:
                            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                            if tag == 'IRI':
                                # IRI can be in text or text attribute
                                iri_text = child.get('text') or child.text
                            elif tag == 'Literal':
                                # Literal can be in text or text attribute
                                literal_text = child.get('text') or child.text

                        if iri_text and literal_text:
                            # Extract class name from IRI (e.g., 'http://...#q01' -> 'q01')
                            if '#q' in iri_text:
                                class_name = iri_text.split('#')[-1]
                                # Map query expression to class name
                                self.query_class_map[literal_text] = class_name

        except Exception as e:
            # If we can't parse the OWL file, just continue without the mapping
            print(f"  [WARNING] Could not load query class mapping: {e}")

    def check_results(
        self,
        individual_types: Dict[str, Set[str]]
    ) -> Dict[str, bool]:
        """Check reasoning results against expected query outcomes.

        This performs a basic correctness check by verifying which queries
        (represented as OWL classes) the designated individual belongs to.

        Args:
            individual_types: Map from individual names to their inferred types

        Returns:
            Map from query expressions to boolean results (True if individual
            is a member of the query class)
        """
        if not self.queries or not self.designated_individual:
            return {}

        # Get types for the designated individual
        individual_classes = individual_types.get(self.designated_individual, set())

        # Map query expressions to membership results
        results = {}

        for category, query_list in self.queries.items():
            for query_expr in query_list:
                # The query expression is translated to an OWL class
                # For now, we check if any class name matches the query
                # This is a simplified approach - a full implementation would
                # need to map query expressions to their generated class names

                # Simple heuristic: check if the query appears in individual's types
                # This works for simple cases but may need refinement
                found = self._query_matches_any_class(query_expr, individual_classes)
                results[query_expr] = found

        return results

    def _query_matches_any_class(
        self,
        query_expr: str,
        individual_classes: Set[str]
    ) -> bool:
        """Check if a query expression matches any of the individual's classes.

        Uses the query_class_map loaded from the OWL file to map query
        expressions to their corresponding OWL class names.

        Args:
            query_expr: Query expression (e.g., 'Xq', 'do(sd1)')
            individual_classes: Set of class names the individual belongs to

        Returns:
            True if the individual is a member of the query class
        """
        # Look up the class name for this query expression
        class_name = self.query_class_map.get(query_expr)

        if class_name:
            # Check if the individual is a member of this class
            return class_name in individual_classes

        # If we don't have a mapping for this query, we can't check it
        return False

    def generate_summary(
        self,
        results: Dict[str, bool]
    ) -> Dict[str, int]:
        """Generate summary statistics from correctness results.

        Args:
            results: Map from query expressions to boolean results

        Returns:
            Summary dict with counts of passed/failed queries
        """
        passed = sum(1 for v in results.values() if v)
        failed = sum(1 for v in results.values() if not v)

        return {
            'total_queries': len(results),
            'passed': passed,
            'failed': failed,
            'pass_rate': passed / len(results) if results else 0.0
        }
