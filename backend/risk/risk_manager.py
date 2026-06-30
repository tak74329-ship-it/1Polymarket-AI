"""Risk Manager V2 — blocking logic for paper trading."""

from backend.utils.config import load_trading_config

CFG = load_trading_config()


def detect_theme(question):
    q = (question or "").lower()
    if "bitcoin" in q or "btc" in q or "eth" in q or "ethereum" in q or "crypto" in q:
        return "crypto"
    if "world cup" in q or "fifa" in q:
        return "sports"
    if "trump" in q or "biden" in q or "marco rubio" in q:
        return "politics"
    if "putin" in q or "russia" in q:
        return "politics"
    if "iran" in q or "israel" in q or "bennett" in q or "china" in q or "taiwan" in q:
        return "geopolitics"
    if "election" in q or "president" in q or "presidential" in q:
        return "politics"
    if "bitcoin" in q:
        return "crypto"
    return "other"


class RiskManager:
    """Evaluates trade requests and returns (allowed: bool, reason: str)."""

    def __init__(self):
        self.cfg = CFG
        self.paper_mode = self.cfg.get("paper_mode", True)

    def check_paper_mode(self) -> tuple:
        """Block trades if paper_mode is disabled."""
        if not self.paper_mode:
            return False, "Real trading disabled (paper_mode=false)"
        return True, ""

    def check_exposure(self, current_invested: float, total_asset: float) -> tuple:
        """Block if exposure exceeds max_exposure_pct."""
        max_exposure = self.cfg.get("max_exposure_pct", 30.0)
        if total_asset <= 0:
            return True, ""
        exposure = (current_invested / total_asset) * 100
        if exposure >= max_exposure:
            return False, f"Exposure {exposure:.1f}% exceeds limit {max_exposure:.0f}%"
        return True, ""

    def check_max_positions(self, current_open: int) -> tuple:
        """Block if max_open_positions reached."""
        max_pos = self.cfg.get("max_open_positions", 5)
        if current_open >= max_pos:
            return False, f"Max open positions reached ({current_open}/{max_pos})"
        return True, ""

    def check_duplicate_theme(self, question: str, cur) -> tuple:
        """Block if this theme already has max_positions_per_theme open positions."""
        max_per_theme = self.cfg.get("max_positions_per_theme", 2)
        theme = detect_theme(question)

        import psycopg2
        from backend.utils.config import DB_CONFIG
        conn = psycopg2.connect(**DB_CONFIG)
        c = conn.cursor()
        c.execute("""
            SELECT p.market_id
            FROM paper_positions p
            WHERE p.status = 'OPEN'
        """)
        open_mids = [r[0] for r in c.fetchall()]
        c.close()
        conn.close()

        theme_count = 0
        for mid in open_mids:
            c2 = psycopg2.connect(**DB_CONFIG)
            cur2 = c2.cursor()
            cur2.execute("SELECT question FROM markets WHERE market_id = %s", (mid,))
            row = cur2.fetchone()
            cur2.close()
            c2.close()
            if row and detect_theme(row[0]) == theme:
                theme_count += 1

        if theme_count >= max_per_theme:
            return False, f"Theme '{theme}' already has {theme_count} open positions (max {max_per_theme})"
        return True, ""

    def check_all(self, question: str, current_invested: float,
                  total_asset: float, current_open: int, cur) -> list:
        """Run all checks and return list of (allowed, reason) tuples."""
        results = []

        # 1. Paper mode
        ok, reason = self.check_paper_mode()
        results.append((ok, reason))

        # 2. Max positions
        ok, reason = self.check_max_positions(current_open)
        results.append((ok, reason))

        # 3. Exposure
        ok, reason = self.check_exposure(current_invested, total_asset)
        results.append((ok, reason))

        # 4. Duplicate theme
        ok, reason = self.check_duplicate_theme(question, cur)
        results.append((ok, reason))

        return results


def run():
    """CLI: run risk checks on current portfolio state."""
    print("=" * 80)
    print("  RISK MANAGER V2")
    print("=" * 80)

    import psycopg2
    from backend.utils.config import DB_CONFIG

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Load current portfolio state
    cur.execute("SELECT cash, equity, pnl FROM paper_balance ORDER BY id DESC LIMIT 1")
    bal = cur.fetchone()
    cash = float(bal[0]) if bal else 10000
    equity = float(bal[1]) if bal else 10000

    cur.execute("SELECT COUNT(*), COALESCE(SUM(invested), 0) FROM paper_positions WHERE status='OPEN'")
    open_count, total_invested = cur.fetchone()
    open_count = int(open_count)
    total_invested = float(total_invested or 0)

    total_asset = cash + total_invested

    rm = RiskManager()

    print(f"\n{'─' * 80}")
    print("  PORTFOLIO STATE")
    print(f"{'─' * 80}")
    print(f"  Paper mode:          {'ON' if rm.paper_mode else 'OFF'}")
    print(f"  Cash:                ${cash:>9.2f}")
    print(f"  Equity:              ${equity:>9.2f}")
    print(f"  Open positions:      {open_count}")
    print(f"  Total invested:      ${total_invested:>9.2f}")
    print(f"  Total asset:         ${total_asset:>9.2f}")
    exposure = (total_invested / total_asset * 100) if total_asset > 0 else 0
    print(f"  Current exposure:    {exposure:>7.1f}%")

    print(f"\n{'─' * 80}")
    print("  CONFIG CHECK")
    print(f"{'─' * 80}")
    print(f"  max_open_positions:  {CFG['max_open_positions']}")
    print(f"  max_exposure_pct:    {CFG['max_exposure_pct']}%")
    print(f"  max_positions_per_theme: {CFG['max_positions_per_theme']}")
    print(f"  trade_amount:        ${CFG['trade_amount']}")
    print(f"  take_profit_pct:     {CFG['take_profit_pct']*100:.0f}%")
    print(f"  stop_loss_pct:       {CFG['stop_loss_pct']*100:.0f}%")

    print(f"\n{'─' * 80}")
    print("  RISK CHECKS")
    print(f"{'─' * 80}")

    checks = [
        ("Paper mode", rm.check_paper_mode()),
        ("Max positions", rm.check_max_positions(open_count)),
        ("Exposure", rm.check_exposure(total_invested, total_asset)),
    ]
    for name, (ok, reason) in checks:
        status = "✅ PASS" if ok else "❌ BLOCKED"
        print(f"  {name:<20} {status:<12} {reason}")

    print(f"\n  Duplicate theme check per open position:")
    cur.execute("SELECT market_id FROM paper_positions WHERE status='OPEN'")
    open_mids = [r[0] for r in cur.fetchall()]
    for mid in open_mids:
        cur.execute("SELECT question FROM markets WHERE market_id = %s", (mid,))
        row = cur.fetchone()
        if row:
            q = row[0]
            theme = detect_theme(q)
            ok, reason = rm.check_duplicate_theme(q, cur)
            status = "✅ PASS" if ok else "❌ BLOCKED"
            print(f"    {mid:>10} ({theme:<12}) {status:<12} {reason}")

    cur.close()
    conn.close()

    print(f"\n{'=' * 80}")
    blocked_checks = [name for name, (ok, _) in checks if not ok]
    if not blocked_checks:
        print(f"  OVERALL: ✅ ALL CHECKS PASSED")
        return True
    else:
        print(f"  OVERALL: ❌ BLOCKED BY: {', '.join(blocked_checks)}")
        return False


if __name__ == "__main__":
    run()
