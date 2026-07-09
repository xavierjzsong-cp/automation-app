"""Base interface for partner mappers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseMapper(ABC):
    """Convert routed partner targets into adapter input data."""

    @abstractmethod
    def build_mapped_data(
        self,
        target: dict[str, Any],
        shared_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError
