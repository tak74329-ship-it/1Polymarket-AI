"""Performance Analytics V1 — evaluate paper trading performance."""

from datetime import datetime, timezone
import psycopg2
from backend.utils.config import DB_CONFIG


def f(v):
    return float(v or 0)


def detect_theme(question):
    q = (question or "").lower()
    if "bitcoin" in q or "btc" in q:
        return "crypto"
    if "eth" in q or "ethereum" in q:
        return "crypto"
    if "world cup" in q or "fifa" in q:
        return "sports"
    if "trump" in q:
        return "politics"
    if "marco rubio" in q:
        return "politics"
    if "putin" in q or "russia" in q:
        return "politics"
    if "iran" in q:
        return "geopolitics"
    if "china" in q or "taiwan" in q:
        return "geopolitics"
    if "election" in q or "president" in q or "presidential" in q:
        return "politics"
    if "israel" in q or "bennett" in q:
        return "geopolitics"
    return "other"


def run():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("=" * 80)
    print("  PERFORMANCE ANALYTICS V1")
    print("=" * 80)

    # ── 1. Balance ───────────────────────────────────────────────────
    cur.execute("""
        SELECT cash, equity, pnl, roi
        FROM paper_balance ORDER BY id DESC LIMIT 1
    """)
    bal = cur.fetchone()
    cash = f(bal[0]) if bal else 10000
    equity = f(bal[1]) if bal else 10000
    total_realized_pnl = f(bal[2]) if bal else 0
    roi = f(bal[3]) if bal else 0

    # ── 2. All positions ─────────────────────────────────────────────
    cur.execute("""
        SELECT p.id, p.market_id, p.side, p.entry_price, p.qty, p.invested,
               p.status, p.created_at, p.closed_at
        FROM paper_positions p
        ORDER BY p.created_at
    """)
    all_positions = cur.fetchall()

    # ── 3. All orders for PnL detail ─────────────────────────────────
    cur.execute("""
        SELECT o.market_id, o.side, o.price, o.qty, o.amount, o.reason, o.created_at
        FROM paper_orders o
        ORDER BY o.id
    """)
    all_orders = cur.fetchall()

    # ── 4. Latest prices for open positions ──────────────────────────
    cur.execute("""
        SELECT DISTINCT ON (p.market_id)
            p.market_id,
            (SELECT yes_price FROM market_prices mp
             WHERE mp.market_id = p.market_id
             ORDER BY mp.created_at DESC LIMIT 1) AS latest_price,
            (SELECT raw->'analysis'->>'action' FROM ai_analysis a
             WHERE a.market_id = p.market_id
             ORDER BY a.created_at DESC LIMIT 1) AS ai_action,
            (SELECT raw->'analysis'->>'risk_level' FROM ai_analysis a
             WHERE a.market_id = p.market_id
             ORDER BY a.created_at DESC LIMIT 1) AS risk_level,
            (SELECT confidence FROM ai_analysis a
             WHERE a.market_id = p.market_id
             ORDER BY a.created_at DESC LIMIT 1) AS ai_confidence
        FROM paper_positions p
        WHERE p.status = 'OPEN'
    """)
    latest_data = {r[0]: r for r in cur.fetchall()}

    # ── 5. Market questions for theme detection ──────────────────────
    cur.execute("""
        SELECT market_id, question FROM markets
    """)
    market_questions = {r[0]: r[1] for r in cur.fetchall()}

    # ── 6. AI decision counts ────────────────────────────────────────
    cur.execute("""
        SELECT raw->'analysis'->>'action' AS action, COUNT(*) AS cnt
        FROM ai_analysis
        GROUP BY action
        ORDER BY cnt DESC
    """)
    ai_action_counts = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("""
        SELECT raw->'analysis'->>'risk_level' AS risk, COUNT(*) AS cnt
        FROM ai_analysis
        GROUP BY risk
        ORDER BY cnt DESC
    """)
    ai_risk_counts = {r[0]: r[1] for r in cur.fetchall()}

    cur.close()
    conn.close()

    # ═══════════════════════════════════════════════════════════════════
    #  ANALYTICS
    # ═══════════════════════════════════════════════════════════════════

    # Separate open vs closed
    open_positions = [p for p in all_positions if p[6] == "OPEN"]
    closed_positions = [p for p in all_positions if p[6] == "CLOSED"]

    total_trades = len(all_positions)
    open_count = len(open_positions)
    closed_count = len(closed_positions)

    # Calculate PnL for each closed position from orders
    closed_pnls = []
    for cp in closed_positions:
        pid, mid, side, entry_price, qty, invested, status, created, closed_at = cp
        entry_price = f(entry_price)
        invested = f(invested)
        qty = f(qty)
        # Find matching sell order
        sell_order = None
        for o in all_orders:
            if o[0] == mid and o[1] == "SELL":
                sell_order = o
        if sell_order:
            exit_price = f(sell_order[2])
            exit_amount = f(sell_order[3]) * exit_price
            pnl = exit_amount - invested
            closed_pnls.append({
                "market_id": mid,
                "pnl": pnl,
                "entry": entry_price,
                "exit": exit_price,
                "reason": sell_order[5],
            })

    # Calculate unrealized PnL for open positions
    total_unrealized = 0.0
    total_invested_open = 0.0
    open_details = []

    for op in open_positions:
        pid, mid, side, entry_price, qty, invested, status, created, closed_at = op
        entry_price = f(entry_price)
        invested = f(invested)
        qty = f(qty)

        ld = latest_data.get(mid)
        latest_price = f(ld[1]) if ld else entry_price
        ai_action = ld[2] if ld else "—"
        risk_level = ld[3] if ld else "—"
        ai_confidence = f(ld[4]) if ld else 0

        current_value = latest_price * qty
        unrealized_pnl = current_value - invested
        unrealized_roi = (unrealized_pnl / invested * 100) if invested > 0 else 0

        total_unrealized += unrealized_pnl
        total_invested_open += invested

        theme = detect_theme(market_questions.get(mid, ""))

        open_details.append({
            "market_id": mid,
            "entry_price": entry_price,
            "latest_price": latest_price,
            "invested": invested,
            "current_value": current_value,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_roi": unrealized_roi,
            "ai_action": ai_action,
            "risk_level": risk_level,
            "ai_confidence": ai_confidence,
            "theme": theme,
        })

    # Calculate totals
    total_realized = sum(c["pnl"] for c in closed_pnls)
    total_pnl = total_realized + total_unrealized
    total_pnl_roi = (total_pnl / (10000 - cash + total_pnl) * 100) if (10000 - cash + total_pnl) > 0 else 0

    # Win/Loss stats
    wins = [c for c in closed_pnls if c["pnl"] > 0]
    losses = [c for c in closed_pnls if c["pnl"] < 0]
    flats = [c for c in closed_pnls if c["pnl"] == 0]
    win_count = len(wins)
    loss_count = len(losses)
    flat_count = len(flats)
    total_closed_trades = len(closed_pnls)
    win_rate = (win_count / total_closed_trades * 100) if total_closed_trades > 0 else None
    avg_win = sum(w["pnl"] for w in wins) / win_count if win_count > 0 else 0
    avg_loss = sum(l["pnl"] for l in losses) / loss_count if loss_count > 0 else 0

    # Best / worst
    all_trades_sorted = sorted(closed_pnls, key=lambda x: x["pnl"], reverse=True)
    best_trade = all_trades_sorted[0] if all_trades_sorted else None
    worst_trade = all_trades_sorted[-1] if all_trades_sorted else None

    # Exposure
    total_asset = cash + total_invested_open + total_unrealized
    exposure_pct = (total_invested_open / total_asset * 100) if total_asset > 0 else 0

    # Group by risk_level
    risk_groups = {}
    for od in open_details:
        rl = od["risk_level"]
        risk_groups.setdefault(rl, {"count": 0, "invested": 0, "unrealized_pnl": 0})
        risk_groups[rl]["count"] += 1
        risk_groups[rl]["invested"] += od["invested"]
        risk_groups[rl]["unrealized_pnl"] += od["unrealized_pnl"]

    # Group by theme
    theme_groups = {}
    for od in open_details:
        t = od["theme"]
        theme_groups.setdefault(t, {"count": 0, "invested": 0})
        theme_groups[t]["count"] += 1
        theme_groups[t]["invested"] += od["invested"]

    # ═══════════════════════════════════════════════════════════════════
    #  PRINT REPORT
    # ═══════════════════════════════════════════════════════════════════

    print(f"\n{'─' * 80}")
    print("  TRADE SUMMARY")
    print(f"{'─' * 80}")
    print(f"  Total trades:           {total_trades}")
    print(f"  Open positions:         {open_count}")
    print(f"  Closed positions:       {closed_count}")
    print(f"  Win rate (closed):      {'N/A (no closed trades)' if win_rate is None else f'{win_rate:.2f}%'}")
    if win_rate is not None:
        print(f"  Wins: {win_count} / Losses: {loss_count} / Flat: {flat_count}")

    print(f"\n{'─' * 80}")
    print("  P&L")
    print(f"{'─' * 80}")
    print(f"  Total realized PnL:     ${total_realized:>+9.2f}")
    print(f"  Total unrealized PnL:   ${total_unrealized:>+9.2f}")
    print(f"  Total PnL:              ${total_pnl:>+9.2f}")
    print(f"  ROI:                    {roi:>+8.2f}%")
    print(f"  Avg win (closed):       ${avg_win:>+9.2f}" if win_count > 0 else "  Avg win (closed):       N/A")
    print(f"  Avg loss (closed):      ${avg_loss:>+9.2f}" if loss_count > 0 else "  Avg loss (closed):      N/A")

    if best_trade:
        print(f"  Best trade:             {best_trade['market_id']} (${best_trade['pnl']:+.2f})")
    if worst_trade:
        print(f"  Worst trade:            {worst_trade['market_id']} (${worst_trade['pnl']:+.2f})")

    print(f"\n{'─' * 80}")
    print("  PORTFOLIO")
    print(f"{'─' * 80}")
    print(f"  Cash:                  ${cash:>9.2f}")
    print(f"  Equity:                ${equity:>9.2f}")
    print(f"  Total invested (open): ${total_invested_open:>9.2f}")
    print(f"  Current value (open):  ${sum(od['current_value'] for od in open_details):>9.2f}")
    print(f"  Exposure:              {exposure_pct:>7.1f}%")
    print(f"  Risk-free rate:        {cash / 10000 * 100:.1f}%")

    # ── AI decision counts ──────────────────────────────────────────
    print(f"\n{'─' * 80}")
    print("  AI DECISION BREAKDOWN")
    print(f"{'─' * 80}")
    for action in ["BUY", "WATCH", "SKIP"]:
        cnt = ai_action_counts.get(action, 0)
        print(f"  {action:<8} {cnt:>4}")

    print(f"\n  By Risk Level:")
    for risk in ["LOW", "MEDIUM", "HIGH"]:
        cnt = ai_risk_counts.get(risk, 0)
        print(f"  {risk:<8} {cnt:>4}")

    # ── Group by risk level ─────────────────────────────────────────
    if risk_groups:
        print(f"\n{'─' * 80}")
        print("  PERFORMANCE BY RISK LEVEL (open)")
        print(f"{'─' * 80}")
        print(f"  {'Risk':>8} {'Count':>6} {'Invested':>10} {'uPnL':>10}")
        for rl in ["LOW", "MEDIUM", "HIGH"]:
            g = risk_groups.get(rl)
            if g:
                print(f"  {rl:>8} {g['count']:>6} ${g['invested']:>8.0f} ${g['unrealized_pnl']:>+8.2f}")

    # ── Group by theme ──────────────────────────────────────────────
    if theme_groups:
        print(f"\n{'─' * 80}")
        print("  EXPOSURE BY THEME (open)")
        print(f"{'─' * 80}")
        print(f"  {'Theme':<14} {'Count':>6} {'Invested':>10}")
        for theme, g in sorted(theme_groups.items(), key=lambda x: x[1]["invested"], reverse=True):
            print(f"  {theme:<14} {g['count']:>6} ${g['invested']:>8.0f}")

    # ═══════════════════════════════════════════════════════════════════
    #  WARNINGS
    # ═══════════════════════════════════════════════════════════════════
    warnings = []

    if win_rate is not None and win_rate < 50:
        warnings.append(f"⚠️  Win rate ({win_rate:.1f}%) is below 50%")
    if roi < 0:
        warnings.append(f"⚠️  ROI ({roi:.1f}%) is negative")
    if exposure_pct > 30:
        warnings.append(f"⚠️  Exposure ({exposure_pct:.1f}%) is too high (>30%)")

    # Duplicate theme
    for theme, g in theme_groups.items():
        if g["count"] >= 2:
            warnings.append(f"⚠️  Duplicate theme '{theme}' with {g['count']} positions (${g['invested']:.0f} invested)")

    # Large unrealized loss
    for od in open_details:
        if od["unrealized_roi"] <= -5:
            warnings.append(f"⚠️  {od['market_id']} is down {od['unrealized_roi']:.1f}%")
        if od["unrealized_roi"] <= -10:
            warnings.append(f"🚨  {od['market_id']} is down {od['unrealized_roi']:.1f}% — consider stop-loss")

    print(f"\n{'=' * 80}")
    print(f"  WARNINGS ({len(warnings)})")
    print(f"{'=' * 80}")
    if warnings:
        for w in warnings:
            print(f"  {w}")
    else:
        print("  ✅ No warnings")

    return {
        "total_trades": total_trades,
        "open_positions": open_count,
        "closed_positions": closed_count,
        "win_rate": win_rate,
        "total_realized_pnl": total_realized,
        "total_unrealized_pnl": total_unrealized,
        "total_pnl": total_pnl,
        "roi": roi,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "exposure": exposure_pct,
        "warnings": warnings,
    }


if __name__ == "__main__":
    run()
