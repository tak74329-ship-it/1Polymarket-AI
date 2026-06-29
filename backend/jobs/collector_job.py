import traceback
from backend.collector.run_collector import main as run_collector


def run():
    try:
        print("▶️ Running Collector Job...")
        run_collector()
        print("✅ Collector Job Finished")
        return {"errors": 0}
    except Exception:
        print("❌ Collector Job Failed")
        traceback.print_exc()
        return {"errors": 1}
