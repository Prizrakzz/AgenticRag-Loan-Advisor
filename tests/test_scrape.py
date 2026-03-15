"""Tests for market data scraping functionality."""

import pytest
import tempfile
import sqlite3
import json
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

from app.scrape.store import MarketDataStore, write_metric, read_metric, read_all_metrics
from app.scrape.scrape_cbj import scrape_cbj_rate, update_cbj_rate
from app.scrape.scrape_cpi import scrape_cpi_data, update_cpi_data
from app.scrape.scrape_realestate import scrape_real_estate_index, update_real_estate_index
from app.scrape.scheduler import MarketDataScheduler


class TestMarketDataStore:
    """Test SQLite storage for market data."""
    
    def test_store_initialization(self):
        """Test store initialization and table creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_market.db"
            store = MarketDataStore(str(db_path))
            
            # Check database file exists
            assert db_path.exists()
            
            # Check table exists
            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='market_snapshot'"
                )
                assert cursor.fetchone() is not None
    
    def test_write_and_read_metric(self):
        """Test writing and reading metrics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_market.db"
            store = MarketDataStore(str(db_path))
            
            # Write metric
            success = store.write_metric(
                "test_rate", 
                7.25, 
                asof="2024-01-01T12:00:00Z",
                extra_json={"source": "test"}
            )
            assert success is True
            
            # Read metric
            metric = store.read_metric("test_rate")
            assert metric is not None
            assert metric["key"] == "test_rate"
            assert metric["value"] == 7.25
            assert metric["asof"] == "2024-01-01T12:00:00Z"
            assert metric["extra"]["source"] == "test"
    
    def test_read_all_metrics(self):
        """Test reading all metrics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_market.db"
            store = MarketDataStore(str(db_path))
            
            # Write multiple metrics
            store.write_metric("cbj_rate", 7.25)
            store.write_metric("cpi_yoy", 3.5)
            store.write_metric("re_index", 125.0)
            
            # Read all
            metrics = store.read_all_metrics()
            assert len(metrics) == 3
            assert "cbj_rate" in metrics
            assert "cpi_yoy" in metrics
            assert "re_index" in metrics
    
    def test_metric_staleness(self):
        """Test metric staleness checking."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_market.db"
            store = MarketDataStore(str(db_path))
            
            # Write fresh metric
            fresh_time = datetime.utcnow().isoformat() + "Z"
            store.write_metric("fresh_metric", 100.0, asof=fresh_time)
            
            # Write stale metric
            stale_time = (datetime.utcnow() - timedelta(hours=72)).isoformat() + "Z"
            store.write_metric("stale_metric", 200.0, asof=stale_time)
            
            # Check staleness
            assert store.is_metric_stale("fresh_metric", max_age_hours=48) is False
            assert store.is_metric_stale("stale_metric", max_age_hours=48) is True
            assert store.is_metric_stale("nonexistent_metric", max_age_hours=48) is True
    
    def test_upsert_behavior(self):
        """Test that writing same key updates the value."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_market.db"
            store = MarketDataStore(str(db_path))
            
            # Write initial value
            store.write_metric("test_metric", 100.0)
            
            # Update value
            store.write_metric("test_metric", 200.0)
            
            # Should only have one record with updated value
            metric = store.read_metric("test_metric")
            assert metric["value"] == 200.0
            
            all_metrics = store.read_all_metrics()
            assert len(all_metrics) == 1


class TestCBJScraper:
    """Test CBJ interest rate scraper."""
    
    @patch('app.scrape.scrape_cbj.aiohttp.ClientSession')
    async def test_scrape_cbj_rate_success(self, mock_session):
        """Test successful CBJ rate scraping."""
        # Mock HTML response with rate table
        mock_html = """
        <html>
            <body>
                <table>
                    <tr><th>Main Interest Rate</th><td>7.25%</td></tr>
                    <tr><th>Deposit Rate</th><td>6.5%</td></tr>
                </table>
            </body>
        </html>
        """
        
        # Mock aiohttp response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=mock_html)
        
        mock_session_instance = AsyncMock()
        mock_session_instance.get.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        # Test scraping
        rate = await scrape_cbj_rate()
        
        assert rate == 7.25
    
    @patch('app.scrape.scrape_cbj.aiohttp.ClientSession')
    async def test_scrape_cbj_rate_no_data(self, mock_session):
        """Test CBJ scraping when no rate found."""
        # Mock HTML response without rate
        mock_html = "<html><body><p>No rate data available</p></body></html>"
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=mock_html)
        
        mock_session_instance = AsyncMock()
        mock_session_instance.get.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        # Test scraping
        rate = await scrape_cbj_rate()
        
        assert rate is None
    
    @patch('app.scrape.scrape_cbj.aiohttp.ClientSession')
    async def test_scrape_cbj_rate_http_error(self, mock_session):
        """Test CBJ scraping with HTTP error."""
        mock_response = AsyncMock()
        mock_response.status = 404
        
        mock_session_instance = AsyncMock()
        mock_session_instance.get.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        # Test scraping
        rate = await scrape_cbj_rate()
        
        assert rate is None
    
    @patch('app.scrape.scrape_cbj.scrape_cbj_rate')
    @patch('app.scrape.store.write_metric')
    async def test_update_cbj_rate(self, mock_write, mock_scrape):
        """Test CBJ rate update and storage."""
        mock_scrape.return_value = 7.25
        mock_write.return_value = True
        
        success = await update_cbj_rate()
        
        assert success is True
        mock_scrape.assert_called_once()
        mock_write.assert_called_once_with(
            "cbj_rate", 
            7.25, 
            extra_json={
                "source": "cbj_official",
                "url": "https://www.cbj.gov.jo/en/Pages/Maininterestrates",
                "scraper_version": "1.0"
            }
        )


class TestCPIScraper:
    """Test CPI scraper."""
    
    @patch('app.scrape.scrape_cpi.aiohttp.ClientSession')
    async def test_scrape_cpi_data_success(self, mock_session):
        """Test successful CPI data scraping."""
        # Mock HTML response with CPI article
        mock_html = """
        <html>
            <body>
                <article>
                    <h2>CPI Report for January 2024</h2>
                    <p>Consumer Price Index increased by 3.2% year-over-year in January 2024.</p>
                </article>
            </body>
        </html>
        """
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=mock_html)
        
        mock_session_instance = AsyncMock()
        mock_session_instance.get.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        # Test scraping
        result = await scrape_cpi_data()
        
        assert result is not None
        cpi_percent, period = result
        assert cpi_percent == 3.2
        assert period  # Should have some period value
    
    @patch('app.scrape.scrape_cpi.aiohttp.ClientSession')
    async def test_scrape_cpi_data_table_format(self, mock_session):
        """Test CPI scraping from table format."""
        mock_html = """
        <html>
            <body>
                <table>
                    <tr><th>Metric</th><th>Value</th></tr>
                    <tr><td>CPI Inflation Rate</td><td>2.8%</td></tr>
                </table>
            </body>
        </html>
        """
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=mock_html)
        
        mock_session_instance = AsyncMock()
        mock_session_instance.get.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        # Test scraping
        result = await scrape_cpi_data()
        
        assert result is not None
        cpi_percent, period = result
        assert cpi_percent == 2.8


class TestRealEstateScraper:
    """Test real estate index scraper."""
    
    @patch('app.scrape.scrape_realestate.aiohttp.ClientSession')
    async def test_scrape_real_estate_index_success(self, mock_session):
        """Test successful real estate index scraping."""
        mock_html = """
        <html>
            <body>
                <table>
                    <tr><th>Period</th><th>Real Estate Price Index</th></tr>
                    <tr><td>Q1 2024</td><td>125.4</td></tr>
                </table>
            </body>
        </html>
        """
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=mock_html)
        
        mock_session_instance = AsyncMock()
        mock_session_instance.get.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        # Test scraping
        result = await scrape_real_estate_index()
        
        assert result is not None
        index_value, period = result
        assert index_value == 125.4
        assert period  # Should have some period value
    
    @patch('app.scrape.scrape_realestate.aiohttp.ClientSession')
    async def test_scrape_real_estate_index_script_data(self, mock_session):
        """Test real estate index scraping from script data."""
        mock_html = """
        <html>
            <body>
                <script>
                    var chart_data = {
                        real_estate_index: [120.5, 125.0, 130.2],
                        periods: ["Q4 2023", "Q1 2024", "Q2 2024"]
                    };
                </script>
            </body>
        </html>
        """
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=mock_html)
        
        mock_session_instance = AsyncMock()
        mock_session_instance.get.return_value.__aenter__.return_value = mock_response
        mock_session.return_value.__aenter__.return_value = mock_session_instance
        
        # Test scraping
        result = await scrape_real_estate_index()
        
        assert result is not None
        index_value, period = result
        # Should find one of the index values in the reasonable range
        assert 120.0 <= index_value <= 135.0


class TestScheduler:
    """Test market data scheduler."""
    
    def test_scheduler_initialization(self):
        """Test scheduler initialization."""
        scheduler = MarketDataScheduler(background=True)
        
        assert scheduler.scheduler is not None
        assert scheduler.last_run_results == {}
    
    def test_market_risk_score_calculation(self):
        """Test market risk score calculation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set up test database
            db_path = Path(temp_dir) / "test_market.db"
            store = MarketDataStore(str(db_path))
            
            # Write test metrics
            store.write_metric("cbj_rate", 8.5)  # Higher rate = higher risk
            store.write_metric("cpi_yoy", 4.0)   # Higher inflation = higher risk  
            store.write_metric("re_price_index", 150.0)  # 50% above baseline = higher risk
            
            # Patch the global store to use our test store
            with patch('app.scrape.scheduler.read_all_metrics', store.read_all_metrics):
                with patch('app.scrape.scheduler.is_metric_stale', store.is_metric_stale):
                    with patch('app.scrape.scheduler.write_metric', store.write_metric):
                        scheduler = MarketDataScheduler()
                        risk_score = scheduler.calculate_market_risk_score()
            
            # Should calculate a risk score
            assert risk_score is not None
            assert 0.0 <= risk_score <= 1.0
            
            # Check that computed score was stored
            stored_risk = store.read_metric("market_risk_score")
            assert stored_risk is not None
            assert stored_risk["value"] == risk_score
    
    def test_market_risk_score_missing_data(self):
        """Test market risk score calculation with missing data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_market.db"
            store = MarketDataStore(str(db_path))
            
            # Only write partial data
            store.write_metric("cbj_rate", 8.5)
            # Missing CPI and real estate data
            
            with patch('app.scrape.scheduler.read_all_metrics', store.read_all_metrics):
                scheduler = MarketDataScheduler()
                risk_score = scheduler.calculate_market_risk_score()
            
            # Should return None due to missing data
            assert risk_score is None
    
    @patch('app.scrape.scheduler.run_cbj_scraper')
    @patch('app.scrape.scheduler.run_cpi_scraper')
    @patch('app.scrape.scheduler.run_real_estate_scraper')
    def test_run_all_scrapers(self, mock_re, mock_cpi, mock_cbj):
        """Test running all scrapers."""
        # Mock scraper success
        mock_cbj.return_value = True
        mock_cpi.return_value = True
        mock_re.return_value = False  # One failure
        
        scheduler = MarketDataScheduler()
        
        with patch.object(scheduler, 'calculate_market_risk_score', return_value=0.5):
            scheduler.run_all_scrapers()
        
        # Check that all scrapers were called
        mock_cbj.assert_called_once()
        mock_cpi.assert_called_once()
        mock_re.assert_called_once()
        
        # Check results
        assert scheduler.last_run_results['cbj_rate'] is True
        assert scheduler.last_run_results['cpi_yoy'] is True
        assert scheduler.last_run_results['re_price_index'] is False
        assert scheduler.last_run_results['risk_score_calculated'] is True
    
    def test_normalize_value(self):
        """Test value normalization for risk scoring."""
        scheduler = MarketDataScheduler()
        
        # Test higher_is_risk=True
        assert scheduler._normalize_value(5.0, 0.0, 10.0, higher_is_risk=True) == 0.5
        assert scheduler._normalize_value(0.0, 0.0, 10.0, higher_is_risk=True) == 0.0
        assert scheduler._normalize_value(10.0, 0.0, 10.0, higher_is_risk=True) == 1.0
        
        # Test higher_is_risk=False
        assert scheduler._normalize_value(5.0, 0.0, 10.0, higher_is_risk=False) == 0.5
        assert scheduler._normalize_value(0.0, 0.0, 10.0, higher_is_risk=False) == 1.0
        assert scheduler._normalize_value(10.0, 0.0, 10.0, higher_is_risk=False) == 0.0
        
        # Test clamping
        assert scheduler._normalize_value(-5.0, 0.0, 10.0, higher_is_risk=True) == 0.0
        assert scheduler._normalize_value(15.0, 0.0, 10.0, higher_is_risk=True) == 1.0
    
    def test_scheduler_status(self):
        """Test scheduler status reporting."""
        scheduler = MarketDataScheduler(background=True)
        
        # Test stopped status
        status = scheduler.get_status()
        assert status["status"] == "stopped"
        assert "last_results" in status
    
    @patch('app.scrape.scheduler.MarketDataScheduler.run_all_scrapers')
    def test_scheduler_job_configuration(self, mock_run):
        """Test scheduler job configuration."""
        scheduler = MarketDataScheduler(background=True)
        
        # This would normally start the scheduler, but we'll just test job config
        # In a real test, you'd use a test scheduler or mock the APScheduler
        
        # Test that the scheduler has the expected configuration
        assert scheduler.scheduler is not None


class TestIntegrationScenarios:
    """Test complete scraping integration scenarios."""
    
    def test_complete_scrape_cycle(self):
        """Test a complete scraping cycle with database storage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_market.db"
            store = MarketDataStore(str(db_path))
            
            # Simulate successful scraping by directly storing metrics
            store.write_metric("cbj_rate", 7.25, extra_json={"source": "cbj_test"})
            store.write_metric("cpi_yoy", 3.2, extra_json={"source": "cpi_test"})
            store.write_metric("re_price_index", 125.0, extra_json={"source": "re_test"})
            
            # Calculate risk score
            with patch('app.scrape.scheduler.read_all_metrics', store.read_all_metrics):
                with patch('app.scrape.scheduler.is_metric_stale', store.is_metric_stale):
                    with patch('app.scrape.scheduler.write_metric', store.write_metric):
                        scheduler = MarketDataScheduler()
                        risk_score = scheduler.calculate_market_risk_score()
            
            # Verify complete data set
            all_metrics = store.read_all_metrics()
            assert len(all_metrics) >= 4  # 3 base + 1 computed risk score
            assert "market_risk_score" in all_metrics
            
            # Verify risk score is reasonable
            assert 0.0 <= risk_score <= 1.0
    
    def test_scraper_failure_handling(self):
        """Test handling of scraper failures."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_market.db"
            store = MarketDataStore(str(db_path))
            
            # Pre-populate with old data
            old_time = (datetime.utcnow() - timedelta(hours=72)).isoformat() + "Z"
            store.write_metric("cbj_rate", 7.0, asof=old_time)
            store.write_metric("cpi_yoy", 2.5, asof=old_time)
            
            # Simulate partial scraper failure (only real estate succeeds)
            store.write_metric("re_price_index", 130.0)  # Fresh data
            
            # Calculate risk score with mixed fresh/stale data
            with patch('app.scrape.scheduler.read_all_metrics', store.read_all_metrics):
                with patch('app.scrape.scheduler.is_metric_stale', store.is_metric_stale):
                    with patch('app.scrape.scheduler.write_metric', store.write_metric):
                        scheduler = MarketDataScheduler()
                        risk_score = scheduler.calculate_market_risk_score()
            
            # Should still calculate a risk score but mark as stale
            assert risk_score is not None
            
            # Check that stale data is flagged
            risk_metric = store.read_metric("market_risk_score")
            assert risk_metric["extra"]["market_stale"] is True
            assert len(risk_metric["extra"]["stale_metrics"]) > 0 