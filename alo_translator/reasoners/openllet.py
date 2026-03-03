"""Openllet reasoner adapter."""

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional, Set

from .base import ReasonerAdapter, ReasoningMode, ReasoningResult


class OpenlletAdapter(ReasonerAdapter):
    """Adapter for Openllet command-line reasoner.

    Supports realisation and classification modes.
    Parses Openllet's indented text output format.
    """

    def supports_mode(self, mode: ReasoningMode) -> bool:
        """Openllet supports realisation and classification."""
        return mode in {ReasoningMode.REALISATION, ReasoningMode.CLASSIFICATION}

    def run(
        self,
        ontology_file: Path,
        mode: ReasoningMode,
        timeout: Optional[int] = None
    ) -> ReasoningResult:
        """Run Openllet on ontology file.

        Args:
            ontology_file: Path to OWL ontology file
            mode: Reasoning mode (realisation or classification)
            timeout: Optional timeout in seconds

        Returns:
            ReasoningResult with parsed results and measurements
        """
        if not self.supports_mode(mode):
            return ReasoningResult(
                individual_types={},
                wall_clock_time=0.0,
                success=False,
                error_message=f"Openllet does not support mode: {mode}"
            )

        # Build command - use script name only since we'll cd to its directory
        reasoner_dir = self.reasoner_path.parent
        script_name = "./" + self.reasoner_path.name

        cmd = [script_name]
        if mode == ReasoningMode.REALISATION:
            cmd.append("realize")
        elif mode == ReasoningMode.CLASSIFICATION:
            cmd.append("classify")

        # Convert ontology path to absolute so it works from reasoner directory
        ontology_abs = ontology_file.resolve()
        cmd.append(str(ontology_abs))

        # Capture timing
        start_time = time.time()

        try:
            # Run from Openllet's directory (it uses relative paths internally)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(reasoner_dir)
            )
            wall_clock_time = time.time() - start_time

            # Note: OpenLlet often returns exit code 1 even on success
            # Check stderr/stdout for actual errors instead of relying on exit code

            # Check for inconsistency
            if "inconsistent" in result.stdout.lower() and "error" in result.stdout.lower():
                return ReasoningResult(
                    individual_types={},
                    wall_clock_time=wall_clock_time,
                    raw_output=result.stdout,
                    success=False,
                    error_message="Ontology is inconsistent"
                )

            # Check for actual errors (not just warnings)
            if result.returncode != 0 and (
                "exception" in result.stderr.lower() or
                "error:" in result.stderr.lower() or
                not result.stdout.strip()  # No output at all is a real error
            ):
                return ReasoningResult(
                    individual_types={},
                    wall_clock_time=wall_clock_time,
                    raw_output=result.stderr or result.stdout,
                    success=False,
                    error_message=f"Openllet failed: {result.stderr[:200]}"
                )

            # Debug: Save raw output for inspection
            debug_output_path = Path(f"/tmp/openllet_debug_{ontology_file.stem}.txt")
            try:
                with open(debug_output_path, 'w') as debug_f:
                    debug_f.write(result.stdout)
                print(f"  [DEBUG] OpenLlet raw output saved to: {debug_output_path}")
            except:
                pass

            # Parse output
            individual_types = self.parse_output(result.stdout, mode)

            # Try to extract reasoner time from output
            reasoner_time = self._extract_reasoner_time(result.stdout)

            return ReasoningResult(
                individual_types=individual_types,
                wall_clock_time=wall_clock_time,
                reasoner_time=reasoner_time,
                raw_output=result.stdout,
                success=True
            )

        except subprocess.TimeoutExpired:
            wall_clock_time = time.time() - start_time
            return ReasoningResult(
                individual_types={},
                wall_clock_time=wall_clock_time,
                success=False,
                error_message=f"Timeout after {timeout} seconds"
            )
        except Exception as e:
            wall_clock_time = time.time() - start_time
            return ReasoningResult(
                individual_types={},
                wall_clock_time=wall_clock_time,
                success=False,
                error_message=f"Error running Openllet: {str(e)}"
            )

    def parse_output(self, raw_output: str, mode: ReasoningMode) -> Dict[str, Set[str]]:
        """Parse Openllet indented text output.

        Openllet outputs a hierarchical structure with indentation:
        - Classes are shown in hierarchy
        - Instances are shown indented under their most specific classes

        Example format:
            Class: http://example.org#ClassA
              Instance: http://example.org#individual1
              Instance: http://example.org#individual2

        Args:
            raw_output: Raw text output from Openllet
            mode: Reasoning mode used

        Returns:
            Map from individual names to sets of class names
        """
        individual_types: Dict[str, Set[str]] = {}

        if mode == ReasoningMode.REALISATION:
            individual_types = self._parse_realisation_output(raw_output)
        elif mode == ReasoningMode.CLASSIFICATION:
            # Classification output shows class hierarchy, not instances
            # We may not get individual-to-class mappings from pure classification
            pass

        return individual_types

    def _parse_realisation_output(self, output: str) -> Dict[str, Set[str]]:
        """Parse Openllet/Pellet realisation output.

        Format: One class per line with indentation to indicate subclassing
        and parenthetical lists at the end of a line to indicate instances.

        Example:
            ClassA (individual1, individual2)
              SubClassB (individual3)
                SubSubClassC

        Important: Instances are listed with their MOST SPECIFIC class.
        We need to propagate instances up the class hierarchy so queries
        for superclasses also return the correct individuals.

        Args:
            output: Raw realisation output

        Returns:
            Map from individual names to sets of class names (including superclasses)
        """
        # First pass: Parse the hierarchy and direct instances
        class_hierarchy: Dict[str, Set[str]] = {}  # child -> set of ancestors
        direct_instances: Dict[str, Set[str]] = {}  # individual -> {most specific classes}
        class_equivalences: Dict[str, Set[str]] = {}  # class -> set of equivalent classes

        # Track class stack by indentation level
        indent_stack: list = []  # [(indent_level, class_name), ...]

        for line in output.splitlines():
            line_stripped = line.rstrip()
            if not line_stripped.strip():
                continue

            # Calculate indentation (number of leading spaces)
            indent_level = len(line_stripped) - len(line_stripped.lstrip())

            # Look for pattern: ClassName - (instance1, instance2, ...)
            # or: ClassName = EquivalentClass - (instances)
            # or just: ClassName
            # Note: Openllet uses " - " before the instance list and " = " for equivalences
            match = re.match(r'^\s*([^\(\-=]+?)(?:\s*=\s*([^\(\-]+?))?(?:\s*-\s*\(([^\)]+)\))?\s*$', line_stripped)
            if match:
                class_part = match.group(1).strip()
                equivalent_class_part = match.group(2)
                instances_part = match.group(3)

                # Extract class name(s) from IRI
                class_name = self._extract_name_from_iri(class_part)
                equivalent_class_names = []
                if equivalent_class_part:
                    eq_name = self._extract_name_from_iri(equivalent_class_part.strip())
                    equivalent_class_names.append(eq_name)

                    # Track equivalences bidirectionally
                    if class_name not in class_equivalences:
                        class_equivalences[class_name] = set()
                    if eq_name not in class_equivalences:
                        class_equivalences[eq_name] = set()
                    class_equivalences[class_name].add(eq_name)
                    class_equivalences[eq_name].add(class_name)

                # Pop classes from stack that are at same or deeper indentation
                while indent_stack and indent_stack[-1][0] >= indent_level:
                    indent_stack.pop()

                # Current class's parent is the top of the stack (if any)
                # Add hierarchy for primary class and all equivalent classes
                for cls_name in [class_name] + equivalent_class_names:
                    if indent_stack:
                        parent_class = indent_stack[-1][1]
                        if cls_name not in class_hierarchy:
                            class_hierarchy[cls_name] = set()
                        class_hierarchy[cls_name].add(parent_class)

                        # Also add all ancestors of parent
                        if parent_class in class_hierarchy:
                            class_hierarchy[cls_name].update(class_hierarchy[parent_class])

                # Push current class onto stack (use primary class name)
                indent_stack.append((indent_level, class_name))

                # Parse instances for this class and all equivalent classes
                if instances_part:
                    instances = [i.strip() for i in instances_part.split(',')]
                    for instance_iri in instances:
                        if instance_iri:
                            individual_name = self._extract_name_from_iri(instance_iri)
                            if individual_name not in direct_instances:
                                direct_instances[individual_name] = set()
                            # Add to primary class and all equivalent classes
                            for cls_name in [class_name] + equivalent_class_names:
                                direct_instances[individual_name].add(cls_name)

        # Second pass: Propagate instances up the hierarchy and to equivalent classes
        individual_types: Dict[str, Set[str]] = {}

        for individual, most_specific_classes in direct_instances.items():
            individual_types[individual] = set(most_specific_classes)

            # Add all ancestor classes
            for specific_class in most_specific_classes:
                if specific_class in class_hierarchy:
                    individual_types[individual].update(class_hierarchy[specific_class])

            # Add equivalent classes for all classes (including ancestors)
            classes_to_expand = set(individual_types[individual])
            for cls in classes_to_expand:
                if cls in class_equivalences:
                    individual_types[individual].update(class_equivalences[cls])

        return individual_types

    def _extract_name_from_iri(self, iri: str) -> str:
        """Extract simple name from IRI.

        Args:
            iri: Full IRI or abbreviated IRI

        Returns:
            Simple name (fragment or last path component)
        """
        # Remove angle brackets if present
        iri = iri.strip('<>')

        # Handle abbreviated IRIs (prefix:name)
        if ":" in iri and not iri.startswith("http"):
            return iri.split(":")[-1]

        # Handle full IRIs
        if "#" in iri:
            return iri.split("#")[-1]
        elif "/" in iri:
            return iri.split("/")[-1]

        return iri

    def _extract_reasoner_time(self, output: str) -> Optional[float]:
        """Extract reasoner-reported time from output.

        Args:
            output: Raw output from Openllet

        Returns:
            Reasoner time in seconds if found, None otherwise
        """
        # Look for time patterns in output
        time_patterns = [
            r'Time:\s+([\d.]+)\s*(?:s|sec|seconds?)',
            r'Reasoning time:\s+([\d.]+)\s*(?:s|sec|seconds?)',
            r'Classification time:\s+([\d.]+)\s*(?:s|sec|seconds?)',
            r'Realisation time:\s+([\d.]+)\s*(?:s|sec|seconds?)',
            r'(\d+)\s*ms',  # milliseconds
        ]

        for pattern in time_patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                time_value = float(match.group(1))
                # Convert milliseconds to seconds if needed
                if 'ms' in pattern:
                    time_value /= 1000.0
                return time_value

        return None
