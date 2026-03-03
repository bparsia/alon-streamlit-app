#!/usr/bin/env python3
"""
Command-line interface for ALOn model translator.

Translates TOML model specifications to various target formalisms.
"""

import argparse
import sys
from pathlib import Path

from .parsers import parse_toml_file
from .parsers.builder import parse_queries
from .serializers import OWLIndexNewExpanderSerializer, EquivFullCardinalityStrategy


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Translate ALOn models from TOML to target formalisms",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate OWL (index-based with full cardinality strategy)
  %(prog)s theories/3.1.toml -o output.owl

  # Print to stdout instead of saving to file
  %(prog)s theories/3.1.toml

  # Verbose output with model statistics
  %(prog)s theories/3.1.toml -o output.owl -v
"""
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input TOML file containing ALOn model specification"
    )

    parser.add_argument(
        "-f", "--format",
        choices=["owl"],
        default="owl",
        help="Target output format (default: owl)"
    )

    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output file path (prints to stdout if not specified)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print detailed information about the model"
    )

    args = parser.parse_args()

    # Validate input file exists
    if not args.input.exists():
        print(f"Error: Input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    if not args.input.is_file():
        print(f"Error: '{args.input}' is not a file", file=sys.stderr)
        sys.exit(1)

    try:
        # Load model
        if args.verbose:
            print(f"Loading model from {args.input}...", file=sys.stderr)

        model = parse_toml_file(str(args.input))
        model = parse_queries(model)

        if args.verbose:
            print(f"✓ Loaded model successfully", file=sys.stderr)
            print(f"  - Actions: {len(model.get_all_actions())}", file=sys.stderr)
            print(f"  - Propositions: {len(model.get_all_propositions())}", file=sys.stderr)
            print(f"  - Opposings: {len(model.opposings)}", file=sys.stderr)
            print(f"  - Histories: {len(model.named_histories)}", file=sys.stderr)
            print(f"  - Results: {len(model.results)}", file=sys.stderr)
            print(f"  - Queries: {len(model.queries)}", file=sys.stderr)
            print(f"  - Complete group actions: {len(model.generate_complete_group_actions())}", file=sys.stderr)

        # Create appropriate serializer
        if args.format == "owl":
            if args.verbose:
                print(f"\nGenerating OWL (index-based, full cardinality strategy)...", file=sys.stderr)
            serializer = OWLIndexNewExpanderSerializer(model, strategy=EquivFullCardinalityStrategy())
        else:
            print(f"Error: Unknown format '{args.format}'", file=sys.stderr)
            sys.exit(1)

        # Serialize
        output = serializer.serialize()

        if args.verbose:
            print(f"✓ Generated {len(output)} characters of OWL/XML", file=sys.stderr)

        # Write output
        if args.output:
            if args.verbose:
                print(f"\nSaving to {args.output}...", file=sys.stderr)

            # Create parent directories if needed
            args.output.parent.mkdir(parents=True, exist_ok=True)

            with open(args.output, 'w') as f:
                f.write(output)

            if args.verbose:
                print(f"✓ Saved successfully", file=sys.stderr)
        else:
            # Print to stdout
            print(output)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error parsing model: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
