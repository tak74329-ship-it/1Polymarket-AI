"""Polymarket Live Execution Adapter — skeleton only, no real trading.

All order methods raise RuntimeError unless live_trading_enabled=true
is explicitly set in config.
"""

import uuid
from datetime import datetime, timezone
from backend.execution.base import BaseExecutionAdapter, Order
from backend.utils.config import load_trading_config

CFG = load_trading_config()


class PolymarketExecutionAdapter(BaseExecutionAdapter):
    """Live execution adapter for Polymarket CLOB API.

    ⚠️  ALL real order methods are PROTECTED by the live_trading_enabled flag.
    ⚠️  No private keys are stored in this repository.
    ⚠️  This class is a SKELETON for future integration.
    """

    def __init__(self):
        self.live_enabled = CFG.get("live_trading_enabled", False)
        self.paper_mode = CFG.get("paper_mode", True)
        self._api_key = None   # Placeholder — never populated in repo

    def name(self) -> str:
        return "polymarket_live"

    def _require_live(self):
        """Guard: raise if live trading is not explicitly enabled."""
        if not self.live_enabled or self.paper_mode:
            raise RuntimeError(
                "🚫 Live trading is DISABLED. "
                "Set paper_mode=false AND live_trading_enabled=true in config to enable."
            )

    def validate_market(self, market_id: str) -> dict:
        """Check if a market exists and is tradeable. Stub for future API call."""
        import psycopg2
        from backend.utils.config import DB_CONFIG
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "SELECT market_id, active, closed, liquidity FROM markets WHERE market_id = %s",
            (market_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return {"valid": False, "reason": f"Market {market_id} not found"}
        mid, active, closed, liquidity = row
        liquidity = float(liquidity or 0)

        if not active:
            return {"valid": False, "reason": "Market is not active"}
        if closed:
            return {"valid": False, "reason": "Market is closed"}
        if liquidity < CFG.get("min_liquidity", 1000):
            return {"valid": False, "reason": f"Liquidity {liquidity:.0f} below minimum"}
        return {"valid": True, "market_id": mid}

    def validate_balance(self, required_usd: float) -> dict:
        """Check if paper_balance has enough cash. Stub for future wallet check."""
        import psycopg2
        from backend.utils.config import DB_CONFIG
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT cash FROM paper_balance ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()

        cash = float(row[0]) if row else 0
        if cash < required_usd:
            return {"sufficient": False, "cash": cash, "required": required_usd}
        return {"sufficient": True, "cash": cash}

    def prepare_order(self, order: Order) -> Order:
        """Pre-process an order before execution (e.g. clamp price, set IDs)."""
        order.mode = "live"
        return order

    def dry_run_order(self, order: Order) -> dict:
        """Simulate order execution without placing on-chain. Always allowed."""
        print(f"  🔍 DRY RUN: {order.action} {order.side} on {order.market_id}")
        print(f"     Amount: ${order.amount_usd:.2f} @ {order.price_limit:.4f}")
        return {
            "success": True,
            "dry_run": True,
            "estimated_cost": order.amount_usd,
            "message": "Dry run passed (no real order placed)",
        }

    def execute(self, order: Order) -> dict:
        """Execute a live order. ❌ RAISES RuntimeError unless live_trading_enabled."""
        # Always guard
        self._require_live()

        # If we get here, live trading is explicitly enabled — but still a skeleton
        order = self.prepare_order(order)
        order_id = f"poly_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        print(f"  🌐 LIVE ORDER {order_id}")
        print(f"     Market: {order.market_id}")
        print(f"     Side:   {order.side} | Action: {order.action}")
        print(f"     Amount: ${order.amount_usd:.2f} @ {order.price_limit:.4f}")

        return {
            "success": True,
            "order_id": order_id,
            "message": f"Live {order.action} {order.side} on {order.market_id}",
            "mode": "live",
            "executed_at": now,
            "order": order.to_dict(),
        }

    def cancel(self, market_id: str) -> dict:
        """Cancel a live order. Guards with _require_live()."""
        self._require_live()
        return {"success": True, "message": f"Live cancel for {market_id}"}
