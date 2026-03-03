"""Base reasoner adapter interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set


class ReasoningMode(Enum):
    """Reasoning task modes."""
    REALISATION = "realisation"
    CLASSIFICATION = "classification"
    ENTAILMENT = "entailment"


@dataclass
class ReasoningResult:
    """Results from a reasoning task.

    Attributes:
        individual_types: Map from individual names to sets of class names
        wall_clock_time: Wall clock time in seconds
        reasoner_time: Reasoner-reported time in seconds (if available)
        raw_output: Raw output from reasoner
        success: Whether reasoning succeeded
        error_message: Error message if reasoning failed
    """
    individual_types: Dict[str, Set[str]]
    wall_clock_time: float
    reasoner_time: Optional[float] = None
    raw_output: str = ""
    success: bool = True
    error_message: Optional[str] = None


class ReasonerAdapter(ABC):
    """Abstract base class for reasoner adapters.

    Each adapter wraps a specific OWL reasoner and handles:
    - Command-line invocation or API calls
    - Parsing reasoner-specific output formats
    - Normalizing results to common format
    - Capturing timing measurements
    """

    def __init__(self, reasoner_path: Path):
        """Initialize adapter with path to reasoner executable.

        Args:
            reasoner_path: Path to reasoner binary or script
        """
        self.reasoner_path = reasoner_path

    @abstractmethod
    def run(
        self,
        ontology_file: Path,
        mode: ReasoningMode,
        timeout: Optional[int] = None
    ) -> ReasoningResult:
        """Run reasoner on ontology file.

        Args:
            ontology_file: Path to OWL ontology file
            mode: Reasoning mode to use
            timeout: Optional timeout in seconds

        Returns:
            ReasoningResult with normalized results and measurements
        """
        pass

    @abstractmethod
    def supports_mode(self, mode: ReasoningMode) -> bool:
        """Check if this reasoner supports the given mode.

        Args:
            mode: Reasoning mode to check

        Returns:
            True if mode is supported
        """
        pass

    @abstractmethod
    def parse_output(self, raw_output: str, mode: ReasoningMode) -> Dict[str, Set[str]]:
        """Parse reasoner-specific output to normalized format.

        Args:
            raw_output: Raw output from reasoner
            mode: Reasoning mode that was used

        Returns:
            Map from individual names to sets of class names
        """
        pass

    def validate_reasoner_path(self) -> bool:
        """Validate that reasoner executable exists and is executable.

        Returns:
            True if reasoner path is valid
        """
        return self.reasoner_path.exists() and self.reasoner_path.is_file()
