"""Market data scraping scheduler with composite risk score calculation."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..utils.config import settings
from ..utils.logger import get_logger
from .store import read_all_metrics, write_metric, is_metric_stale
from .scrape_fred import run_fred_scraper
from .scrape_bls import run_bls_scraper
from .scrape_cox import run_cox_automotive_scraper
from .scrape_student_loans import run_student_loan_scraper
from .scrape_personal_loans import run_personal_loan_scraper
from .scrape_realestate import run_real_estate_scraper

logger = get_logger(__name__)


class MarketDataScheduler:
    """Scheduler for market data scraping and risk score calculation."""
    
    def __init__(self, background: bool = True):
        self.scheduler = BackgroundScheduler() if background else BlockingScheduler()
        self.last_run_results: Dict[str, bool] = {}
        
    def calculate_market_risk_score(self) -> Optional[float]:
        """
        Calculate composite market risk score from individual metrics.
        
        Returns:
            Market risk score (0.0 = low risk, 1.0 = high risk) or None if insufficient data
        """
        logger.info("calculating_market_risk_score")
        
        try:
            # Read all current metrics
            metrics = read_all_metrics()
            
            # Updated for U.S./Oklahoma metrics
            required_metrics = ["fed_funds_rate", "oklahoma_cpi_yoy", "okc_home_price_index"]
            missing_metrics = [m for m in required_metrics if m not in metrics]
            
            if missing_metrics:
                logger.warning("missing_metrics_for_risk_score", missing=missing_metrics)
                return None
            
            # Extract values
            fed_funds_rate = metrics["fed_funds_rate"]["value"]
            oklahoma_cpi_yoy = metrics["oklahoma_cpi_yoy"]["value"]
            okc_home_price_index = metrics["okc_home_price_index"]["value"]
            
            # Check for stale data
            stale_threshold_hours = settings.scrape.stale_threshold_hours
            stale_metrics = []
            for metric_key in required_metrics:
                if is_metric_stale(metric_key, stale_threshold_hours):
                    stale_metrics.append(metric_key)
            
            market_stale = len(stale_metrics) > 0
            
            # Normalize individual metrics to 0-1 risk scale
            # Higher values = higher risk in this context
            
            # Federal Funds Rate normalization (higher rates = higher risk for borrowers)
            # Typical range: 0% - 8%, risk increases with rate
            fed_risk = self._normalize_value(fed_funds_rate, min_val=0.0, max_val=8.0, higher_is_risk=True)
            
            # Oklahoma CPI YoY normalization (higher inflation = higher risk)
            # Typical range: -2% to 8%, risk increases with inflation
            cpi_risk = self._normalize_value(oklahoma_cpi_yoy, min_val=-2.0, max_val=8.0, higher_is_risk=True)
            
            # Oklahoma City Home Price Index normalization (rapid changes = higher risk)
            # Use year-over-year change as risk indicator
            # Get previous year data if available for trend calculation
            okc_trend_risk = 0.5  # Default middle risk if no trend data
            
            try:
                # Try to calculate YoY home price change
                home_price_trend = (okc_home_price_index - 100) / 100  # Deviation from baseline
                okc_trend_risk = self._normalize_value(abs(home_price_trend), min_val=0.0, max_val=0.5, higher_is_risk=True)
            except:
                logger.debug("home_price_trend_calculation_fallback")
            
            # Weighted composite risk score
            # Updated weights for U.S. market: Fed rate 40%, CPI 35%, Home prices 25%
            weights = {
                "fed_weight": 0.4,
                "cpi_weight": 0.35,
                "home_weight": 0.25
            }
            
            # Allow configuration override
            if hasattr(settings, 'risk') and hasattr(settings.risk, 'market_weights'):
                weights.update(settings.risk.market_weights)
            
            market_risk_score = (
                weights["fed_weight"] * fed_risk +
                weights["cpi_weight"] * cpi_risk +
                weights["home_weight"] * okc_trend_risk
            )
            
            # Ensure score is in valid range
            market_risk_score = max(0.0, min(1.0, market_risk_score))
            
            # Store the computed risk score
            extra_data = {
                "components": {
                    "fed_funds_rate": fed_funds_rate,
                    "fed_risk": fed_risk,
                    "oklahoma_cpi_yoy": oklahoma_cpi_yoy,
                    "cpi_risk": cpi_risk,
                    "okc_home_price_index": okc_home_price_index,
                    "home_price_risk": okc_trend_risk,
                },
                "weights": weights,
                "market_stale": market_stale,
                "stale_metrics": stale_metrics,
                "calculation_version": "2.0_us_oklahoma"
            }
            
            write_metric("market_risk_score", market_risk_score, extra_json=extra_data)
            
            logger.info(
                "market_risk_score_calculated",
                score=market_risk_score,
                fed_risk=fed_risk,
                cpi_risk=cpi_risk,
                home_price_risk=okc_trend_risk,
                market_stale=market_stale
            )
            
            return market_risk_score
            
        except Exception as e:
            logger.error("market_risk_calculation_failed", error=str(e))
            return None
    
    def _normalize_value(
        self,
        value: float,
        min_val: float,
        max_val: float,
        higher_is_risk: bool = True
    ) -> float:
        """
        Normalize a value to 0-1 risk scale.
        
        Args:
            value: Value to normalize
            min_val: Minimum expected value
            max_val: Maximum expected value
            higher_is_risk: If True, higher values = higher risk
        
        Returns:
            Normalized risk score (0.0 - 1.0)
        """
        # Clamp value to expected range
        clamped_value = max(min_val, min(max_val, value))
        
        # Normalize to 0-1
        if max_val == min_val:
            normalized = 0.5  # Default to medium risk if no range
        else:
            normalized = (clamped_value - min_val) / (max_val - min_val)
        
        # Invert if lower values indicate higher risk
        if not higher_is_risk:
            normalized = 1.0 - normalized
        
        return normalized
    
    def run_all_scrapers(self):
        """Run all market data scrapers and calculate risk score."""
        logger.info("starting_scheduled_scrape_job")
        
        scrape_results = {}
        
        # Run U.S./Oklahoma market data scrapers
        scrapers = [
            ("fred_data", run_fred_scraper),
            ("bls_data", run_bls_scraper),
            ("cox_automotive", run_cox_automotive_scraper),
            ("student_loans", run_student_loan_scraper),
            ("personal_loans", run_personal_loan_scraper),
            ("real_estate", run_real_estate_scraper)
        ]
        
        for metric_name, scraper_func in scrapers:
            try:
                logger.info("running_scraper", metric=metric_name)
                
                # All new scrapers are async
                if asyncio.iscoroutinefunction(scraper_func):
                    success = asyncio.run(scraper_func())
                else:
                    success = scraper_func()
                
                scrape_results[metric_name] = success
                
                if success:
                    logger.info("scraper_completed", metric=metric_name)
                else:
                    logger.warning("scraper_failed", metric=metric_name)
                    
            except Exception as e:
                logger.error("scraper_exception", metric=metric_name, error=str(e))
                scrape_results[metric_name] = False
        
        # Calculate market risk score
        try:
            risk_score = self.calculate_market_risk_score()
            if risk_score is not None:
                logger.info("market_risk_score_updated", score=risk_score)
            else:
                logger.warning("market_risk_score_calculation_failed")
        except Exception as e:
            logger.error("risk_score_calculation_exception", error=str(e))
        
        # Store run results
        self.last_run_results = scrape_results
        self.last_run_results['risk_score_calculated'] = risk_score is not None
        
        successful_scrapers = sum(1 for success in scrape_results.values() if success)
        total_scrapers = len(scrape_results)
        
        logger.info(
            "scheduled_scrape_job_completed",
            successful_scrapers=successful_scrapers,
            total_scrapers=total_scrapers,
            success_rate=successful_scrapers / total_scrapers if total_scrapers > 0 else 0
        )
    
    def start(self):
        """Start the scheduler."""
        logger.info("starting_market_data_scheduler")
        
        # Parse cron schedule from settings
        cron_schedule = settings.scrape.schedule_cron  # "0 8,14 * * *"
        
        # Add the scheduled job
        self.scheduler.add_job(
            self.run_all_scrapers,
            trigger=CronTrigger.from_crontab(cron_schedule),
            id="market_data_scrape",
            name="Market Data Scraping Job",
            max_instances=1,  # Prevent overlapping runs
            coalesce=True,    # Combine missed runs
            misfire_grace_time=300  # 5 minutes grace for missed jobs
        )
        
        job = self.scheduler.get_job("market_data_scrape")
        next_run = getattr(job, 'next_run_time', None) if job else None
        logger.info(
            "scheduler_configured",
            schedule=cron_schedule,
            next_run=next_run
        )
        
        self.scheduler.start()
        logger.info("market_data_scheduler_started")
    
    def stop(self):
        """Stop the scheduler."""
        logger.info("stopping_market_data_scheduler")
        self.scheduler.shutdown(wait=True)
        logger.info("market_data_scheduler_stopped")
    
    def run_once(self):
        """Run scrapers once (for testing/manual execution)."""
        logger.info("running_scrapers_once")
        self.run_all_scrapers()
    
    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status and last run results."""
        if not self.scheduler.running:
            return {"status": "stopped", "last_results": self.last_run_results}
        
        job = self.scheduler.get_job("market_data_scrape")
        
        return {
            "status": "running",
            "next_run": str(job.next_run_time) if job else None,
            "last_results": self.last_run_results,
            "jobs_count": len(self.scheduler.get_jobs())
        }


