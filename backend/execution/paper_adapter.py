"""Paper Execution Adapter — simulated orders via existing paper_trader logic."""

import uuid
from datetime import datetime, timezone
from backend.execution.base import BaseExecutionAdapter, Order
from backend.utils.config import load_trading_config

CFG = load_trading_config()


class PaperExecutionAdapter(BaseExecutionAdapter):
    """Simulates order execution by writing to paper_positions / paper_orders.

    This is the default adapter when paper_mode=true.
    """

    def name(self) -> str:
        return "paper"

    def execute(self, order: Order) -> dict:
        """Execute a paper order (no real API call)."""
        valid, reason = self.validate(order)
        if not valid:
            return {"success": False, "order_id": "", "message": reason}

        order_id = f"paper_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        print(f"  📝 PAPER ORDER {order_id}")
        print(f"     Market: {order.market_id}")
        print(f"     Side:   {order.side} | Action: {order.action}")
        print(f"     Amount: ${order.amount_usd:.2f} @ {order.price_limit:.4f}")
        print(f"     Reason: {order.reason}")

        return {
            "success": True,
            "order_id": order_id,
            "message": f"Paper {order.action} {order.side} on {order.market_id} for ${order.amount_usd:.2f}",
            "mode": "paper",
            "executed_at": now,
            "order": order.to_dict(),
        }

    def cancel(self, market_id: str) -> dict:
        """Cancel a paper position (no-op in paper mode)."""
        return {"success": True, "message": f"Paper cancel for {market_id} (no-op)"}
