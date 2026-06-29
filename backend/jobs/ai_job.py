import traceback
from backend.ai.ai_engine import run as run_ai_engine


def run(limit=10):
    try:
        return run_ai_engine(limit=limit)
    except Exception:
        print("❌ AI Job Failed")
        traceback.print_exc()
        return {"errors": 1}
