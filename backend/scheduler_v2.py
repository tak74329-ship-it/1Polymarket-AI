"""Scheduler V2 — auto-run the complete pipeline with config-driven intervals."""

import os
import sys
import time
import json
import logging
import traceback
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

from backend.utils.config import load_trading_config

CFG = load_trading_config()

# ── Job imports (unchanged) ──────────────────────────────────────────
from backend.jobs.collector_job import run as collector_job
from backend.jobs.orderbook_job import run as orderbook_job
from backend.jobs.signal_job import run as signal_job
from backend.jobs.feature_job import run as feature_job
from backend.jobs.ai_job import run as ai_job
from backend.jobs.paper_trader_job import run as paper_trader_job
from backend.jobs.news_job import run as news_job
from backend.jobs.market_keyword_job import run as market_keyword_job
from backend.jobs.news_market_match_job import run as news_match_job
from backend.jobs.news_signal_job import run as news_signal_job

# ── Logging setup ───────────────────────────────────────────────────
LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

log_filename = os.path.join(LOGS_DIR, f"scheduler_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("scheduler_v2")

MAX_RETRIES = 2
RETRY_DELAY_SEC = 30
PIPELINE_INTERVAL_MINUTES = CFG.get("scheduler_market_interval_minutes", 5)
NEWS_INTERVAL_MINUTES = CFG.get("scheduler_news_interval_minutes", 30)


def safe_run(name: str, func, *args, **kwargs) -> dict:
    """Run a job with retry logic and structured logging."""
    last_error = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            log.info("▶️  %s (attempt %d/%d)", name, attempt + 1, 1 + MAX_RETRIES)
            result = func(*args, **kwargs)
            if isinstance(result, dict) and result.get("errors", 0) > 0:
                log.warning("⚠️  %s completed with %d error(s): %s", name, result["errors"], result)
            else:
                log.info("✅  %s finished: %s", name, result)
            return result if result else {}
        except Exception as e:
            last_error = e
            log.error("❌  %s failed (attempt %d/%d): %s", name, attempt + 1, 1 + MAX_RETRIES, e)
            traceback.print_exc()
            if attempt < MAX_RETRIES:
                log.info("🔄  Retrying %s in %ds...", name, RETRY_DELAY_SEC)
                time.sleep(RETRY_DELAY_SEC)

    log.critical("💥  %s failed after %d attempts: %s", name, 1 + MAX_RETRIES, last_error)
    return {"errors": 1, "last_error": str(last_error)}


def trigger_dashboard_refresh():
    """Hit the dashboard to warm up its cache for the next browser poll."""
    try:
        import urllib.request
        endpoints = [
            "http://localhost:8080/api/health",
            "http://localhost:8080/api/portfolio",
            "http://localhost:8080/api/positions",
            "http://localhost:8080/api/ai-decisions",
            "http://localhost:8080/api/ranked-markets",
            "http://localhost:8080/api/news-matches",
            "http://localhost:8080/api/performance",
        ]
        for ep in endpoints:
            try:
                urllib.request.urlopen(ep, timeout=5)
            except Exception:
                pass  # Dashboard may not be running
        log.info("🔁  Dashboard data refreshed")
    except Exception:
        pass


def market_pipeline():
    """Full market data + signals + AI + trading pipeline."""
    log.info("=" * 60)
    log.info("🏁  MARKET PIPELINE START")
    log.info("=" * 60)

    steps = [
        ("Collector", collector_job),
        ("OrderBook", orderbook_job),
        ("Signals", signal_job, 50),
        ("Features", feature_job, 50),
        ("AI Engine", ai_job, 20),
        ("Paper Trader", paper_trader_job),
    ]

    results = {}
    for step in steps:
        name = step[0]
        func = step[1]
        args = step[2:] if len(step) > 2 else []
        kwargs = step[3] if len(step) > 3 else {}
        if isinstance(args, dict):
            kwargs = args
            args = []
        results[name] = safe_run(name, func, *args, **(kwargs if isinstance(kwargs, dict) else {}))
        log.info("")

    log.info("=" * 60)
    log.info("🏁  MARKET PIPELINE END")
    log.info("=" * 60)

    trigger_dashboard_refresh()

    return results


def news_pipeline():
    """News keyword extraction + fetch + match + signal."""
    log.info("=" * 60)
    log.info("📰  NEWS PIPELINE START")
    log.info("=" * 60)

    steps = [
        ("Market Keywords", market_keyword_job, 2100),
        ("News Fetch", news_job, 50),
        ("News Match", news_match_job, 200, 2100),
        ("News Signal", news_signal_job, 200),
    ]

    results = {}
    for step in steps:
        name = step[0]
        func = step[1]
        args = step[2:] if len(step) > 2 else []
        kwargs = step[3] if len(step) > 3 else {}
        if isinstance(args, dict):
            kwargs = args
            args = []
        results[name] = safe_run(name, func, *args, **(kwargs if isinstance(kwargs, dict) else {}))
        log.info("")

    log.info("=" * 60)
    log.info("📰  NEWS PIPELINE END")
    log.info("=" * 60)

    trigger_dashboard_refresh()

    return results


def run_market_pipeline():
    """Wrapper for APScheduler."""
    try:
        market_pipeline()
    except Exception:
        log.critical("💥  Market pipeline crashed")
        traceback.print_exc()


def run_news_pipeline():
    """Wrapper for APScheduler."""
    try:
        news_pipeline()
    except Exception:
        log.critical("💥  News pipeline crashed")
        traceback.print_exc()


def main():
    log.info("=" * 60)
    log.info("🚀  SCHEDULER V2 STARTING")
    log.info("=" * 60)
    log.info("Log file: %s", log_filename)
    log.info("Market pipeline: every %d minutes", PIPELINE_INTERVAL_MINUTES)
    log.info("News pipeline:   every %d minutes", NEWS_INTERVAL_MINUTES)
    log.info("Max retries per job: %d", MAX_RETRIES)
    log.info("=" * 60)

    scheduler = BlockingScheduler()

    scheduler.add_job(
        run_market_pipeline,
        "interval",
        minutes=PIPELINE_INTERVAL_MINUTES,
        id="market_pipeline_v2",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )

    scheduler.add_job(
        run_news_pipeline,
        "interval",
        minutes=NEWS_INTERVAL_MINUTES,
        id="news_pipeline_v2",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    # Run once immediately on startup
    log.info("▶️  Running initial market pipeline...")
    market_pipeline()
    log.info("▶️  Running initial news pipeline...")
    news_pipeline()

    log.info("✅  Scheduler V2 running. Press Ctrl+C to stop.")
    log.info("=" * 60)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("🛑  Scheduler V2 stopped by user.")
    except Exception:
        log.critical("💥  Scheduler V2 crashed")
        traceback.print_exc()


if __name__ == "__main__":
    main()
