"""Paper Trading Monitor V1 — open positions & risk report."""

from datetime import datetime
import psycopg2
from backend.utils.config import DB_CONFIG

MAX_HOLDING_MINUTES = 60 * 24 * 7  # 7 days
PNL_WARN_PCT = -5.0


def f(v):
    return float(v or 0)


def age_minutes(created_at):
    """Compute age in minutes. DB stores naive local timestamps."""
    if not created_at:
        return 0
    now = datetime.now()
    # created_at from DB is naive (TIMESTAMP without time zone)
    if created_at.tzinfo is not None:
        created_at = created_at.replace(tzinfo=None)
    return int((now - created_at).total_seconds() / 60)


def run():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("=" * 80)
    print("  PAPER TRADING MONITOR V1")
    print("=" * 80)

    # ── 1. Balance snapshot ──────────────────────────────────────────
    cur.execute("""
        SELECT cash, equity, pnl, roi
        FROM paper_balance
        ORDER BY id DESC LIMIT 1
    """)
    bal = cur.fetchone()
    cash = f(bal[0]) if bal else 0
    equity = f(bal[1]) if bal else 0
    total_pnl = f(bal[2]) if bal else 0
    roi = f(bal[3]) if bal else 0

    # ── 2. Open positions ────────────────────────────────────────────
    cur.execute("""
        SELECT
            p.id,
            p.market_id,
            (SELECT question FROM markets m WHERE m.market_id = p.market_id) AS question,
            p.entry_price,
            p.qty,
            p.invested,
            p.created_at,
            (SELECT yes_price FROM market_prices mp
             WHERE mp.market_id = p.market_id
             ORDER BY mp.created_at DESC LIMIT 1) AS latest_price,
            (SELECT raw->'analysis'->>'action' FROM ai_analysis a
             WHERE a.market_id = p.market_id
             ORDER BY a.created_at DESC LIMIT 1) AS ai_action,
            (SELECT confidence FROM ai_analysis a
             WHERE a.market_id = p.market_id
             ORDER BY a.created_at DESC LIMIT 1) AS ai_confidence,
            (SELECT raw->'analysis'->>'risk_level' FROM ai_analysis a
             WHERE a.market_id = p.market_id
             ORDER BY a.created_at DESC LIMIT 1) AS risk_level,
            (SELECT raw->'analysis'->>'reason' FROM ai_analysis a
             WHERE a.market_id = p.market_id
             ORDER BY a.created_at DESC LIMIT 1) AS ai_reason
        FROM paper_positions p
        WHERE p.status = 'OPEN'
        ORDER BY p.created_at ASC
    """)
    positions = cur.fetchall()

    # ── 3. Closed positions ──────────────────────────────────────────
    cur.execute("""
        SELECT p.id, p.market_id, p.entry_price, p.qty, p.invested,
               p.created_at, p.closed_at,
               (SELECT reason FROM paper_orders o
                WHERE o.market_id = p.market_id AND o.side = 'SELL'
                ORDER BY o.created_at DESC LIMIT 1) AS close_reason
        FROM paper_positions p
        WHERE p.status = 'CLOSED'
        ORDER BY p.closed_at DESC LIMIT 20
    """)
    closed_positions = cur.fetchall()

    # ── 4. Portfolio summary ─────────────────────────────────────────
    open_count = len(positions)
    total_invested = sum(f(p[5]) for p in positions)
    total_value = 0.0
    position_rows = []
    risk_warnings = []

    for row in positions:
        (
            pid, market_id, question, entry_price, qty, invested,
            created_at, latest_price, ai_action, ai_confidence,
            risk_level, ai_reason
        ) = row

        entry_price = f(entry_price)
        qty = f(qty)
        invested = f(invested)
        latest_price = f(latest_price) if latest_price else entry_price
        ai_confidence = f(ai_confidence)

        current_value = latest_price * qty
        total_value += current_value

        unrealized_pnl = current_value - invested
        unrealized_roi = (unrealized_pnl / invested * 100) if invested > 0 else 0
        age = age_minutes(created_at)

        if unrealized_roi <= PNL_WARN_PCT:
            risk_warnings.append(
                f"\u26a0\ufe0f  Position {market_id} down {unrealized_roi:.1f}% "
                f"(threshold {PNL_WARN_PCT:.0f}%)"
            )

        if age > MAX_HOLDING_MINUTES:
            risk_warnings.append(
                f"\u26a0\ufe0f  Position {market_id} held {age} min "
                f"(max {MAX_HOLDING_MINUTES} min)"
            )

        position_rows.append({
            "market_id": market_id,
            "question": (question or "")[:60],
            "entry_price": entry_price,
            "latest_price": latest_price,
            "qty": qty,
            "invested": invested,
            "current_value": current_value,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_roi": unrealized_roi,
            "age_minutes": age,
            "ai_action": ai_action or "\u2014",
            "ai_confidence": ai_confidence,
            "risk_level": risk_level or "\u2014",
        })

    # ── Theme overlap detection ────────────────────────────────────
    themes = {}
    for r in position_rows:
        q = r["question"].lower()
        if "bitcoin" in q:
            themes.setdefault("bitcoin", []).append(r["market_id"])
        if "world cup" in q or "fifa" in q:
            themes.setdefault("world_cup", []).append(r["market_id"])
        if "trump" in q:
            themes.setdefault("trump", []).append(r["market_id"])
        if "marco rubio" in q:
            themes.setdefault("rubio", []).append(r["market_id"])

    for theme, mids in themes.items():
        if len(mids) >= 2:
            risk_warnings.append(
                f"\u26a0\ufe0f  Duplicate theme '{theme}': {', '.join(mids)}"
            )

    if open_count >= 5:
        risk_warnings.append(
            f"\u26a0\ufe0f  Too many open positions: {open_count} (max 5)"
        )

    sorted_positions = sorted(position_rows, key=lambda x: x["unrealized_pnl"], reverse=True)
    best = sorted_positions[0] if sorted_positions else None
    worst = sorted_positions[-1] if sorted_positions else None

    exposure = total_invested
    exposure_pct = (exposure / (cash + total_value) * 100) if (cash + total_value) > 0 else 0

    # ══════════════════════════════════════════════════════════════════
    #  PRINT REPORT
    # ══════════════════════════════════════════════════════════════════

    print(f"\n{'=' * 80}")
    print(f"  PORTFOLIO SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Cash:                ${cash:>9.2f}")
    print(f"  Equity:              ${equity:>9.2f}")
    print(f"  Total PnL:           ${total_pnl:>+9.2f}")
    print(f"  ROI:                 {roi:>+8.2f}%")
    print(f"  Open positions:      {open_count:>4}")
    print(f"  Total invested:      ${total_invested:>9.2f}")
    print(f"  Current value:       ${total_value:>9.2f}")
    print(f"  Exposure:            {exposure_pct:>7.1f}%")
    if best:
        print(f"  Best position:       {best['market_id']} ({best['unrealized_pnl']:+.2f})")
    if worst:
        print(f"  Worst position:      {worst['market_id']} ({worst['unrealized_pnl']:+.2f})")

    # ── Open positions table ─────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print(f"  OPEN POSITIONS ({open_count})")
    print(f"{'=' * 80}")
    print(f"{'market_id':>10} {'entry':>8} {'last':>8} {'size':>8} "
          f"{'uPnL':>8} {'uROI':>7} {'age_m':>6} {'action':>6} {'conf':>5} "
          f"{'risk':>5}  question")
    print("-" * 120)

    for r in position_rows:
        print(
            f"{r['market_id']:>10} "
            f"{r['entry_price']:>8.4f} "
            f"{r['latest_price']:>8.4f} "
            f"{r['qty']:>8.1f} "
            f"{r['unrealized_pnl']:>+8.2f} "
            f"{r['unrealized_roi']:>+6.2f}% "
            f"{r['age_minutes']:>6} "
            f"{r['ai_action']:>6} "
            f"{r['ai_confidence']:>5.0f} "
            f"{r['risk_level']:>5} "
            f" {r['question']}"
        )

    # ── Closed positions ─────────────────────────────────────────────
    if closed_positions:
        print(f"\n{'=' * 80}")
        print(f"  RECENTLY CLOSED ({len(closed_positions)})")
        print(f"{'=' * 80}")
        for cp in closed_positions:
            pid, mid, ep, qty, inv, created, closed_at, reason = cp
            ep = f(ep)
            print(f"  {mid:>10}  entry={ep:.4f}  reason={reason}")

    # ── Risk warnings ───────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print(f"  RISK WARNINGS ({len(risk_warnings)})")
    print(f"{'=' * 80}")
    if risk_warnings:
        for w in risk_warnings:
            print(f"  {w}")
    else:
        print("  \u2705 No risk warnings")

    cur.close()
    conn.close()

    return {
        "cash": cash,
        "equity": equity,
        "total_pnl": total_pnl,
        "roi": roi,
        "open_positions": open_count,
        "exposure": exposure_pct,
        "positions": position_rows,
        "warnings": risk_warnings,
    }


if __name__ == "__main__":
    run()
