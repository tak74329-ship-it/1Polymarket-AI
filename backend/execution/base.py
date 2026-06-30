"""Execution Adapter — base class and standard order object."""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Order:
    """Standardised order object used across all adapters."""
    market_id: str
    condition_id: str = ""
    token_id: str = ""
    side: str = "YES"          # YES or NO
    action: str = "BUY"        # BUY or SELL
    price_limit: float = 0.0
    amount_usd: float = 0.0
    confidence: float = 0.0
    reason: str = ""
    mode: str = "paper"        # paper or live

    def to_dict(self) -> dict:
        return asdict(self)


class BaseExecutionAdapter:
    """Abstract base for execution adapters.

    Subclasses must implement execute() and name().
    """

    def name(self) -> str:
        raise NotImplementedError

    def execute(self, order: Order) -> dict:
        """Execute an order. Returns result dict with at least:
           - success: bool
           - order_id: str
           - message: str
        """
        raise NotImplementedError

    def validate(self, order: Order) -> tuple:
        """Pre-flight validation. Returns (valid: bool, reason: str)."""
        if not order.market_id:
            return False, "market_id is required"
        if order.amount_usd <= 0:
            return False, "amount_usd must be positive"
        if order.side not in ("YES", "NO"):
            return False, "side must be YES or NO"
        if order.action not in ("BUY", "SELL"):
            return False, "action must be BUY or SELL"
        return True, ""
