"""Portfolio Manager — position sizing, exposure, theme limits, market validation."""

import psycopg2
from backend.utils.config import DB_CONFIG, load_trading_config
from backend.risk.risk_manager import detect_theme

CFG = load_trading_config()


def f(v):
    return float(v or 0)


class PortfolioManager:
    """Manages portfolio-level constraints before an order is placed."""

    def __init__(self):
        self.cfg = CFG

    # ── Queries ──────────────────────────────────────────────────────

    def _get_open_count(self, cur) -> int:
        cur.execute("SELECT COUNT(*) FROM paper_positions WHERE status='OPEN'")
        return int(cur.fetchone()[0])

    def _get_total_invested(self, cur) -> float:
        cur.execute("SELECT COALESCE(SUM(invested), 0) FROM paper_positions WHERE status='OPEN'")
        return float(cur.fetchone()[0])

    def _get_cash(self, cur) -> float:
        cur.execute("SELECT cash FROM paper_balance ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return float(row[0]) if row else 10000

    def _get_market_question(self, cur, market_id: str) -> str:
        cur.execute("SELECT question FROM markets WHERE market_id = %s", (market_id,))
        row = cur.fetchone()
        return row[0] if row else ""

    def _count_theme_positions(self, cur, theme: str) -> int:
        cur.execute("SELECT market_id FROM paper_positions WHERE status='OPEN'")
        open_mids = [r[0] for r in cur.fetchall()]
        count = 0
        for mid in open_mids:
            q = self._get_market_question(cur, mid)
            if detect_theme(q) == theme:
                count += 1
        return count

    def _get_market_info(self, cur, market_id: str) -> dict:
        cur.execute("""
            SELECT active, closed, liquidity, volume
            FROM markets WHERE market_id = %s
        """, (market_id,))
        row = cur.fetchone()
        if not row:
            return {"exists": False}
        active, closed, liquidity, volume = row
        return {
            "exists": True,
            "active": bool(active),
            "closed": bool(closed),
            "liquidity": f(liquidity),
            "volume": f(volume),
        }

    def _get_spread(self, cur, market_id: str) -> float:
        cur.execute("""
            SELECT spread FROM market_prices
            WHERE market_id = %s AND spread IS NOT NULL
            ORDER BY created_at DESC LIMIT 1
        """, (market_id,))
        row = cur.fetchone()
        return f(row[0]) if row else 0.0

    # ── Validation checks ────────────────────────────────────────────

    def check_market_open(self, cur, market_id: str) -> tuple:
        """Block closed or inactive markets."""
        info = self._get_market_info(cur, market_id)
        if not info["exists"]:
            return False, f"Market {market_id} not found"
        if not info["active"]:
            return False, f"Market {market_id} is not active"
        if info["closed"]:
            return False, f"Market {market_id} is closed"
        return True, ""

    def check_min_liquidity(self, cur, market_id: str) -> tuple:
        """Block low-liquidity markets."""
        min_liq = self.cfg.get("min_liquidity", 1000)
        info = self._get_market_info(cur, market_id)
        if not info["exists"]:
            return False, "Market not found"
        if info["liquidity"] < min_liq:
            return False, f"Liquidity {info['liquidity']:.0f} < minimum {min_liq}"
        return True, ""

    def check_max_spread(self, cur, market_id: str) -> tuple:
        """Block wide-spread markets."""
        max_spread = self.cfg.get("max_spread", 0.05)
        spread = self._get_spread(cur, market_id)
        if spread > max_spread:
            return False, f"Spread {spread:.4f} exceeds max {max_spread:.4f}"
        return True, ""

    def check_max_exposure(self, cur, additional: float = 0.0) -> tuple:
        """Block if adding additional would exceed max exposure."""
        max_exp = self.cfg.get("max_exposure_pct", 30.0)
        cash = self._get_cash(cur)
        invested = self._get_total_invested(cur)
        new_invested = invested + additional
        total = cash + new_invested
        if total <= 0:
            return True, ""
        exposure = (new_invested / total) * 100
        if exposure >= max_exp:
            return False, f"Exposure would be {exposure:.1f}% (max {max_exp:.0f}%)"
        return True, ""

    def check_max_positions(self, cur) -> tuple:
        """Block if max positions reached."""
        max_pos = self.cfg.get("max_open_positions", 5)
        current = self._get_open_count(cur)
        if current >= max_pos:
            return False, f"Already at max positions ({current}/{max_pos})"
        return True, ""

    def check_theme_limit(self, cur, question: str) -> tuple:
        """Block if this theme already hit the per-theme limit."""
        max_per = self.cfg.get("max_positions_per_theme", 2)
        theme = detect_theme(question)
        count = self._count_theme_positions(cur, theme)
        if count >= max_per:
            return False, f"Theme '{theme}' already has {count} positions (max {max_per})"
        return True, ""

    def check_amount(self, amount_usd: float) -> tuple:
        """Block if trade amount exceeds per-trade limit."""
        max_trade = self.cfg.get("trade_amount", 100)
        if amount_usd > max_trade:
            return False, f"Trade amount ${amount_usd:.2f} exceeds max ${max_trade:.2f}"
        return True, ""

    def check_all(self, cur, market_id: str, amount_usd: float) -> list:
        """Run all portfolio checks. Returns list of (check_name, passed, reason)."""
        results = []

        # 1. Market open
        ok, reason = self.check_market_open(cur, market_id)
        results.append(("market_open", ok, reason))

        # 2. Min liquidity
        ok, reason = self.check_min_liquidity(cur, market_id)
        results.append(("min_liquidity", ok, reason))

        # 3. Max spread
        ok, reason = self.check_max_spread(cur, market_id)
        results.append(("max_spread", ok, reason))

        # 4. Max exposure
        ok, reason = self.check_max_exposure(cur, amount_usd)
        results.append(("max_exposure", ok, reason))

        # 5. Max positions
        ok, reason = self.check_max_positions(cur)
        results.append(("max_positions", ok, reason))

        # 6. Theme limit
        question = self._get_market_question(cur, market_id)
        ok, reason = self.check_theme_limit(cur, question)
        results.append(("theme_limit", ok, reason))

        # 7. Amount
        ok, reason = self.check_amount(amount_usd)
        results.append(("trade_amount", ok, reason))

        return results


def run():
    """CLI: run portfolio checks on a sample market."""
    print("=" * 80)
    print("  PORTFOLIO MANAGER V1")
    print("=" * 80)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    pm = PortfolioManager()
    cfg = CFG

    print(f"\n{'─' * 80}")
    print("  CONFIG")
    print(f"{'─' * 80}")
    print(f"  max_open_positions:      {cfg.get('max_open_positions')}")
    print(f"  max_positions_per_theme: {cfg.get('max_positions_per_theme')}")
    print(f"  max_exposure_pct:        {cfg.get('max_exposure_pct')}%")
    print(f"  max_spread:              {cfg.get('max_spread')}")
    print(f"  min_liquidity:           {cfg.get('min_liquidity')}")
    print(f"  trade_amount:            ${cfg.get('trade_amount')}")

    # Get latest BUY candidate from ai_analysis
    cur.execute("""
        SELECT DISTINCT ON (a.market_id)
            a.market_id,
            a.raw->'analysis'->>'action' AS ai_action,
            a.confidence
        FROM ai_analysis a
        WHERE a.raw->'analysis'->>'action' = 'BUY'
        ORDER BY a.market_id, a.created_at DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    if row:
        market_id = row[0]
        amount = cfg.get("trade_amount", 100)
        question = pm._get_market_question(cur, market_id)

        print(f"\n{'─' * 80}")
        print(f"  CHECKING: {market_id} — ${amount} [{question[:60]}]")
        print(f"{'─' * 80}")

        results = pm.check_all(cur, market_id, amount)
        all_pass = True
        for name, ok, reason in results:
            status = "✅ PASS" if ok else "❌ BLOCKED"
            if not ok:
                all_pass = False
            print(f"  {name:<20} {status:<12} {reason}")

        print(f"\n{'=' * 80}")
        if all_pass:
            print(f"  ✅ ALL CHECKS PASSED — order can proceed")
        else:
            blocked = [n for n, ok, _ in results if not ok]
            print(f"  ❌ BLOCKED BY: {', '.join(blocked)}")
        print(f"{'=' * 80}")
    else:
        print(f"\n  ⚠️  No BUY candidates found in ai_analysis")

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
