import traceback
from backend.collector.orderbook_collector import main as run_orderbook


def run():
    try:
        print("▶️ Running OrderBook Job...")
        run_orderbook()
        print("✅ OrderBook Job Finished")
        return {"errors": 0}
    except Exception:
        print("❌ OrderBook Job Failed")
        traceback.print_exc()
        return {"errors": 1}
