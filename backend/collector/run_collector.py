import psycopg2
from psycopg2.extras import Json
from backend.utils.config import DB_CONFIG
from backend.collector.polymarket_collector import fetch_markets, save_markets

def log(component, level, message, raw=None):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO system_logs (component, level, message, raw)
        VALUES (%s, %s, %s, %s)
        """,
        (component, level, message, Json(raw or {}))
    )
    conn.commit()
    cur.close()
    conn.close()

def main():
    try:
        markets = fetch_markets()
        stats = save_markets(markets)
        
        # Print clear statistics
        print(f"Total fetched: {stats['total_fetched']}")
        print(f"Inserted: {stats['inserted_count']}")
        print(f"Updated: {stats['updated_count']}")
        print(f"Skipped: {stats['skipped_count']}")
        print(f"Price snapshots: {stats['price_snapshots_count']}")
        
        # Log to system_logs with statistics
        msg = f"Collected {stats['total_fetched']} markets: {stats['inserted_count']} new, {stats['updated_count']} updated, {stats['skipped_count']} skipped"
        log("polymarket_collector", "INFO", msg, stats)
        print("✅", msg)
    except Exception as e:
        log("polymarket_collector", "ERROR", str(e))
        print("❌ Collector failed:", e)

if __name__ == "__main__":
    main()
