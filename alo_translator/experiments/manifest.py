"""Experiment manifest parsing and compilation."""

try:
    import tomllib as tomli
except ImportError:
    import tomli
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set
import csv
import hashlib
import sys


@dataclass
class ExperimentSpec:
    """Single experiment specification.

    Attributes:
        name: Experiment name (for tracking)
        source_toml: Path to source TOML file (if using integrated translation)
        input_file: Path to input OWL file (generated or pre-existing)
        reasoner: Reasoner name
        translation: Translation type
        invocation: Invocation mode
        timeout: Optional timeout in seconds
    """
    name: str
    input_file: Path
    reasoner: str
    translation: str
    invocation: str
    timeout: Optional[int] = None
    source_toml: Optional[Path] = None


@dataclass
class ExperimentManifest:
    """Experiment manifest specifying what to test.

    The manifest lists inputs, reasoners, translations, and measurements.
    The compiler expands this into a full cross-product of experiments.

    Attributes:
        name: Manifest name
        version: Semantic version (e.g., "1.2.3"), optional
        manifest_checksum: SHA256 checksum of manifest content, optional
        input_dirs: Directories containing input files
        input_patterns: File patterns to match (e.g., "*.owl")
        reasoners: List of reasoner names to test
        translations: List of translation types
        invocations: List of invocation modes
        measurements: List of measurements to capture
        timeout: Default timeout in seconds
        incompatible: List of incompatible combinations
        experiments: Compiled list of individual experiments
    """
    name: str
    version: Optional[str] = None
    manifest_checksum: Optional[str] = None
    input_dirs: List[Path] = field(default_factory=list)
    input_patterns: List[str] = field(default_factory=list)
    reasoners: List[str] = field(default_factory=list)
    translations: List[str] = field(default_factory=list)
    invocations: List[str] = field(default_factory=list)
    measurements: List[str] = field(default_factory=list)
    timeout: int = 300
    incompatible: List[Dict[str, str]] = field(default_factory=list)
    experiments: List[ExperimentSpec] = field(default_factory=list)

    def compile(self) -> List[ExperimentSpec]:
        """Compile manifest into full list of experiments.

        Generates cross-product of all inputs, reasoners, translations,
        and invocations, excluding incompatible combinations.

        Returns:
            List of compiled experiment specifications
        """
        from ..reasoners.config import ConfigLoader

        experiments = []

        # Collect all input files
        input_files = []
        for input_dir in self.input_dirs:
            for pattern in self.input_patterns:
                input_files.extend(input_dir.glob(pattern))

        # Generate cross-product
        for input_file in input_files:
            # Detect if this is a TOML source file or pre-generated OWL
            is_toml_source = input_file.suffix.lower() == '.toml'

            for reasoner in self.reasoners:
                for translation in self.translations:
                    for invocation in self.invocations:
                        # Check if this combination is compatible
                        if not self._is_compatible(reasoner, translation, invocation):
                            continue

                        # Determine owl file path
                        if is_toml_source:
                            # Will be generated: translations/<stem>_<translation>.owl
                            owl_file = Path('translations') / f"{input_file.stem}_{translation}.owl"
                            source_toml = input_file
                        else:
                            # Already exists as OWL
                            owl_file = input_file
                            source_toml = None

                        # Create experiment spec
                        name = f"{input_file.stem}_{reasoner}_{translation}_{invocation}"
                        spec = ExperimentSpec(
                            name=name,
                            input_file=owl_file,
                            reasoner=reasoner,
                            translation=translation,
                            invocation=invocation,
                            timeout=self.timeout,
                            source_toml=source_toml
                        )
                        experiments.append(spec)

        self.experiments = experiments
        return experiments

    def _is_compatible(self, reasoner: str, translation: str, invocation: str) -> bool:
        """Check if reasoner/translation/invocation combination is compatible.

        Args:
            reasoner: Reasoner name
            translation: Translation type
            invocation: Invocation mode

        Returns:
            True if compatible, False otherwise
        """
        from ..reasoners.config import ConfigLoader

        # Check translation-invocation compatibility
        if not ConfigLoader.is_compatible(translation, invocation):
            return False

        # Check explicit incompatible list
        for incomp in self.incompatible:
            if (incomp.get('reasoner') == reasoner and
                incomp.get('translation') == translation and
                incomp.get('invocation') == invocation):
                return False

        return True

    def to_csv(self, output_path: Path) -> None:
        """Write compiled experiments to CSV file.

        Args:
            output_path: Path to output CSV file
        """
        if not self.experiments:
            self.compile()

        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'name', 'input_file', 'reasoner', 'translation',
                'invocation', 'timeout'
            ])
            for exp in self.experiments:
                writer.writerow([
                    exp.name,
                    str(exp.input_file),
                    exp.reasoner,
                    exp.translation,
                    exp.invocation,
                    exp.timeout
                ])

    def write_incompatible(self, output_path: Path) -> None:
        """Write incompatible combinations to file.

        Args:
            output_path: Path to output file
        """
        with open(output_path, 'w') as f:
            f.write("# Incompatible Reasoner/Translation/Invocation Combinations\n\n")

            # Find all incompatible combinations
            incompatible = []
            for reasoner in self.reasoners:
                for translation in self.translations:
                    for invocation in self.invocations:
                        if not self._is_compatible(reasoner, translation, invocation):
                            incompatible.append((reasoner, translation, invocation))

            if incompatible:
                for reasoner, translation, invocation in incompatible:
                    f.write(f"- {reasoner} + {translation} + {invocation}\n")
            else:
                f.write("No incompatible combinations found.\n")


