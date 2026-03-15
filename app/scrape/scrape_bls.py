"""BLS API scraper for Oklahoma labor statistics and CPI data."""

import aiohttp
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

from ..utils.config import settings
from ..utils.logger import get_logger
from .store import write_metric

logger = get_logger(__name__)

# BLS API endpoint
BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# Oklahoma-specific BLS series IDs
BLS_SERIES = {
    'oklahoma_cpi': {
        'series_id': 'CUUR0000SA0L1OK',  # Oklahoma CPI-U All Items
        'description': 'Consumer Price Index - All Urban Consumers, Oklahoma',
        'cache_key': 'oklahoma_cpi_yoy',
        'calculate_yoy': True
    },
    'oklahoma_unemployment': {
        'series_id': 'LAUST390000000000003',  # Oklahoma unemployment rate
        'description': 'Unemployment Rate - Oklahoma',
        'cache_key': 'oklahoma_unemployment_rate',
        'calculate_yoy': False
    }
}


async def fetch_bls_series(series_id: str, api_key: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch time series data from BLS API.
    
    Args:
        series_id: BLS series identifier
        api_key: BLS API key (optional, but allows more requests)
        
    Returns:
        List of observations or None if failed
    """
    timeout = aiohttp.ClientTimeout(total=settings.scrape.timeout)
    
    # Request last 2 years to calculate YoY changes
    current_year = datetime.now().year
    start_year = str(current_year - 2)
    end_year = str(current_year)
    
    payload = {
        "seriesid": [series_id],
        "startyear": start_year,
        "endyear": end_year
    }
    
    # Add API key if available (increases rate limits)
    if api_key:
        payload["registrationkey"] = api_key
    
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Oklahoma-Loan-Advisory/1.0'
    }
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(BLS_URL, json=payload, headers=headers) as response:
                if response.status != 200:
                    logger.error("bls_request_failed", series_id=series_id, status=response.status)
                    return None
                
                data = await response.json()
                
                if data.get('status') != 'REQUEST_SUCCEEDED':
                    logger.error("bls_api_error", 
                               series_id=series_id, 
                               status=data.get('status'),
                               message=data.get('message', []))
                    return None
                
                results = data.get('Results', {})
                series_data = results.get('series', [])
                
                if not series_data:
                    logger.warning("no_bls_series_data", series_id=series_id)
                    return None
                
                # Extract observations from first (and should be only) series
                observations = series_data[0].get('data', [])
                
                if not observations:
                    logger.warning("no_bls_observations", series_id=series_id)
                    return None
                
                # Sort by period (most recent first)
                observations.sort(key=lambda x: (x.get('year', ''), x.get('period', '')), reverse=True)
                
                logger.debug("bls_observations_found", 
                           series_id=series_id, 
                           count=len(observations))
                return observations
                
    except Exception as e:
        logger.error("bls_fetch_error", series_id=series_id, error=str(e))
        return None


def calculate_yoy_change(observations: List[Dict[str, Any]]) -> Optional[Tuple[float, str, str]]:
    """
    Calculate year-over-year percentage change from BLS observations.
    
    Args:
        observations: List of BLS observations (sorted most recent first)
        
    Returns:
        Tuple of (yoy_percent, current_period, current_value) or None
    """
    if len(observations) < 13:  # Need at least 13 months for YoY calculation
        logger.warning("insufficient_data_for_yoy", observations_count=len(observations))
        return None
    
    try:
        # Most recent observation
        current_obs = observations[0]
        current_value = float(current_obs['value'])
        current_period = f"{current_obs['year']}-{current_obs['period']}"
        
        # Find observation from same period last year
        current_year = int(current_obs['year'])
        current_period_code = current_obs['period']
        target_year = str(current_year - 1)
        
        year_ago_obs = None
        for obs in observations:
            if obs['year'] == target_year and obs['period'] == current_period_code:
                year_ago_obs = obs
                break
        
        if not year_ago_obs:
            logger.warning("no_year_ago_data", 
                         current_period=current_period,
                         target_year=target_year)
            return None
        
        year_ago_value = float(year_ago_obs['value'])
        
        # Calculate YoY percentage change
        if year_ago_value == 0:
            logger.warning("zero_year_ago_value", period=current_period)
            return None
        
        yoy_percent = ((current_value - year_ago_value) / year_ago_value) * 100
        
        logger.debug("yoy_calculated", 
                   current_value=current_value,
                   year_ago_value=year_ago_value,
                   yoy_percent=yoy_percent)
        
        return yoy_percent, current_period, str(current_value)
        
    except (ValueError, KeyError) as e:
        logger.error("yoy_calculation_error", error=str(e))
        return None


async def scrape_bls_data() -> Dict[str, bool]:
    """
    Scrape all BLS labor statistics.
    
    Returns:
        Dict mapping cache_key to success status
    """
    logger.info("scraping_bls_data", series_count=len(BLS_SERIES))
    
    # Get API key from settings (optional)
    api_key = getattr(settings.scrape, 'bls_api_key', None) or getattr(settings, 'bls_api_key', None)
    if api_key:
        logger.info("using_bls_api_key")
    else:
        logger.info("using_bls_public_api")
    
    results = {}
    
    # Fetch all series
    for series_name, series_info in BLS_SERIES.items():
        try:
            series_id = series_info['series_id']
            cache_key = series_info['cache_key']
            
            observations = await fetch_bls_series(series_id, api_key)
            
            if not observations:
                results[cache_key] = False
                logger.warning("bls_series_failed", series=series_name)
                continue
            
            if series_info['calculate_yoy']:
                # Calculate YoY change (for CPI)
                yoy_result = calculate_yoy_change(observations)
                if yoy_result:
                    yoy_percent, period, current_value = yoy_result
                    value_to_store = yoy_percent
                    period_info = period
                else:
                    results[cache_key] = False
                    logger.warning("yoy_calculation_failed", series=series_name)
                    continue
            else:
                # Use current value directly (for unemployment rate)
                current_obs = observations[0]
                try:
                    value_to_store = float(current_obs['value'])
                    period_info = f"{current_obs['year']}-{current_obs['period']}"
                except (ValueError, KeyError) as e:
                    results[cache_key] = False
                    logger.error("current_value_parse_error", series=series_name, error=str(e))
                    continue
            
            # Convert BLS period to approximate ISO date
            try:
                year = period_info.split('-')[0]
                period_code = period_info.split('-')[1]
                
                # BLS monthly periods are M01-M12
                if period_code.startswith('M'):
                    month = period_code[1:].zfill(2)
                    iso_date = f"{year}-{month}-15T12:00:00Z"  # Use 15th of month
                else:
                    iso_date = f"{year}-01-01T12:00:00Z"  # Fallback
            except:
                iso_date = datetime.utcnow().isoformat() + "Z"
            
            # Write to cache with enriched metadata
            success = write_metric(
                key=cache_key,
                value=value_to_store,
                asof=iso_date,
                extra_json={
                    'source': 'BLS',
                    'series_id': series_id,
                    'description': series_info['description'],
                    'period': period_info,
                    'is_yoy_change': series_info['calculate_yoy']
                }
            )
            
            results[cache_key] = success
            if success:
                logger.info("bls_metric_cached", 
                          key=cache_key, 
                          value=value_to_store, 
                          period=period_info)
            else:
                logger.error("bls_cache_failed", key=cache_key)
                
        except Exception as e:
            results[series_info['cache_key']] = False
            logger.error("bls_series_error", series=series_name, error=str(e))
    
    success_count = sum(results.values())
    logger.info("bls_scraping_complete", 
                success_count=success_count, 
                total_count=len(BLS_SERIES))
    
    return results


async def run_bls_scraper() -> bool:
    """
    Main entry point for BLS scraper.
    
    Returns:
        True if all series scraped successfully, False otherwise
    """
    try:
        results = await scrape_bls_data()
        all_success = all(results.values())
        
        if all_success:
            logger.info("bls_scraper_success")
        else:
            failed_keys = [k for k, v in results.items() if not v]
            logger.warning("bls_scraper_partial_failure", failed_keys=failed_keys)
        
        return all_success
        
    except Exception as e:
        logger.error("bls_scraper_failed", error=str(e))
        return False


if __name__ == "__main__":
    # Test the scraper
    asyncio.run(run_bls_scraper())
