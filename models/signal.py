from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TradeSignal:
    """
    Minimal domain model for a generated trade signal.

    The runtime currently passes dicts end-to-end; this model exists to enable
    gradual migration to typed boundaries without breaking existing behavior.
    """

    index: str
    regime: str
    strategy: str
    confidence: int
    legs: dict[str, dict[str, Any]]
    capital_used: float
    lots: int

