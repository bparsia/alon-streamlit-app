"""HermiT reasoner adapter, via ROBOT.

HermiT has no CLI for individual/instance retrieval (only classification,
consistency, and subsumption via its own jar) -- ROBOT wraps the OWL API
and provides `reason` (run a reasoner, materialize inferred axioms) and
`convert` (change serialization format), chainable in one invocation.
"""

import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional, Set

from .base import ReasonerAdapter, ReasoningMode, ReasoningResult


class HermitAdapter(ReasonerAdapter):
    """Adapter for HermiT via ROBOT's `reason` + `convert` chain.

    Supports realisation only. Output is real OWL/XML (via `convert
    --format owx`), parsed the same way as Konclude's OWL/XML output.
    """

    def supports_mode(self, mode: ReasoningMode) -> bool:
        return mode == ReasoningMode.REALISATION

    def run(
        self,
        ontology_file: Path,
        mode: ReasoningMode,
        timeout: Optional[int] = None
    ) -> ReasoningResult:
        """Run HermiT (via ROBOT) on an ontology file.

        Args:
            ontology_file: Path to OWL ontology file
            mode: Reasoning mode (realisation only)
            timeout: Optional timeout in seconds

        Returns:
            ReasoningResult with parsed results and measurements
        """
        if not self.supports_mode(mode):
            return ReasoningResult(
                individual_types={},
                wall_clock_time=0.0,
                success=False,
                error_message=f"HermiT does not support mode: {mode}"
            )

        output_fd, output_file = tempfile.mkstemp(suffix='.owx', prefix='hermit_')
        output_path = Path(output_file)

        try:
            cmd = [
                str(self.reasoner_path), "reason",
                "-r", "HermiT",
                "-i", str(ontology_file),
                "-n", "true",
                "-A", "ClassAssertion",
                "-d", "true",
                "convert",
                "--format", "owx",
                "-o", str(output_path),
            ]

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
                    error_message=f"ROBOT exited with code {result.returncode}"
                )

            if not output_path.exists():
                return ReasoningResult(
                    individual_types={},
                    wall_clock_time=wall_clock_time,
                    raw_output=result.stdout,
                    success=False,
                    error_message="ROBOT did not create output file"
                )

            with open(output_path, 'r') as f:
                output_content = f.read()

            individual_types = self.parse_output(output_content, mode)

            return ReasoningResult(
                individual_types=individual_types,
                wall_clock_time=wall_clock_time,
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
                error_message=f"Error running ROBOT: {str(e)}"
            )
        finally:
            import os as os_module
            try:
                os_module.close(output_fd)
                if output_path.exists():
                    output_path.unlink()
            except Exception:
                pass

    def parse_output(self, raw_output: str, mode: ReasoningMode) -> Dict[str, Set[str]]:
        """Parse ROBOT's OWL/XML (functional-style) output.

        Args:
            raw_output: OWL/XML content from `robot ... convert --format owx`
            mode: Reasoning mode used (realisation only)

        Returns:
            Map from individual names to sets of class names
        """
        individual_types: Dict[str, Set[str]] = {}

        try:
            root = ET.fromstring(raw_output)
            owl_ns = "http://www.w3.org/2002/07/owl#"
            ns = {'owl': owl_ns}

            assertions = root.findall(".//owl:ClassAssertion", ns)
            if not assertions:
                assertions = root.findall(".//{%s}ClassAssertion" % owl_ns)

            for assertion in assertions:
                class_elem = assertion.find("owl:Class", ns)
                if class_elem is None:
                    class_elem = assertion.find("{%s}Class" % owl_ns)

                individual_elem = assertion.find("owl:NamedIndividual", ns)
                if individual_elem is None:
                    individual_elem = assertion.find("{%s}NamedIndividual" % owl_ns)

                if class_elem is None or individual_elem is None:
                    continue

                class_iri = class_elem.get("IRI") or class_elem.get("abbreviatedIRI") or ""
                individual_iri = individual_elem.get("IRI") or individual_elem.get("abbreviatedIRI") or ""
                if not class_iri or not individual_iri:
                    continue

                class_name = self._extract_name_from_iri(class_iri)
                individual_name = self._extract_name_from_iri(individual_iri)

                if class_name == "Thing" or "owl#Thing" in class_iri:
                    continue

                individual_types.setdefault(individual_name, set()).add(class_name)

        except ET.ParseError:
            pass

        return individual_types

    def _extract_name_from_iri(self, iri: str) -> str:
        """Extract simple name from IRI (abbreviated or full)."""
        if ":" in iri and not iri.startswith("http"):
            return iri.split(":")[-1]
        if "#" in iri:
            return iri.split("#")[-1]
        elif "/" in iri:
            return iri.split("/")[-1]
        return iri
