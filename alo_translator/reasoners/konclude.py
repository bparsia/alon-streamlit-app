"""Konclude reasoner adapter."""

import re
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
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
        """Konclude supports realisation, classification, and SPARQL."""
        return mode in {ReasoningMode.REALISATION, ReasoningMode.CLASSIFICATION, ReasoningMode.SPARQL}

    def run(
        self,
        ontology_file: Path,
        mode: ReasoningMode,
        timeout: Optional[int] = None,
        verbose: bool = False,
        threads: str = "AUTO",
        sparql_query_file: Optional[Path] = None,
    ) -> ReasoningResult:
        """Run Konclude on ontology file.

        Args:
            ontology_file: Path to OWL ontology file
            mode: Reasoning mode (realisation, classification, or sparql)
            timeout: Optional timeout in seconds
            threads: Value for Konclude's -w flag (number of processing
                threads). Without this flag Konclude defaults to a single
                processing unit regardless of core count. Measured on the
                same 16-history ontology (2026-08-24): "-w AUTO" (11
                processing units on this machine) completed in 71.75s vs.
                600s+ single-threaded. This does NOT explain why the
                single-threaded path itself got slower than its own
                historical baseline (~200-270s) -- that's a separate,
                unresolved question. See project_konclude_performance memory.
            sparql_query_file: Required when mode is SPARQL -- path to a
                .sparql file containing a single SELECT query (Konclude's
                `sparqlfile -s <query_file> -i <ontology_file>` mode).

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
        if mode == ReasoningMode.SPARQL and sparql_query_file is None:
            return ReasoningResult(
                individual_types={},
                wall_clock_time=0.0,
                success=False,
                error_message="sparql_query_file is required for ReasoningMode.SPARQL"
            )

        # Build command with output file
        # Create temp file for output
        output_suffix = '.xml' if mode != ReasoningMode.SPARQL else '.srx'
        output_fd, output_file = tempfile.mkstemp(suffix=output_suffix, prefix='konclude_')
        output_path = Path(output_file)

        try:
            cmd = [str(self.reasoner_path)]
            if mode == ReasoningMode.REALISATION:
                cmd.append("realize")
            elif mode == ReasoningMode.CLASSIFICATION:
                cmd.append("classification")
            elif mode == ReasoningMode.SPARQL:
                cmd.extend(["sparqlfile", "-s", str(sparql_query_file)])

            cmd.extend(["-i", str(ontology_file), "-o", str(output_path)])
            if threads:
                cmd.extend(["-w", threads])

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

            reasoner_time = self._extract_reasoner_time(result.stdout)

            if mode == ReasoningMode.SPARQL:
                # A malformed/degenerate query (see alon_test_suite
                # findings/bug-006) is reported as a Rasqal query-execution
                # error in Konclude's stdout (fixed to be loud, not a
                # silent empty result, per that finding) rather than a
                # nonzero exit code or a stderr message -- check for it
                # explicitly so callers see a real error, not "0 results".
                if "query execution failed" in result.stdout.lower() or \
                   "query parsing and preparation failed" in result.stdout.lower():
                    return ReasoningResult(
                        individual_types={},
                        wall_clock_time=wall_clock_time,
                        raw_output=result.stdout,
                        success=False,
                        error_message="Konclude/Rasqal reported a SPARQL query error -- see raw_output"
                    )
                bound_individuals = self.parse_sparql_output(output_content)
                return ReasoningResult(
                    individual_types={},
                    wall_clock_time=wall_clock_time,
                    reasoner_time=reasoner_time,
                    raw_output=output_content,
                    success=True,
                    bound_individuals=bound_individuals,
                )

            # Parse output
            individual_types = self.parse_output(output_content, mode)

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

    def parse_sparql_output(self, raw_output: str) -> Set[str]:
        """Parse Konclude's SPARQL Results XML Format output.

        Expects a single-variable SELECT query (FormulaToSPARQL's
        BASE_VAR, `?idx0`, is always the sole answer variable -- see
        alo_translator/serializers/sparql.py). Returns the set of bound
        individual names (duplicates from e.g. UNION branches matching
        the same individual collapse naturally into a set, which is what
        every caller actually needs -- membership, not row count).

        Format confirmed empirically against the real fixed
        konclude/rasqal build (2026-09-01): standard SPARQL 1.1 XML
        Results Format,
        <results><result><binding name="..."><uri>...</uri></binding></result>...
        """
        bound: Set[str] = set()
        try:
            root = ET.fromstring(raw_output)
        except ET.ParseError:
            return bound

        ns = {"srx": "http://www.w3.org/2005/sparql-results#"}
        for binding in root.findall(".//srx:binding", ns):
            uri_elem = binding.find("srx:uri", ns)
            if uri_elem is not None and uri_elem.text:
                bound.add(self._extract_name_from_iri(uri_elem.text))
        return bound

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


class KoncludeSparqlServer:
    """Long-lived Konclude `sparqlserver` process: load + classify an
    ontology ONCE, then answer many SPARQL queries against the live
    in-memory reasoner over HTTP.

    Exists because the per-query `KoncludeAdapter.run(mode=SPARQL)` path
    (one `sparqlfile` subprocess per query -- reloads and reclassifies
    the WHOLE ontology from scratch every single call) does not scale
    with query count: measured on the real 3.5.mmd model (90 queries),
    per-subprocess-invocation cost meant the batch did not finish within
    10 minutes, versus 16.65s for the equivalent batch run against a
    single warm `sparqlserver` instance (steady-state per-query latency
    ~3-40ms after the ontology is loaded once) -- and 32.1s for the
    existing OWL/realization path on the same model, so the server-mode
    SPARQL path is faster than realization, not just "not catastrophically
    slower." This is a genuinely different cost model, not a tuning
    knob on the per-query path -- see docs/sparql_serializer.md.

    Usage:
        with KoncludeSparqlServer(reasoner_path, ontology_file) as server:
            bound = server.query(sparql_text)  # -> Set[str] of individual names
    """

    def __init__(self, reasoner_path: Path, ontology_file: Path,
                 threads: str = "AUTO", startup_timeout: float = 60.0):
        self.reasoner_path = reasoner_path
        self.ontology_file = ontology_file
        self.threads = threads
        self.startup_timeout = startup_timeout
        self._process: Optional[subprocess.Popen] = None
        self._port: Optional[int] = None
        self._adapter = KoncludeAdapter(reasoner_path)

    def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("Server already started")

        self._port = self._find_free_port()
        cmd = [
            str(self.reasoner_path), "sparqlserver",
            "-p", str(self._port),
            "-i", str(self.ontology_file),
        ]
        if self.threads:
            cmd.extend(["-w", self.threads])

        self._process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )

        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if self._process.poll() is not None:
                remaining_output = self._process.stdout.read() if self._process.stdout else ""
                raise RuntimeError(
                    f"Konclude sparqlserver exited during startup (code "
                    f"{self._process.returncode}): {remaining_output}"
                )
            # A successful HTTP POST is the real readiness signal (more
            # reliable than scraping stdout for "Listening on port",
            # which races with the socket actually accepting connections).
            # Deliberately NOT an ASK query -- ASK is confirmed unreliable
            # on this Konclude/Rasqal build (alon_test_suite findings
            # bug-001, wrong answers in both directions on the reasoning
            # path) and, separately, was observed to take tens of seconds
            # here during initial server startup on a real 90-query/
            # 16-history workload (3.5.mmd) -- SELECT does not have this
            # problem (confirmed: same workload's steady-state SELECT
            # latency was 3-40ms once warm).
            try:
                self._post(
                    "PREFIX owl: <http://www.w3.org/2002/07/owl#>\n"
                    "SELECT ?s WHERE { ?s a owl:Thing } LIMIT 1"
                )
                return
            except (urllib.error.URLError, ConnectionRefusedError, TimeoutError):
                time.sleep(0.1)

        self.stop()
        raise TimeoutError(
            f"Konclude sparqlserver did not become ready within {self.startup_timeout}s"
        )

    def stop(self) -> None:
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
        self._process = None

    def query(self, sparql_text: str, timeout: float = 120.0) -> Set[str]:
        """Run a single-variable SELECT query, return the set of bound
        individual names (see KoncludeAdapter.parse_sparql_output)."""
        body = self._post(sparql_text, timeout=timeout)
        return self._adapter.parse_sparql_output(body)

    def _post(self, sparql_text: str, timeout: float = 5.0) -> str:
        if self._port is None:
            raise RuntimeError("Server not started")
        req = urllib.request.Request(
            f"http://localhost:{self._port}/sparql",
            data=sparql_text.encode("utf-8"),
            headers={"Content-Type": "application/sparql-query"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

    @staticmethod
    def _find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("localhost", 0))
            return s.getsockname()[1]

    def __enter__(self) -> "KoncludeSparqlServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
