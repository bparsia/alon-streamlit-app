"""Experiment runner with measurement collection."""

import csv
import hashlib
import json
import platform
import shutil
import sys
import time
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..reasoners import ConfigLoader, ReasoningMode
from .manifest import ExperimentSpec, ExperimentManifest
from .correctness import CorrectnessChecker


@dataclass
class ExperimentResult:
    """Results from running a single experiment.

    Attributes:
        name: Experiment name
        input_file: Input file path
        reasoner: Reasoner used
        translation: Translation type
        invocation: Invocation mode
        success: Whether experiment succeeded
        wall_clock_time: Wall clock time in seconds
        reasoner_time: Reasoner-reported time (if available)
        num_individuals: Number of individuals in results
        num_classes: Number of classes assigned
        error_message: Error message if failed
        correctness_checks: Optional correctness validation results
    """
    name: str
    input_file: str
    reasoner: str
    translation: str
    invocation: str
    success: bool
    wall_clock_time: float
    reasoner_time: Optional[float] = None
    num_individuals: int = 0
    num_classes: int = 0
    error_message: Optional[str] = None
    correctness_checks: Optional[Dict[str, bool]] = None


class ExperimentRunner:
    """Runs experiments and collects measurements.

    This runner executes a series of experiments (from manifest or CSV)
    and collects comprehensive measurements including timing and correctness.
    """

    def __init__(self, config_loader: ConfigLoader, output_dir: Optional[Path] = None):
        """Initialize experiment runner.

        Args:
            config_loader: ConfigLoader with reasoner configurations
            output_dir: Optional directory for output files
        """
        self.config_loader = config_loader
        self.output_dir = output_dir or Path('.')
        self.results: List[ExperimentResult] = []

    @staticmethod
    def _compute_file_checksum(file_path: Path) -> str:
        """Compute SHA256 checksum of a file.

        Args:
            file_path: Path to file

        Returns:
            Hex digest of SHA256 checksum
        """
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _gather_system_info() -> Dict[str, str]:
        """Gather system information for reproducibility.

        Returns:
            Dictionary of system information
        """
        try:
            import psutil
            cpu_count = psutil.cpu_count(logical=True)
            memory_gb = round(psutil.virtual_memory().total / (1024**3), 2)
            load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
        except ImportError:
            cpu_count = "N/A (psutil not installed)"
            memory_gb = "N/A (psutil not installed)"
            load_avg = None

        info = {
            'timestamp': datetime.now().isoformat(),
            'hostname': platform.node(),
            'os': f"{platform.system()} {platform.release()}",
            'os_version': platform.version(),
            'architecture': platform.machine(),
            'processor': platform.processor(),
            'python_version': sys.version,
            'python_implementation': platform.python_implementation(),
            'cpu_count': str(cpu_count),
            'memory_gb': str(memory_gb),
        }

        if load_avg:
            info['load_average_1m'] = f"{load_avg[0]:.2f}"
            info['load_average_5m'] = f"{load_avg[1]:.2f}"
            info['load_average_15m'] = f"{load_avg[2]:.2f}"

        return info

    @staticmethod
    def create_experiment_directory(
        base_dir: Path,
        experiment_name: str,
        manifest: ExperimentManifest,
        manifest_path: Path,
        config_path: Path
    ) -> Path:
        """Create a structured, self-contained experiment directory.

        Creates directory structure:
        ```
        <experiment_name>_<timestamp>/
        ├── README.md              # Experiment documentation
        ├── SYSTEM_INFO.txt        # System/environment information
        ├── manifest.toml          # Copy of original manifest
        ├── reasoner_config.toml   # Copy of reasoner config
        ├── inputs/                # Copied input files (not symlinks)
        │   └── checksums.txt      # SHA256 checksums of inputs
        ├── generated/             # Compiled experiment plan
        │   ├── experiment_plan.csv
        │   ├── incompatible.txt
        │   └── GENERATION_INFO.txt
        └── results/               # Experiment results
            ├── results.csv
            ├── summary.txt
            ├── RUN_INFO.txt       # Execution metadata
            └── logs/              # Individual experiment logs
        ```

        Args:
            base_dir: Base directory for experiments
            experiment_name: Name for this experiment run
            manifest: Loaded experiment manifest
            manifest_path: Path to original manifest file
            config_path: Path to reasoner config file

        Returns:
            Path to created experiment directory
        """
        # Create timestamped directory
        creation_time = datetime.now()
        timestamp = creation_time.strftime("%Y%m%d_%H%M%S")
        exp_dir = base_dir / f"{experiment_name}_{timestamp}"
        exp_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (exp_dir / "inputs").mkdir()
        (exp_dir / "generated").mkdir()
        (exp_dir / "results" / "logs").mkdir(parents=True)

        # Copy manifest and config
        shutil.copy2(manifest_path, exp_dir / "manifest.toml")
        shutil.copy2(config_path, exp_dir / "reasoner_config.toml")

        # Gather and save system information
        system_info = ExperimentRunner._gather_system_info()
        system_info_content = f"""# System Information

**Experiment Created:** {creation_time.strftime("%Y-%m-%d %H:%M:%S")}

## Hardware

- **Hostname:** {system_info['hostname']}
- **Architecture:** {system_info['architecture']}
- **Processor:** {system_info['processor']}
- **CPU Count:** {system_info['cpu_count']}
- **Memory:** {system_info['memory_gb']} GB

## Operating System

- **OS:** {system_info['os']}
- **Version:** {system_info['os_version']}

## Python Environment

- **Python Version:** {system_info['python_version'].splitlines()[0]}
- **Implementation:** {system_info['python_implementation']}

## System Load (at creation)

"""
        if 'load_average_1m' in system_info:
            system_info_content += f"""- **1 minute:** {system_info['load_average_1m']}
- **5 minute:** {system_info['load_average_5m']}
- **15 minute:** {system_info['load_average_15m']}
"""
        else:
            system_info_content += "- Load average not available on this platform\n"

        (exp_dir / "SYSTEM_INFO.txt").write_text(system_info_content)

        # Save system info as JSON for programmatic access
        system_info_json = system_info.copy()
        system_info_json['creation_time'] = creation_time.isoformat()
        with open(exp_dir / "system_info.json", 'w') as f:
            json.dump(system_info_json, f, indent=2)

        # Save generation metadata
        generation_info = f"""# Experiment Generation Information

**Generated:** {creation_time.isoformat()}
**Manifest:** {manifest_path.absolute()}
**Config:** {config_path.absolute()}

## Generation Details

- Total experiments compiled: {len(manifest.experiments)}
- Reasoners: {', '.join(manifest.reasoners)}
- Translations: {', '.join(manifest.translations)}
- Invocations: {', '.join(manifest.invocations)}
- Timeout: {manifest.timeout}s
"""
        (exp_dir / "generated" / "GENERATION_INFO.txt").write_text(generation_info)

        # Save generation info as JSON for programmatic access
        generation_info_json = {
            'generated_at': creation_time.isoformat(),
            'manifest_path': str(manifest_path.absolute()),
            'config_path': str(config_path.absolute()),
            'manifest_name': manifest.name,
            'total_experiments': len(manifest.experiments),
            'reasoners': manifest.reasoners,
            'translations': manifest.translations,
            'invocations': manifest.invocations,
            'timeout': manifest.timeout,
            'measurements': manifest.measurements
        }
        with open(exp_dir / "generated" / "generation_info.json", 'w') as f:
            json.dump(generation_info_json, f, indent=2)

        # Create README
        readme_content = f"""# Experiment: {manifest.name}

**Created:** {creation_time.strftime("%Y-%m-%d %H:%M:%S")}
**Experiment ID:** {exp_dir.name}

## Overview

This directory contains a **complete, self-contained, reproducible** experiment for ALOn reasoner testing.
All input files, configurations, and metadata are included. This directory can be zipped and shared.

## Directory Structure

```
{exp_dir.name}/
├── README.md              # This file
├── SYSTEM_INFO.txt        # Hardware/OS/Python environment details
├── manifest.toml          # Original experiment specification
├── reasoner_config.toml   # Reasoner configuration
├── inputs/                # Input OWL files (copied, not symlinked)
│   └── checksums.txt      # SHA256 checksums for verification
├── generated/             # Compiled experiment plan
│   ├── experiment_plan.csv        # Full test matrix
│   ├── incompatible.txt           # Excluded combinations
│   └── GENERATION_INFO.txt        # Generation metadata
└── results/               # Experiment execution results
    ├── results.csv        # Detailed per-experiment results
    ├── summary.txt        # Summary statistics
    ├── RUN_INFO.txt       # Execution timing and system state
    └── logs/              # Individual experiment logs (if enabled)
```

## Reproduction

This experiment is fully self-contained. To reproduce:

```bash
# Extract if zipped
unzip {exp_dir.name}.zip
cd {exp_dir.name}

# Verify input file integrity
sha256sum -c inputs/checksums.txt

# Re-run experiments (uses included manifest and config)
../../alo_run_experiments.py manifest.toml -c reasoner_config.toml -o results_new/
```

## Configuration Summary

- **Reasoners:** {', '.join(manifest.reasoners)}
- **Translations:** {', '.join(manifest.translations)}
- **Invocations:** {', '.join(manifest.invocations)}
- **Default Timeout:** {manifest.timeout}s
- **Measurements:** {', '.join(manifest.measurements)}

## Experiment Scale

- **Total experiments:** {len(manifest.experiments)}
- **Unique input files:** {len(set(exp.input_file for exp in manifest.experiments))}
- **Reasoner/translation/invocation combinations:** {len(manifest.reasoners) * len(manifest.translations) * len(manifest.invocations)} (before compatibility filtering)

## Files

See `SYSTEM_INFO.txt` for complete hardware and environment details.
See `generated/GENERATION_INFO.txt` for experiment compilation details.
See `results/RUN_INFO.txt` (after execution) for execution timing and system state.
"""
        (exp_dir / "README.md").write_text(readme_content)

        print(f"Created experiment directory: {exp_dir}")
        return exp_dir

    def _ensure_owl_file(self, spec: ExperimentSpec) -> bool:
        """Ensure OWL file exists, generating it from TOML if needed.

        Args:
            spec: Experiment specification with source_toml

        Returns:
            True if OWL file exists or was successfully generated, False otherwise
        """
        import subprocess
        import sys

        owl_path = Path(spec.input_file)

        # CACHING DISABLED: Always regenerate OWL files from scratch
        # This ensures experiments run "soup to nuts" with fresh translations
        # Old caching logic only checked TOML timestamp, not translator code changes
        # If caching is needed in future, add a --use-cache flag

        # Need to generate OWL file
        print(f"  Translating {spec.source_toml} -> {owl_path} (translation: {spec.translation})")

        # Ensure output directory exists
        owl_path.parent.mkdir(parents=True, exist_ok=True)

        # For now, we'll use subprocess to call translate_alo.py
        # In the future, we can refactor to import translation functions directly
        translate_script = Path(__file__).parent.parent.parent.parent / "translate_alo.py"

        if not translate_script.exists():
            print(f"  ERROR: Translation script not found: {translate_script}")
            return False

        try:
            # Call translation script
            result = subprocess.run(
                [sys.executable, str(translate_script), str(spec.source_toml), "-o", str(owl_path)],
                capture_output=True,
                text=True,
                timeout=60  # Translation should be quick
            )

            if result.returncode != 0:
                print(f"  ERROR: Translation failed with code {result.returncode}")
                print(f"  STDERR: {result.stderr}")
                return False

            if not owl_path.exists():
                print(f"  ERROR: Translation completed but OWL file not created")
                return False

            print(f"  ✓ Translation successful: {owl_path}")
            return True

        except subprocess.TimeoutExpired:
            print(f"  ERROR: Translation timed out after 60 seconds")
            return False
        except Exception as e:
            print(f"  ERROR: Translation failed: {e}")
            return False

    def run_experiment(self, spec: ExperimentSpec) -> ExperimentResult:
        """Run a single experiment.

        Args:
            spec: Experiment specification

        Returns:
            ExperimentResult with measurements
        """
        print(f"Running: {spec.name}")

        try:
            # Handle translation if needed
            if spec.source_toml:
                # Need to generate OWL from TOML source
                if not self._ensure_owl_file(spec):
                    raise RuntimeError(f"Failed to generate OWL file from {spec.source_toml}")

            # Verify input file exists
            if not Path(spec.input_file).exists():
                raise FileNotFoundError(f"Input file not found: {spec.input_file}")

            # Create reasoner adapter
            adapter = self.config_loader.create_adapter(spec.reasoner)

            # Map invocation mode
            mode_map = {
                'realisation': ReasoningMode.REALISATION,
                'classification': ReasoningMode.CLASSIFICATION,
                'entailment': ReasoningMode.ENTAILMENT,
            }
            mode = mode_map.get(spec.invocation)
            if mode is None:
                raise ValueError(f"Unknown invocation mode: {spec.invocation}")

            # Run reasoner
            reasoning_result = adapter.run(
                spec.input_file,
                mode,
                timeout=spec.timeout
            )

            # Collect measurements
            num_individuals = len(reasoning_result.individual_types)
            num_classes = sum(
                len(classes) for classes in reasoning_result.individual_types.values()
            )

            # Perform correctness checking if source TOML is available
            correctness_checks = None
            if spec.source_toml and Path(spec.source_toml).exists():
                checker = CorrectnessChecker(
                    theory_toml_path=spec.source_toml,
                    owl_file_path=Path(spec.input_file)
                )
                correctness_checks = checker.check_results(reasoning_result.individual_types)

            result = ExperimentResult(
                name=spec.name,
                input_file=str(spec.input_file),
                reasoner=spec.reasoner,
                translation=spec.translation,
                invocation=spec.invocation,
                success=reasoning_result.success,
                wall_clock_time=reasoning_result.wall_clock_time,
                reasoner_time=reasoning_result.reasoner_time,
                num_individuals=num_individuals,
                num_classes=num_classes,
                error_message=reasoning_result.error_message,
                correctness_checks=correctness_checks
            )

        except Exception as e:
            result = ExperimentResult(
                name=spec.name,
                input_file=str(spec.input_file),
                reasoner=spec.reasoner,
                translation=spec.translation,
                invocation=spec.invocation,
                success=False,
                wall_clock_time=0.0,
                error_message=str(e)
            )

        self.results.append(result)
        return result

    def run_experiments(self, specs: List[ExperimentSpec]) -> List[ExperimentResult]:
        """Run multiple experiments.

        Args:
            specs: List of experiment specifications

        Returns:
            List of experiment results
        """
        print(f"Running {len(specs)} experiments...")
        results = []

        for i, spec in enumerate(specs, 1):
            print(f"\n[{i}/{len(specs)}] ", end='')
            result = self.run_experiment(spec)

            if result.success:
                print(f"  ✓ Success ({result.wall_clock_time:.2f}s)")
            else:
                print(f"  ✗ Failed: {result.error_message}")

            results.append(result)

        return results

    def save_results_csv(self, output_path: Path) -> None:
        """Save experiment results to CSV.

        Args:
            output_path: Path to output CSV file
        """
        if not self.results:
            print("No results to save")
            return

        with open(output_path, 'w', newline='') as f:
            # Get field names from dataclass
            fieldnames = [
                'name', 'input_file', 'reasoner', 'translation', 'invocation',
                'success', 'wall_clock_time', 'reasoner_time',
                'num_individuals', 'num_classes',
                'queries_checked', 'queries_satisfied',
                'error_message'
            ]

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for result in self.results:
                # Calculate correctness summary
                queries_checked = 0
                queries_satisfied = 0
                if result.correctness_checks:
                    queries_checked = len(result.correctness_checks)
                    queries_satisfied = sum(1 for v in result.correctness_checks.values() if v)

                row = {
                    'name': result.name,
                    'input_file': result.input_file,
                    'reasoner': result.reasoner,
                    'translation': result.translation,
                    'invocation': result.invocation,
                    'success': result.success,
                    'wall_clock_time': f"{result.wall_clock_time:.3f}",
                    'reasoner_time': f"{result.reasoner_time:.3f}" if result.reasoner_time else '',
                    'num_individuals': result.num_individuals,
                    'num_classes': result.num_classes,
                    'queries_checked': queries_checked,
                    'queries_satisfied': queries_satisfied,
                    'error_message': result.error_message or ''
                }
                writer.writerow(row)

        print(f"\nResults saved to {output_path}")

    def save_results_json(self, output_path: Path) -> None:
        """Save experiment results to JSON for programmatic access.

        Args:
            output_path: Path to output JSON file
        """
        if not self.results:
            print("No results to save")
            return

        # Convert results to dicts, handling None values
        results_data = []
        for result in self.results:
            result_dict = asdict(result)
            # Keep None values as null in JSON
            results_data.append(result_dict)

        with open(output_path, 'w') as f:
            json.dump(results_data, f, indent=2)

        print(f"Results (JSON) saved to {output_path}")

    def print_summary(self) -> None:
        """Print summary of experiment results."""
        if not self.results:
            print("No results to summarize")
            return

        total = len(self.results)
        successful = sum(1 for r in self.results if r.success)
        failed = total - successful

        print("\n" + "=" * 60)
        print("EXPERIMENT SUMMARY")
        print("=" * 60)
        print(f"Total experiments: {total}")
        print(f"Successful: {successful} ({successful/total*100:.1f}%)")
        print(f"Failed: {failed} ({failed/total*100:.1f}%)")

        if successful > 0:
            avg_time = sum(r.wall_clock_time for r in self.results if r.success) / successful
            print(f"\nAverage time (successful): {avg_time:.2f}s")

            # Group by reasoner
            by_reasoner: Dict[str, List[ExperimentResult]] = {}
            for result in self.results:
                if result.success:
                    if result.reasoner not in by_reasoner:
                        by_reasoner[result.reasoner] = []
                    by_reasoner[result.reasoner].append(result)

            print("\nBy Reasoner:")
            for reasoner, results in by_reasoner.items():
                avg = sum(r.wall_clock_time for r in results) / len(results)
                print(f"  {reasoner}: {len(results)} experiments, avg {avg:.2f}s")

        if failed > 0:
            print("\nFailed Experiments:")
            for result in self.results:
                if not result.success:
                    print(f"  - {result.name}: {result.error_message}")

        print("=" * 60)
