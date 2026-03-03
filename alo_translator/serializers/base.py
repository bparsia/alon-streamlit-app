"""
Base serializer class following visitor pattern.

This module provides the abstract base class for all ALOn model serializers,
following the pattern from examtools/formats/serialisers.py.
"""

from abc import ABC, abstractmethod
from typing import Any
from ..model.core import ALOModel


class Serializer(ABC):
    """
    Abstract base class for ALOn model serializers.

    Subclasses should implement the serialize() method to convert
    ALOModel objects into their target format (OWL, Datalog, etc.)
    """

    def __init__(self, model: ALOModel):
        """
        Initialize serializer with a model.

        Args:
            model: The ALOModel to serialize
        """
        self.model = model

    @abstractmethod
    def serialize(self) -> str:
        """
        Serialize the model to the target format.

        Returns:
            String representation in the target format

        Raises:
            NotImplementedError: If subclass doesn't implement this method
        """
        raise NotImplementedError("Subclasses must implement serialize()")

    def save(self, file_path: str) -> None:
        """
        Serialize the model and save to a file.

        Args:
            file_path: Path to output file
        """
        output = self.serialize()
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(output)
