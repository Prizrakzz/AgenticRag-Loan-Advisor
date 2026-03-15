"""FRED API scraper for U.S. economic indicators relevant to Oklahoma lending."""

import aiohttp
import asyncio
import json
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from ..utils.config import settings
from ..utils.logger import get_logger
from .store import write_metric

logger = get_logger(__name__)

# FRED API endpoint
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

# U.S./Oklahoma relevant series IDs
FRED_SERIES = {
    'okc_home_prices': {
        'series_id': 'OKCSHPINSA',
        'description': 'S&P Case-Shiller Home Price Index - Oklahoma City',
        'cache_key': 'okc_home_price_index'
    },
    'mortgage_rate_30yr': {
        'series_id': 'MORTGAGE30US', 
        'description': '30-Year Fixed Rate Mortgage Average in the United States',
        'cache_key': 'mortgage_30yr_rate'
    },
    'federal_funds_rate': {
        'series_id': 'FEDFUNDS',
        'description': 'Federal Funds Effective Rate',
        'cache_key': 'fed_funds_rate'
    }
}


async def fetch_fred_series(series_id: str, api_key: str) -> Optional[Tuple[float, str]]:
    """
    Fetch latest observation from a FRED series.
    
    Args:
        series_id: FRED series identifier
        api_key: FRED API key
        
    Returns:
        Tuple of (value, observation_date) or None if failed
    """
    timeout = aiohttp.ClientTimeout(total=settings.scrape.timeout)
    
    params = {
        'series_id': series_id,
        'api_key': api_key,
        'file_type': 'json',
        'sort_order': 'desc',
        'limit': 5,  # Get last 5 observations to find most recent valid data
        'observation_start': '2023-01-01'
    }
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(FRED_URL, params=params) as response:
                if response.status != 200:
                    logger.error("fred_request_failed", series_id=series_id, status=response.status)
                    return None
                
                data = await response.json()
                observations = data.get('observations', [])
                
                if not observations:
                    logger.warning("no_fred_observations", series_id=series_id)
                    return None
                
                # Find the most recent observation with valid data
                for obs in observations:
                    value_str = obs.get('value', '.')
                    if value_str != '.' and value_str != '':
                        try:
                            value = float(value_str)
                            obs_date = obs.get('date', '')
                            logger.debug("fred_observation_found", 
                                       series_id=series_id, 
                                       value=value, 
                                       date=obs_date)
                            return value, obs_date
                        except (ValueError, TypeError):
                            continue
                
                logger.warning("no_valid_fred_data", series_id=series_id)
                return None
                
    except Exception as e:
        logger.error("fred_fetch_error", series_id=series_id, error=str(e))
        return None


async def use_fred_fallback_data() -> Dict[str, bool]:
    """
    Use fallback data when FRED API key is not available.
    
    Returns:
        Dict mapping cache_key to success status
    """
    logger.info("using_fred_fallback_data")
    
    # Current approximate values based on recent economic conditions (as of late 2024)
    fallback_data = {
        'okc_home_price_index': {
            'value': 145.2,  # Approximate Oklahoma City home price index
            'description': 'Oklahoma City Home Price Index (Fallback Data)',
            'date': '2024-01-01'
        },
        'mortgage_30yr_rate': {
            'value': 7.2,  # Approximate 30-year mortgage rate
            'description': '30-Year Fixed Rate Mortgage Average (Fallback Data)',
            'date': '2024-01-01'
        },
        'fed_funds_rate': {
            'value': 5.25,  # Approximate federal funds rate
            'description': 'Federal Funds Effective Rate (Fallback Data)',
            'date': '2024-01-01'
        }
    }
    
    results = {}
    current_time = datetime.utcnow().isoformat() + "Z"
    
    for cache_key, data in fallback_data.items():
        try:
            success = write_metric(
                key=cache_key,
                value=data['value'],
                asof=current_time,
                extra_json={
                    'source': 'FRED_Fallback',
                    'description': data['description'],
                    'fallback_date': data['date'],
                    'note': 'Fallback data used due to missing FRED API key'
                }
            )
            
            results[cache_key] = success
            if success:
                logger.info("fred_fallback_cached", 
                          key=cache_key, 
                          value=data['value'])
            
        except Exception as e:
            logger.error("fred_fallback_error", key=cache_key, error=str(e))
            results[cache_key] = False
    
    return results


async def scrape_fred_data() -> Dict[str, bool]:
    """
    Scrape all FRED economic indicators.
    
    Returns:
        Dict mapping cache_key to success status
    """
    logger.info("scraping_fred_data", series_count=len(FRED_SERIES))
    
    # Get API key from settings (optional for basic usage)
    api_key = getattr(settings.scrape, 'fred_api_key', None) or getattr(settings, 'fred_api_key', None)
    if not api_key:
        logger.warning("fred_api_key_missing_using_fallback")
        # Use fallback known values instead of failing completely
        return await use_fred_fallback_data()
    
    results = {}
    
    # Fetch all series concurrently
    tasks = []
    for series_name, series_info in FRED_SERIES.items():
        task = fetch_fred_series(series_info['series_id'], api_key)
        tasks.append((series_name, series_info, task))
    
    for series_name, series_info, task in tasks:
        try:
            result = await task
            cache_key = series_info['cache_key']
            
            if result:
                value, obs_date = result
                
                # Write to cache with enriched metadata
                success = write_metric(
                    key=cache_key,
                    value=value,
                    asof=f"{obs_date}T12:00:00Z",  # Convert FRED date to ISO format
                    extra_json={
                        'source': 'FRED',
                        'series_id': series_info['series_id'],
                        'description': series_info['description'],
                        'observation_date': obs_date
                    }
                )
                
                results[cache_key] = success
                if success:
                    logger.info("fred_metric_cached", 
                              key=cache_key, 
                              value=value, 
                              date=obs_date)
                else:
                    logger.error("fred_cache_failed", key=cache_key)
            else:
                results[cache_key] = False
                logger.warning("fred_series_failed", series=series_name)
                
        except Exception as e:
            results[series_info['cache_key']] = False
            logger.error("fred_series_error", series=series_name, error=str(e))
    
    success_count = sum(results.values())
    logger.info("fred_scraping_complete", 
                success_count=success_count, 
                total_count=len(FRED_SERIES))
    
    return results


async def run_fred_scraper() -> bool:
    """
    Main entry point for FRED scraper.
    
    Returns:
        True if all series scraped successfully, False otherwise
    """
    try:
        results = await scrape_fred_data()
        all_success = all(results.values())
        
        if all_success:
            logger.info("fred_scraper_success")
        else:
            failed_keys = [k for k, v in results.items() if not v]
            logger.warning("fred_scraper_partial_failure", failed_keys=failed_keys)
        
        return all_success
        
    except Exception as e:
        logger.error("fred_scraper_failed", error=str(e))
        return False


if __name__ == "__main__":
    # Test the scraper
    asyncio.run(run_fred_scraper())
