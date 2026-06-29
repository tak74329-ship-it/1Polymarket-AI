import psycopg2
from backend.utils.config import DB_CONFIG


def run():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("\n===== PAPER BALANCE =====")
    cur.execute("""
        SELECT cash, equity, pnl, roi, updated_at
        FROM paper_balance
        ORDER BY id DESC
        LIMIT 1
    """)
    print(cur.fetchone())

    print("\n===== OPEN POSITIONS =====")
    cur.execute("""
        SELECT
            p.id,
            p.market_id,
            m.question,
            p.entry_price,
            latest.yes_price AS current_price,
            p.qty,
            p.invested,
            ((latest.yes_price - p.entry_price) / p.entry_price) * 100 AS pnl_pct,
            p.opened_at
        FROM paper_positions p
        LEFT JOIN markets m ON m.market_id = p.market_id
        LEFT JOIN LATERAL (
            SELECT yes_price
            FROM market_prices mp
            WHERE mp.market_id = p.market_id
            ORDER BY mp.created_at DESC
            LIMIT 1
        ) latest ON true
        WHERE p.status = 'OPEN'
        ORDER BY p.opened_at DESC
    """)
    for r in cur.fetchall():
        print(r)

    print("\n===== RECENT ORDERS =====")
    cur.execute("""
        SELECT market_id, side, price, qty, amount, reason, created_at
        FROM paper_orders
        ORDER BY id DESC
        LIMIT 20
    """)
    for r in cur.fetchall():
        print(r)

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
