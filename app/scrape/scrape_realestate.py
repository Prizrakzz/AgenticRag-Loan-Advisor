"""Oklahoma Housing Index scraper using Zillow ZORI data."""

import aiohttp
import asyncio
import csv
import io
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from ..utils.config import settings
from ..utils.logger import get_logger
from .store import write_metric

logger = get_logger(__name__)

# Zillow ZORI CSV endpoint
ZORI_URL = "https://files.zillowstatic.com/research/public_csvs/zori/Metro_ZORI_AllHomesPlusMultifamily_SSA.csv"


async def scrape_real_estate_index() -> Optional[Tuple[float, str]]:
    """
    Scrape latest Oklahoma housing index from Zillow ZORI data.
    
    Returns:
        Tuple of (index_value, period_string) or None if failed
    """
    logger.info("scraping_oklahoma_housing_index", url=ZORI_URL)
    
    timeout = aiohttp.ClientTimeout(total=settings.scrape.timeout)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(ZORI_URL) as response:
                if response.status != 200:
                    logger.error("zori_request_failed", status=response.status)
                    return None
                
                csv_content = await response.text()
                
                # Parse CSV data
                csv_reader = csv.DictReader(io.StringIO(csv_content))
                
                # Find Oklahoma City metro area data
                oklahoma_data = None
                for row in csv_reader:
                    region_name = row.get('RegionName', '').lower()
                    if 'oklahoma city' in region_name or 'oklahoma' in region_name:
                        oklahoma_data = row
                        logger.info("found_oklahoma_region", region_name=row.get('RegionName'))
                        break
                
                if not oklahoma_data:
                    logger.error("oklahoma_region_not_found")
                    return None
                
                # Get the most recent date column with data
                date_columns = [col for col in oklahoma_data.keys() 
                              if col not in ['RegionID', 'SizeRank', 'RegionName', 'RegionType', 'StateName']]
                
                # Sort date columns to get the most recent
                date_columns.sort(reverse=True)
                
                index_value = None
                period = None
                
                for date_col in date_columns:
                    value = oklahoma_data.get(date_col)
                    if value and value.strip() and value != 'N/A':
                        try:
                            index_value = float(value)
                            period = date_col
                            
                            # ZORI values are typically in hundreds to thousands (rent prices)
                            if 500.0 <= index_value <= 5000.0:
                                logger.info("housing_index_found", 
                                          value=index_value, period=period)
                                break
                            else:
                                logger.warning("housing_index_out_of_range", 
                                             value=index_value, period=period)
                                
                        except ValueError:
                            continue
                
                if index_value is None:
                    logger.error("no_valid_housing_index_data")
                    return None
                
                logger.info("housing_index_scraped_successfully", 
                          index_value=index_value, 
                          period=period,
                          region=oklahoma_data.get('RegionName'))
                
                return index_value, period
                
    except asyncio.TimeoutError:
        logger.error("housing_index_scrape_timeout", timeout=settings.scrape.timeout)
        return None
    except Exception as e:
        logger.error("housing_index_scrape_failed", error=str(e))
        return None


async def update_real_estate_index() -> bool:
    """
    Scrape Oklahoma housing index and store in database.
    
    Returns:
        True if successful, False otherwise
    """
    logger.info("updating_oklahoma_housing_index")
    
    try:
        result = await scrape_real_estate_index()
        
        if result is None:
            logger.error("housing_index_update_failed_no_data")
            return False
        
        index_value, period = result
        
        # Store in database
        extra_data = {
            "source": "zillow_zori",
            "url": ZORI_URL,
            "period": period,
            "location": "Oklahoma City, OK",
            "index_type": "ZORI_AllHomesPlusMultifamily_SSA",
            "scraper_version": "2.0"
        }
        
        success = write_metric("re_price_index", index_value, extra_json=extra_data)
        
        if success:
            logger.info("housing_index_updated", 
                       index_value=index_value, period=period)
        else:
            logger.error("housing_index_store_failed", index_value=index_value)
        
        return success
        
    except Exception as e:
        logger.error("housing_index_update_exception", error=str(e))
        return False


def run_real_estate_scraper() -> bool:
    """
    Synchronous wrapper to run real estate scraper.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        return asyncio.run(update_real_estate_index())
    except Exception as e:
        logger.error("re_scraper_run_failed", error=str(e))
        return False


if __name__ == "__main__":
    # Test scraper
    import sys
    
    async def test_scraper():
        result = await scrape_real_estate_index()
        if result:
            index_value, period = result
            print(f"✅ Real Estate Index: {index_value} (Period: {period})")
            
            # Test storage
            success = await update_real_estate_index()
            if success:
                print("✅ Real estate index stored successfully")
            else:
                print("❌ Failed to store real estate index")
        else:
            print("❌ Failed to scrape real estate index")
    
    asyncio.run(test_scraper()) 