def compute_manifest_checksum(manifest_path: Path, exclude_checksum_line: bool = True) -> str:
    """Compute SHA256 checksum of manifest file.

    Args:
        manifest_path: Path to manifest file
        exclude_checksum_line: If True, exclude the manifest_checksum line itself

    Returns:
        Hex string of SHA256 checksum
    """
    content = manifest_path.read_text()

    if exclude_checksum_line:
        # Remove the manifest_checksum line to avoid circular dependency
        lines = content.splitlines()
        filtered_lines = [
            line for line in lines
            if not line.strip().startswith('manifest_checksum')
        ]
        content = '\n'.join(filtered_lines)

    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _validate_manifest_checksum(manifest_path: Path, expected_checksum: str) -> None:
    """Validate manifest checksum and prompt user if mismatch.

    Args:
        manifest_path: Path to manifest file
        expected_checksum: Expected checksum from manifest

    Raises:
        SystemExit: If user declines to continue with mismatched checksum
    """
    actual_checksum = compute_manifest_checksum(manifest_path, exclude_checksum_line=True)

    if actual_checksum != expected_checksum:
        print(f"\n⚠️  WARNING: Manifest checksum mismatch!")
        print(f"   File: {manifest_path}")
        print(f"   Expected: {expected_checksum}")
        print(f"   Actual:   {actual_checksum}")
        print(f"\nThe manifest has been modified without updating the checksum.")
        print(f"This usually means the version should be bumped.")

        response = input("\nContinue anyway? [y/N]: ").strip().lower()
        if response not in ('y', 'yes'):
            print("Aborted. Please update the manifest version and checksum.")
            sys.exit(1)

        print("Continuing with modified manifest (checksum ignored)...")


def load_manifest(manifest_path: Path) -> ExperimentManifest:
    """Load experiment manifest from TOML file.

    Args:
        manifest_path: Path to manifest TOML file

    Returns:
        Loaded ExperimentManifest

    Example manifest format:
        ```toml
        [manifest]
        name = "ALO 3.1 Tests"
        timeout = 300

        [inputs]
        directories = ["translations/"]
        patterns = ["*_3.1.owl", "*_3.5.owl"]

        [testing]
        reasoners = ["konclude", "openllet"]
        translations = ["owl-abox", "owl-nominal"]
        invocations = ["realisation", "classification"]
        measurements = ["wall_clock_time", "reasoner_time", "correctness"]

        [[incompatible]]
        reasoner = "konclude"
        translation = "owl-abox"
        invocation = "classification"
        ```
    """
    with open(manifest_path, 'rb') as f:
        data = tomli.load(f)

    # Extract manifest metadata
    manifest_data = data.get('manifest', {})
    name = manifest_data.get('name', 'Experiment')
    timeout = manifest_data.get('timeout', 300)
    version = manifest_data.get('version')
    manifest_checksum = manifest_data.get('manifest_checksum')

    # Validate checksum if present
    if manifest_checksum:
        _validate_manifest_checksum(manifest_path, manifest_checksum)

    # Extract inputs
    inputs_data = data.get('inputs', {})
    input_dirs = [Path(d) for d in inputs_data.get('directories', [])]
    input_patterns = inputs_data.get('patterns', ['*.owl'])

    # Extract testing configuration
    testing_data = data.get('testing', {})
    reasoners = testing_data.get('reasoners', [])
    translations = testing_data.get('translations', [])
    invocations = testing_data.get('invocations', [])
    measurements = testing_data.get('measurements', [])

    # Extract incompatible combinations
    incompatible = data.get('incompatible', [])

    manifest = ExperimentManifest(
        name=name,
        version=version,
        manifest_checksum=manifest_checksum,
        input_dirs=input_dirs,
        input_patterns=input_patterns,
        reasoners=reasoners,
        translations=translations,
        invocations=invocations,
        measurements=measurements,
        timeout=timeout,
        incompatible=incompatible
    )

    return manifest
