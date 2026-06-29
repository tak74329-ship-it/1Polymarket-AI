import traceback
from backend.features.feature_engine import run as run_feature_engine


def run(limit=20):
    try:
        print("▶️ Running Feature Job...")
        result = run_feature_engine(limit=limit)
        print("✅ Feature Job Finished")
        return {"errors": 0}
    except Exception:
        print("❌ Feature Job Failed")
        traceback.print_exc()
        return {"errors": 1}
