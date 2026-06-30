import traceback
import psycopg2
from psycopg2.extras import Json
from backend.utils.config import DB_CONFIG

START_CASH = 10000
TRADE_AMOUNT = 100
TAKE_PROFIT = 0.20
STOP_LOSS = -0.08
MAX_OPEN_POSITIONS = 5


def f(v):
    return float(v or 0)


def get_latest_price(cur, market_id):
    cur.execute("""
        SELECT yes_price
        FROM market_prices
        WHERE market_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (market_id,))
    row = cur.fetchone()
    return f(row[0]) if row else None


def ensure_balance(cur):
    cur.execute("SELECT COUNT(*) FROM paper_balance")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            INSERT INTO paper_balance (cash, equity, pnl, roi)
            VALUES (%s, %s, 0, 0)
        """, (START_CASH, START_CASH))


def count_open_positions(cur):
    cur.execute("SELECT COUNT(*) FROM paper_positions WHERE status='OPEN'")
    return cur.fetchone()[0]


def already_open(cur, market_id):
    cur.execute("""
        SELECT COUNT(*)
        FROM paper_positions
        WHERE market_id=%s AND status='OPEN'
    """, (market_id,))
    return cur.fetchone()[0] > 0


def open_position(cur, market_id, price, reason):
    cur.execute("SELECT cash FROM paper_balance ORDER BY id DESC LIMIT 1")
    cash = f(cur.fetchone()[0])

    if cash < TRADE_AMOUNT:
        return False

    qty = TRADE_AMOUNT / price

    cur.execute("""
        INSERT INTO paper_positions
        (market_id, side, entry_price, qty, invested, status)
        VALUES (%s, 'YES', %s, %s, %s, 'OPEN')
    """, (market_id, price, qty, TRADE_AMOUNT))

    cur.execute("""
        INSERT INTO paper_orders
        (market_id, side, price, qty, amount, reason)
        VALUES (%s, 'BUY', %s, %s, %s, %s)
    """, (market_id, price, qty, TRADE_AMOUNT, reason))

    cur.execute("""
        UPDATE paper_balance
        SET cash = cash - %s, updated_at = NOW()
        WHERE id = (SELECT id FROM paper_balance ORDER BY id DESC LIMIT 1)
    """, (TRADE_AMOUNT,))

    return True


def close_position(cur, position_id, market_id, price, qty, invested, reason):
    amount = price * qty
    pnl = amount - invested

    cur.execute("""
        UPDATE paper_positions
        SET status='CLOSED', closed_at=NOW()
        WHERE id=%s
    """, (position_id,))

    cur.execute("""
        INSERT INTO paper_orders
        (market_id, side, price, qty, amount, reason)
        VALUES (%s, 'SELL', %s, %s, %s, %s)
    """, (market_id, price, qty, amount, reason))

    cur.execute("""
        UPDATE paper_balance
        SET cash = cash + %s,
            pnl = pnl + %s,
            equity = cash + %s,
            roi = ((pnl + %s) / %s) * 100,
            updated_at = NOW()
        WHERE id = (SELECT id FROM paper_balance ORDER BY id DESC LIMIT 1)
    """, (amount, pnl, amount, pnl, START_CASH))


def run():
    try:
        print("▶️ Running Paper Trader V2 (AI action-based)...")

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        ensure_balance(cur)

        # ── 1. Check open positions: take profit / stop loss ──────────
        cur.execute("""
            SELECT id, market_id, entry_price, qty, invested
            FROM paper_positions
            WHERE status='OPEN'
        """)
        positions = cur.fetchall()

        closed = 0

        for pid, market_id, entry_price, qty, invested in positions:
            price = get_latest_price(cur, market_id)
            if price is None or price <= 0:
                continue

            entry_price = f(entry_price)
            qty = f(qty)
            invested = f(invested)
            pnl_pct = (price - entry_price) / entry_price

            if pnl_pct >= TAKE_PROFIT:
                close_position(cur, pid, market_id, price, qty, invested, "TAKE_PROFIT")
                closed += 1
            elif pnl_pct <= STOP_LOSS:
                close_position(cur, pid, market_id, price, qty, invested, "STOP_LOSS")
                closed += 1

        # ── 2. Open new positions from AI V2 BUY signals ──────────────
        cur.execute("""
            SELECT DISTINCT ON (a.market_id)
                a.market_id,
                a.ai_probability,
                a.confidence,
                a.raw->'analysis'->>'action' AS ai_action,
                a.reason
            FROM ai_analysis a
            JOIN markets m ON m.market_id = a.market_id
            WHERE m.active = true
              AND m.closed = false
              AND COALESCE(m.liquidity, 0) > 1000
            ORDER BY a.market_id, a.created_at DESC
        """)

        rows = cur.fetchall()

        # Count current open positions
        current_open = count_open_positions(cur)

        # Stats
        ai_buy_count = 0
        skipped_not_buy = 0
        skipped_duplicate = 0
        skipped_max_positions = 0
        skipped_low_confidence = 0
        opened = 0

        for market_id, probability, confidence, ai_action, reason in rows:
            probability = f(probability)
            confidence = f(confidence)

            # Primary gate: AI action must be BUY
            if ai_action != "BUY":
                skipped_not_buy += 1
                continue

            ai_buy_count += 1

            # Secondary gate: confidence sanity check
            if confidence < 60 or probability < 50:
                skipped_low_confidence += 1
                continue

            # No duplicate positions
            if already_open(cur, market_id):
                skipped_duplicate += 1
                continue

            # Max positions cap
            if current_open + opened >= MAX_OPEN_POSITIONS:
                skipped_max_positions += 1
                continue

            price = get_latest_price(cur, market_id)
            if price is None or price <= 0.05 or price >= 0.95:
                continue

            ok = open_position(cur, market_id, price, reason)
            if ok:
                opened += 1

        conn.commit()

        cur.execute("""
            SELECT cash, equity, pnl, roi
            FROM paper_balance
            ORDER BY id DESC
            LIMIT 1
        """)
        balance = cur.fetchone()

        cur.close()
        conn.close()

        print("✅ Paper Trader V2 Finished")
        print(f"Closed (TP/SL):          {closed}")
        print(f"AI BUY signals found:    {ai_buy_count}")
        print(f"  └─ Skipped (not BUY):  {skipped_not_buy}")
        print(f"  └─ Skipped (duplicate):{skipped_duplicate}")
        print(f"  └─ Skipped (max pos):  {skipped_max_positions}")
        print(f"  └─ Skipped (low conf): {skipped_low_confidence}")
        print(f"Opened:                  {opened}")
        print(f"Balance: cash={balance[0]}, equity={balance[1]}, pnl={balance[2]}, roi={balance[3]}")

        return {
            "closed": closed,
            "ai_buy_count": ai_buy_count,
            "skipped_not_buy": skipped_not_buy,
            "skipped_duplicate": skipped_duplicate,
            "skipped_max_positions": skipped_max_positions,
            "skipped_low_confidence": skipped_low_confidence,
            "opened": opened,
            "errors": 0,
        }

    except Exception:
        print("❌ Paper Trader V2 Failed")
        traceback.print_exc()
        return {"errors": 1}


if __name__ == "__main__":
    run()
