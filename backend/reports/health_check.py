import psycopg2
from backend.utils.config import DB_CONFIG

TABLES = [
    "markets",
    "market_prices",
    "order_books",
    "news_items",
    "news_market_matches",
    "market_keywords",
    "signals",
    "ai_analysis",
    "market_features",
    "paper_positions",
    "paper_orders",
    "paper_balance",
    "system_logs",
]

def run():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("\n===== SYSTEM HEALTH CHECK =====")
    for table in TABLES:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"{table}: {cur.fetchone()[0]}")

    print("\n===== LATEST DATA =====")
    checks = [
        ("Latest market price", "SELECT MAX(created_at) FROM market_prices"),
        ("Latest order book", "SELECT MAX(created_at) FROM order_books"),
        ("Latest news", "SELECT MAX(created_at) FROM news_items"),
        ("Latest news match", "SELECT MAX(created_at) FROM news_market_matches"),
        ("Latest signal", "SELECT MAX(created_at) FROM signals"),
        ("Latest AI analysis", "SELECT MAX(created_at) FROM ai_analysis"),
        ("Latest feature", "SELECT MAX(created_at) FROM market_features"),
        ("Latest paper order", "SELECT MAX(created_at) FROM paper_orders"),
    ]

    for name, sql in checks:
        cur.execute(sql)
        print(f"{name}: {cur.fetchone()[0]}")

    print("\n===== PAPER BALANCE =====")
    cur.execute("""
        SELECT cash, equity, pnl, roi, updated_at
        FROM paper_balance
        ORDER BY id DESC
        LIMIT 1
    """)
    print(cur.fetchone())

    cur.close()
    conn.close()

if __name__ == "__main__":
    run()
