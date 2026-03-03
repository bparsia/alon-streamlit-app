"""Configuration system for reasoner adapters."""

try:
    import tomllib as tomli  # Python 3.11+
except ImportError:
    import tomli  # Fallback for older Python
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .base import ReasoningMode
from .konclude import KoncludeAdapter
from .openllet import OpenlletAdapter


@dataclass
class ReasonerConfig:
    """Configuration for a reasoner.

    Attributes:
        name: Reasoner name (e.g., 'konclude', 'openllet')
        path: Path to reasoner executable
        type: Reasoner type (e.g., 'command-line', 'api')
    """
    name: str
    path: Path
    type: str


@dataclass
class Configuration:
    """Complete configuration for reasoner/translation/invocation.

    Attributes:
        name: Configuration name
        reasoner: Reasoner to use
        translation: Translation type (e.g., 'owl-abox', 'owl-nominal')
        invocation: Invocation mode (e.g., 'realisation', 'classification')
    """
    name: str
    reasoner: str
    translation: str
    invocation: str


class ConfigLoader:
    """Loads and manages reasoner configurations from TOML files."""

    def __init__(self, config_path: Path):
        """Initialize config loader.

        Args:
            config_path: Path to TOML configuration file
        """
        self.config_path = config_path
        self.reasoners: Dict[str, ReasonerConfig] = {}
        self.configurations: Dict[str, Configuration] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from TOML file."""
        with open(self.config_path, 'rb') as f:
            config_data = tomli.load(f)

        # Load reasoner configurations
        if 'reasoners' in config_data:
            for name, reasoner_data in config_data['reasoners'].items():
                self.reasoners[name] = ReasonerConfig(
                    name=name,
                    path=Path(reasoner_data['path']),
                    type=reasoner_data.get('type', 'command-line')
                )

        # Load configurations (reasoner/translation/invocation combinations)
        if 'configurations' in config_data:
            for name, config_data_item in config_data['configurations'].items():
                self.configurations[name] = Configuration(
                    name=name,
                    reasoner=config_data_item['reasoner'],
                    translation=config_data_item['translation'],
                    invocation=config_data_item['invocation']
                )

    def get_reasoner_config(self, name: str) -> Optional[ReasonerConfig]:
        """Get reasoner configuration by name.

        Args:
            name: Reasoner name

        Returns:
            ReasonerConfig if found, None otherwise
        """
        return self.reasoners.get(name)

    def get_configuration(self, name: str) -> Optional[Configuration]:
        """Get configuration by name.

        Args:
            name: Configuration name

        Returns:
            Configuration if found, None otherwise
        """
        return self.configurations.get(name)

    def list_reasoners(self) -> list[str]:
        """List all available reasoner names."""
        return list(self.reasoners.keys())

    def list_configurations(self) -> list[str]:
        """List all available configuration names."""
        return list(self.configurations.keys())

    def create_adapter(self, reasoner_name: str):
        """Create a reasoner adapter instance.

        Args:
            reasoner_name: Name of reasoner to create adapter for

        Returns:
            ReasonerAdapter instance

        Raises:
            ValueError: If reasoner name is not found or type is unsupported
        """
        reasoner_config = self.get_reasoner_config(reasoner_name)
        if not reasoner_config:
            raise ValueError(f"Reasoner '{reasoner_name}' not found in configuration")

        # Create appropriate adapter based on reasoner name
        if reasoner_name.lower() == 'konclude':
            return KoncludeAdapter(reasoner_config.path)
        elif reasoner_name.lower() == 'openllet':
            return OpenlletAdapter(reasoner_config.path)
        else:
            raise ValueError(f"Unsupported reasoner: {reasoner_name}")

    @staticmethod
    def is_compatible(translation: str, invocation: str) -> bool:
        """Check if translation and invocation mode are compatible.

        Args:
            translation: Translation type (e.g., 'owl-abox', 'owl-nominal')
            invocation: Invocation mode (e.g., 'realisation', 'classification')

        Returns:
            True if compatible, False otherwise
        """
        # Pure ABox requires realisation (classification may not include it)
        if 'abox' in translation.lower() and invocation == 'classification':
            return False

        # Nominal class can use either realisation or classification
        if 'nominal' in translation.lower():
            return invocation in {'realisation', 'classification'}

        # Entailment-based doesn't need realisation or classification
        if 'entailment' in translation.lower():
            return invocation == 'entailment'

        return True


def load_config(config_path: Optional[Path] = None) -> ConfigLoader:
    """Load reasoner configuration from TOML file.

    Args:
        config_path: Path to config file. If None, looks for 'reasoner_config.toml'
                     in current directory.

    Returns:
        ConfigLoader instance
    """
    if config_path is None:
        config_path = Path('reasoner_config.toml')

    return ConfigLoader(config_path)
