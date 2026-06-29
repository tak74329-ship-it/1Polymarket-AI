import traceback
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from backend.collector import run_collector


def job_wrapper():
    """Wrapper function for scheduled jobs with logging and error handling."""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting collector job...")
    
    try:
        run_collector.main()
        print("Collector Finished")
    except Exception as e:
        print(f"Collector Failed: {e}")
        print("Full traceback:")
        traceback.print_exc()


def run_polymarket_collector():
    """Run Polymarket collector job."""
    job_wrapper()


def run_feedly_collector():
    """Run Feedly collector job (placeholder for future implementation)."""
    job_wrapper()


def run_openbb_collector():
    """Run OpenBB collector job (placeholder for future implementation)."""
    job_wrapper()


def run_redroom_collector():
    """Run Redroom collector job (placeholder for future implementation)."""
    job_wrapper()


def main():
    """Initialize and start the APScheduler."""
    scheduler = BlockingScheduler()
    
    # Schedule Polymarket collector to run every 1 minute
    # misfire_grace_time=60 allows the job to run even if it missed its scheduled time
    scheduler.add_job(
        run_polymarket_collector,
        'interval',
        minutes=1,
        id='polymarket_collector',
        name='Polymarket Collector',
        misfire_grace_time=60,
        coalesce=True,
        max_instances=1
    )
    
    print("Scheduler started. Press Ctrl+C to exit.")
    
    # Run immediately on startup without waiting for the first interval
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running initial collector job...")
    try:
        run_collector.main()
        print("Collector Finished")
    except Exception as e:
        print(f"Collector Failed: {e}")
        print("Full traceback:")
        traceback.print_exc()
    
    # Start the scheduler (blocking)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler shutdown.")


if __name__ == "__main__":
    main()
