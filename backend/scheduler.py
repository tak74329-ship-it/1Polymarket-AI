import traceback
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

from backend.jobs.collector_job import run as collector_job
from backend.jobs.signal_job import run as signal_job
from backend.jobs.orderbook_job import run as orderbook_job
from backend.jobs.news_job import run as news_job
from backend.jobs.news_market_match_job import run as news_match_job
from backend.jobs.news_signal_job import run as news_signal_job
from backend.jobs.feature_job import run as feature_job
from backend.jobs.ai_job import run as ai_job
from backend.jobs.paper_trader_job import run as paper_trader_job


def safe_run(name, func, *args, **kwargs):
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ▶️ Starting {name}")
    try:
        result = func(*args, **kwargs)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Finished {name}: {result}")
    except Exception:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Failed {name}")
        traceback.print_exc()


def market_pipeline():
    safe_run("Collector Job", collector_job)
    safe_run("OrderBook Job", orderbook_job)
    safe_run("Signal Job", signal_job, 20)
    safe_run("Feature Job", feature_job, 20)
    safe_run("AI Job", ai_job, 10)
    safe_run("Paper Trader Job", paper_trader_job)


def news_pipeline():
    safe_run("News Job", news_job)
    safe_run("News Match Job", news_match_job)
    safe_run("News Signal Job", news_signal_job)


def main():
    scheduler = BlockingScheduler()

    scheduler.add_job(
        market_pipeline,
        "interval",
        minutes=1,
        id="market_pipeline",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    scheduler.add_job(
        news_pipeline,
        "interval",
        minutes=10,
        id="news_pipeline",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )

    print("✅ Scheduler V2 started")
    print("Market pipeline: every 1 minute")
    print("News pipeline: every 10 minutes")
    print("Press Ctrl+C to stop")

    market_pipeline()
    news_pipeline()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped.")


if __name__ == "__main__":
    main()
