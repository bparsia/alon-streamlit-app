#!/usr/bin/env python3
"""
Standalone OWL Responsibility Analyzer

Analyzes an OWL file containing ALOn responsibility queries using Konclude reasoner
and produces a formatted results table.

NO DEPENDENCIES - Just Python 3.7+ standard library + Konclude binary

Usage:
    python analyze_owl.py <owl_file> [--konclude PATH] [--timeout SECONDS]

Example:
    python analyze_owl.py model.owl
    python analyze_owl.py model.owl --konclude /usr/local/bin/Konclude --timeout 600

Download this script and your .owl file, install Konclude, and run!
"""

import sys
import argparse
import subprocess
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict


def run_konclude(owl_file: Path, konclude_path: str = "Konclude", timeout: int = 300, verbose: bool = False):
    """
    Run Konclude reasoner on OWL file and return individual types.

    Returns: dict mapping individual IRIs to sets of class IRIs they belong to
    """
    # Create output file
    output_file = owl_file.with_suffix('.owl.xml')

    try:
        # Run Konclude realization command
        cmd = [
            str(konclude_path),
            "realization",
            "-i", str(owl_file),
            "-o", str(output_file)
        ]

        if verbose:
            print(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode != 0:
            raise RuntimeError(f"Konclude failed with return code {result.returncode}\n{result.stderr}")

        if verbose and result.stdout:
            print("Konclude output:", result.stdout)

        # Parse the output OWL file to extract individual types
        individual_types = parse_konclude_output(output_file)

        return individual_types

    finally:
        # Clean up output file
        if output_file.exists():
            output_file.unlink()


def parse_konclude_output(output_file: Path):
    """
    Parse Konclude's OWL output to extract individual types.

    Returns: dict mapping individual IRIs to sets of class IRIs
    """
    individual_types = defaultdict(set)

    try:
        tree = ET.parse(output_file)
        root = tree.getroot()

        # Define namespaces
        ns = {
            'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
            'owl': 'http://www.w3.org/2002/07/owl#'
        }

        # Find ClassAssertion axioms: <individual> rdf:type <class>
        for class_assertion in root.findall('.//owl:ClassAssertion', ns):
            # Get the class
            class_elem = class_assertion.find('owl:Class', ns)
            if class_elem is not None:
                class_iri = class_elem.get('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about')
                if class_iri:
                    # Extract fragment (after #)
                    class_name = class_iri.split('#')[-1] if '#' in class_iri else class_iri

                    # Get the individual
                    ind_elem = class_assertion.find('owl:NamedIndividual', ns)
                    if ind_elem is not None:
                        ind_iri = ind_elem.get('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about')
                        if ind_iri:
                            ind_name = ind_iri.split('#')[-1] if '#' in ind_iri else ind_iri
                            individual_types[ind_name].add(class_name)

    except ET.ParseError as e:
        raise RuntimeError(f"Failed to parse Konclude output: {e}")

    return individual_types


def extract_queries_from_owl(owl_file: Path):
    """Extract query class names from OWL file."""
    queries = set()
    with open(owl_file, 'r') as f:
        content = f.read()
        # Find query classes like q_pres_1_m_h1, q_but_sd1_m_h1, etc.
        pattern = r'<owl:Class rdf:about="[^"]*#(q_[^"]+)"'
        queries = set(re.findall(pattern, content))
    return queries


def format_results_table(satisfied_queries: set, all_queries: set):
    """Format responsibility results as a table."""
    agent_results = defaultdict(lambda: {
        'pres': False, 'sres': False, 'res': False,
        'dxstit': False, 'but': False, 'ness': False
    })

    action_legend = {}

    for query_id in all_queries:
        satisfied = query_id in satisfied_queries

        parts = query_id.split('_')
        if len(parts) >= 3:
            resp_type = parts[1]
            # Everything between type and m_h1
            agent_parts = parts[2:-2]
            agent_str = '_'.join(agent_parts)

            if resp_type in ('but', 'ness'):
                m = re.match(r'^([a-zA-Z]+)(\d+)$', agent_str)
                if m:
                    action_id = agent_str
                    agent_str = m.group(2)
                    action_legend[agent_str] = action_id

            if resp_type in agent_results[agent_str]:
                agent_results[agent_str][resp_type] = satisfied

    sorted_agents = sorted(agent_results.keys(), key=lambda x: (len(x.split('_')), x))

    # Build results table
    print("\n" + "="*70)
    print("RESPONSIBILITY ANALYSIS RESULTS")
    print("="*70)
    print("\n| Agent/Coalition | PRES | SRES | RES | DXSTIT | BUT | NESS |")
    print("|----------------|------|------|-----|--------|-----|------|")

    for agent in sorted_agents:
        r = agent_results[agent]

        # Format agent name
        if '_' in agent:
            agent_display = '{' + agent.replace('_', ', ') + '}'
        else:
            agent_display = f"Agent {agent}"

        pres = " ✓ " if r['pres'] else "   "
        sres = " ✓ " if r['sres'] else "   "
        res = " ✓ " if r['res'] else "   "
        dxstit = " ✓ " if r['dxstit'] else "   "
        but = " ✓ " if r['but'] else "   "
        ness = " ✓ " if r['ness'] else "   "

        print(f"| {agent_display:14} | {pres} | {sres} | {res} | {dxstit:6} | {but} | {ness} |")

    # Add legend
    if action_legend:
        print("\nNote: BUT/NESS evaluated for actions:", end=" ")
        legend_parts = []
        for ag, act in sorted(action_legend.items()):
            legend_parts.append(f"agent {ag} → {act}")
        print(", ".join(legend_parts))

    print("\n" + "="*70)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze OWL file and produce responsibility results table",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This is a standalone script requiring only:
  - Python 3.7+
  - Konclude reasoner (download from konclude.com)

No other dependencies needed!
        """
    )

    parser.add_argument("owl_file", type=Path, help="Path to OWL file")
    parser.add_argument("--konclude", type=str, default="Konclude",
                       help="Path to Konclude binary (default: search in PATH)")
    parser.add_argument("--timeout", type=int, default=300,
                       help="Konclude timeout in seconds (default: 300)")
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Verbose output")

    args = parser.parse_args()

    # Check OWL file exists
    if not args.owl_file.exists():
        print(f"ERROR: OWL file not found: {args.owl_file}", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing: {args.owl_file}")
    print(f"File size: {args.owl_file.stat().st_size:,} bytes")

    # Extract queries from OWL file
    all_queries = extract_queries_from_owl(args.owl_file)
    print(f"Found {len(all_queries)} responsibility queries")

    if args.verbose:
        print("\nQueries:", sorted(all_queries))

    # Run Konclude
    print(f"\nRunning Konclude (timeout: {args.timeout}s)...")
    try:
        individual_types = run_konclude(
            args.owl_file,
            konclude_path=args.konclude,
            timeout=args.timeout,
            verbose=args.verbose
        )

        # Extract satisfied queries for evaluation point m_h1
        eval_individual = "m_h1"
        if eval_individual not in individual_types:
            print(f"\nWARNING: Evaluation point '{eval_individual}' not found in results",
                  file=sys.stderr)
            print("Available individuals:", list(individual_types.keys())[:10], file=sys.stderr)

        satisfied_queries = individual_types.get(eval_individual, set())
        satisfied_queries = {q for q in satisfied_queries if q in all_queries}

        print(f"Analysis complete: {len(satisfied_queries)}/{len(all_queries)} queries satisfied")

        # Format and display results
        format_results_table(satisfied_queries, all_queries)

    except FileNotFoundError:
        print(f"\nERROR: Konclude not found: {args.konclude}", file=sys.stderr)
        print("Please install Konclude or specify path with --konclude", file=sys.stderr)
        print("Download from: https://www.konclude.com/", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"\nERROR: Konclude timed out after {args.timeout} seconds", file=sys.stderr)
        print("Try increasing timeout with --timeout SECONDS", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: Analysis failed: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
