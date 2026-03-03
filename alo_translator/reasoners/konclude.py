"""Konclude reasoner adapter."""

import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional, Set

from .base import ReasonerAdapter, ReasoningMode, ReasoningResult


class KoncludeAdapter(ReasonerAdapter):
    """Adapter for Konclude command-line reasoner.

    Supports realisation and classification modes.
    Parses Konclude's XML output format.
    """

    def supports_mode(self, mode: ReasoningMode) -> bool:
        """Konclude supports realisation and classification."""
        return mode in {ReasoningMode.REALISATION, ReasoningMode.CLASSIFICATION}

    def run(
        self,
        ontology_file: Path,
        mode: ReasoningMode,
        timeout: Optional[int] = None,
        verbose: bool = False
    ) -> ReasoningResult:
        """Run Konclude on ontology file.

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
                error_message=f"Konclude does not support mode: {mode}"
            )

        # Build command with output file
        # Create temp file for output
        output_fd, output_file = tempfile.mkstemp(suffix='.xml', prefix='konclude_')
        output_path = Path(output_file)

        try:
            cmd = [str(self.reasoner_path)]
            if mode == ReasoningMode.REALISATION:
                cmd.append("realize")
            elif mode == ReasoningMode.CLASSIFICATION:
                cmd.append("classification")

            cmd.extend(["-i", str(ontology_file), "-o", str(output_path)])

            # Capture timing
            start_time = time.time()

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            wall_clock_time = time.time() - start_time

            if result.returncode != 0:
                return ReasoningResult(
                    individual_types={},
                    wall_clock_time=wall_clock_time,
                    raw_output=result.stderr,
                    success=False,
                    error_message=f"Konclude exited with code {result.returncode}"
                )

            # Read output file
            if not output_path.exists():
                return ReasoningResult(
                    individual_types={},
                    wall_clock_time=wall_clock_time,
                    raw_output=result.stdout,
                    success=False,
                    error_message="Konclude did not create output file"
                )

            with open(output_path, 'r') as f:
                output_content = f.read()

            # Debug: Save raw output for inspection
            debug_output_path = Path(f"/tmp/konclude_debug_{ontology_file.stem}.xml")
            try:
                with open(debug_output_path, 'w') as debug_f:
                    debug_f.write(output_content)
                if verbose:
                    print(f"  [DEBUG] Konclude raw output saved to: {debug_output_path}")
            except:
                pass

            # Check for inconsistency in stdout
            if "is inconsistent" in result.stdout.lower():
                return ReasoningResult(
                    individual_types={},
                    wall_clock_time=wall_clock_time,
                    raw_output=output_content,
                    success=False,
                    error_message="Ontology is inconsistent"
                )

            # Check for inconsistency in XML output (individuals asserted as owl:Nothing)
            if "owl#Nothing" in output_content or "owl:Nothing" in output_content:
                return ReasoningResult(
                    individual_types={},
                    wall_clock_time=wall_clock_time,
                    raw_output=output_content,
                    success=False,
                    error_message="Ontology is inconsistent (all individuals are owl:Nothing)"
                )

            # Parse output
            individual_types = self.parse_output(output_content, mode)

            # Try to extract reasoner time from output
            reasoner_time = self._extract_reasoner_time(result.stdout)

            return ReasoningResult(
                individual_types=individual_types,
                wall_clock_time=wall_clock_time,
                reasoner_time=reasoner_time,
                raw_output=output_content,
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
                error_message=f"Error running Konclude: {str(e)}"
            )
        finally:
            # Clean up temp file
            import os as os_module
            try:
                os_module.close(output_fd)
                if output_path.exists():
                    output_path.unlink()
            except:
                pass

    def parse_output(self, raw_output: str, mode: ReasoningMode) -> Dict[str, Set[str]]:
        """Parse Konclude XML output.

        Args:
            raw_output: Raw XML output from Konclude
            mode: Reasoning mode used

        Returns:
            Map from individual names to sets of class names
        """
        individual_types: Dict[str, Set[str]] = {}

        try:
            # Parse XML
            root = ET.fromstring(raw_output)

            # Define namespaces - handle both prefixed and default namespace
            owl_ns = "http://www.w3.org/2002/07/owl#"
            ns = {'owl': owl_ns}

            # Find realisation results (format depends on mode)
            if mode == ReasoningMode.REALISATION:
                # Look for individual-class relationships
                # Konclude XML format has ClassAssertion elements with child elements
                # Handle both prefixed (owl:ClassAssertion) and default namespace ({ns}ClassAssertion)
                assertions = root.findall(".//owl:ClassAssertion", ns)
                if not assertions:
                    # Try default namespace format
                    assertions = root.findall(".//{%s}ClassAssertion" % owl_ns)

                for assertion in assertions:
                    # Try prefixed first, then default namespace
                    class_elem = assertion.find("owl:Class", ns)
                    if class_elem is None:
                        class_elem = assertion.find("{%s}Class" % owl_ns)

                    individual_elem = assertion.find("owl:NamedIndividual", ns)
                    if individual_elem is None:
                        individual_elem = assertion.find("{%s}NamedIndividual" % owl_ns)

                    if class_elem is not None and individual_elem is not None:
                        # Try to get IRI from either attribute or text content
                        class_iri = class_elem.get("IRI") or class_elem.get("abbreviatedIRI") or ""
                        individual_iri = individual_elem.get("IRI") or individual_elem.get("abbreviatedIRI") or ""

                        if not class_iri or not individual_iri:
                            continue

                        # Extract simple names from IRIs
                        class_name = self._extract_name_from_iri(class_iri)
                        individual_name = self._extract_name_from_iri(individual_iri)

                        # Skip owl:Thing assertions (usually not interesting)
                        if class_name == "Thing" or "owl#Thing" in class_iri:
                            continue

                        if individual_name not in individual_types:
                            individual_types[individual_name] = set()
                        individual_types[individual_name].add(class_name)

            elif mode == ReasoningMode.CLASSIFICATION:
                # Classification gives us class hierarchy, not instance types
                # We might need different parsing logic here
                pass

        except ET.ParseError as e:
            # If XML parsing fails, try to extract info from text format
            # (Konclude sometimes outputs non-XML format)
            individual_types = self._parse_text_format(raw_output)

        return individual_types

    def _extract_name_from_iri(self, iri: str) -> str:
        """Extract simple name from IRI.

        Args:
            iri: Full IRI or abbreviated IRI

        Returns:
            Simple name (fragment or last path component)
        """
        # Handle abbreviated IRIs (prefix:name)
        if ":" in iri and not iri.startswith("http"):
            return iri.split(":")[-1]

        # Handle full IRIs
        if "#" in iri:
            return iri.split("#")[-1]
        elif "/" in iri:
            return iri.split("/")[-1]

        return iri

    def _parse_text_format(self, output: str) -> Dict[str, Set[str]]:
        """Parse Konclude text output format (fallback).

        Args:
            output: Raw text output

        Returns:
            Map from individual names to sets of class names
        """
        individual_types: Dict[str, Set[str]] = {}

        # Look for patterns like "individual_name : class_name"
        # This is a simplified parser - may need refinement based on actual output
        for line in output.splitlines():
            # Pattern: individual is member of class
            match = re.search(r'(\w+)\s+(?:is|:)\s+(?:member of|type)\s+(\w+)', line, re.IGNORECASE)
            if match:
                individual_name = match.group(1)
                class_name = match.group(2)
                if individual_name not in individual_types:
                    individual_types[individual_name] = set()
                individual_types[individual_name].add(class_name)

        return individual_types

    def _extract_reasoner_time(self, output: str) -> Optional[float]:
        """Extract reasoner-reported time from output.

        Args:
            output: Raw output from Konclude

        Returns:
            Reasoner time in seconds if found, None otherwise
        """
        # Look for time patterns in output
        # Konclude may report time in various formats
        time_patterns = [
            r'Time:\s+([\d.]+)\s*(?:s|sec|seconds?)',
            r'Reasoning time:\s+([\d.]+)\s*(?:s|sec|seconds?)',
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