# Global scheduler instance
_scheduler: Optional[MarketDataScheduler] = None


def get_scheduler() -> MarketDataScheduler:
    """Get global scheduler instance (singleton pattern)."""
    global _scheduler
    if _scheduler is None:
        _scheduler = MarketDataScheduler(background=True)
    return _scheduler


def start_market_data_scheduler():
    """Start the global market data scheduler."""
    scheduler = get_scheduler()
    scheduler.start()


def stop_market_data_scheduler():
    """Stop the global market data scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        _scheduler = None


if __name__ == "__main__":
    # CLI for testing and manual operation
    import argparse
    
    parser = argparse.ArgumentParser(description="Market data scheduler")
    parser.add_argument("--run-once", action="store_true", help="Run scrapers once and exit")
    parser.add_argument("--start", action="store_true", help="Start scheduled scraping")
    parser.add_argument("--status", action="store_true", help="Show scheduler status")
    
    args = parser.parse_args()
    
    scheduler = MarketDataScheduler(background=False)
    
    if args.run_once:
        print("🔄 Running all scrapers once...")
        scheduler.run_once()
        print("✅ Scraping completed")
        
    elif args.start:
        print("🚀 Starting market data scheduler...")
        print(f"📅 Schedule: {settings.scrape.schedule_cron}")
        try:
            scheduler.start()
            print("⏰ Scheduler started. Press Ctrl+C to stop.")
            # Keep running until interrupted
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping scheduler...")
            scheduler.stop()
            print("✅ Scheduler stopped")
            
    elif args.status:
        # For status, we need a background scheduler
        bg_scheduler = get_scheduler()
        status = bg_scheduler.get_status()
        print(f"Status: {status['status']}")
        if status.get('next_run'):
            print(f"Next run: {status['next_run']}")
        if status.get('last_results'):
            print("Last results:")
            for metric, success in status['last_results'].items():
                print(f"  {metric}: {'✅' if success else '❌'}")
                
    else:
        parser.print_help() 