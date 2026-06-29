import traceback
import psycopg2

from backend.utils.config import DB_CONFIG
from backend.analyzer.signal_engine import SignalEngine


def run(limit=20):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT market_id FROM markets ORDER BY updated_at DESC LIMIT %s", (limit,))
        market_ids = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()

        engine = SignalEngine()
        results = engine.generate_signals_for_markets(market_ids, limit=limit)

        print("✅ Signal Engine Finished")
        print(f"Total tested: {results['total_tested']}")
        print(f"BUY: {results['buy_signals']}")
        print(f"SELL: {results['sell_signals']}")
        print(f"WATCH: {results['watch_signals']}")
        print(f"Errors: {results['errors']}")
        return results

    except Exception:
        print("❌ Signal Job Failed")
        traceback.print_exc()
        return {"errors": 1}
