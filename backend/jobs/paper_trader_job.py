import traceback
from backend.trading.paper_trader import run as run_paper_trader


def run():
    try:
        print("▶️ Running Paper Trader Job...")
        result = run_paper_trader()
        print("✅ Paper Trader Job Finished")
        return result
    except Exception:
        print("❌ Paper Trader Job Failed")
        traceback.print_exc()
        return {"errors": 1}
