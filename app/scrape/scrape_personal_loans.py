"""Personal Loan benchmark rates scraper from multiple public sources."""

import aiohttp
import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from statistics import median

from ..utils.config import settings
from ..utils.logger import get_logger
from .store import write_metric

logger = get_logger(__name__)

# Public sources for personal loan rate data
RATE_SOURCES = {
    'bankrate': {
        'url': 'https://www.bankrate.com/loans/personal-loans/rates/',
        'description': 'Bankrate Personal Loan Rates'
    },
    'nerdwallet': {
        'url': 'https://www.nerdwallet.com/personal-loans',
        'description': 'NerdWallet Personal Loan Data'
    },
    'creditkarma': {
        'url': 'https://www.creditkarma.com/personal-loans',
        'description': 'Credit Karma Personal Loan Rates'
    }
}

# Known benchmark rates (updated periodically from industry sources)
BENCHMARK_RATES = {
    'excellent_credit': {
        'fico_range': '720+',
        'rate_range': (6.99, 12.99),
        'median_rate': 9.99
    },
    'good_credit': {
        'fico_range': '660-719',
        'rate_range': (8.99, 18.99),
        'median_rate': 13.99
    },
    'fair_credit': {
        'fico_range': '580-659',
        'rate_range': (13.99, 25.99),
        'median_rate': 19.99
    },
    'poor_credit': {
        'fico_range': 'Below 580',
        'rate_range': (18.99, 35.99),
        'median_rate': 27.99
    }
}


async def fetch_rate_source(source_name: str, source_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """
    Fetch personal loan rate data from a specific source.
    
    Args:
        source_name: Name of the rate source
        source_info: Dict with 'url' and 'description'
        
    Returns:
        Dict with parsed rate data or None if failed
    """
    timeout = aiohttp.ClientTimeout(total=settings.scrape.timeout)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(source_info['url'], headers=headers) as response:
                if response.status != 200:
                    logger.warning("rate_source_failed", 
                                 source=source_name, 
                                 status=response.status)
                    return None
                
                content = await response.text()
                
                # Extract rate information using regex patterns
                rates = extract_rates_from_content(content, source_name)
                
                if rates:
                    logger.debug("rates_extracted", 
                               source=source_name, 
                               rate_count=len(rates))
                    return {
                        'source': source_name,
                        'url': source_info['url'],
                        'description': source_info['description'],
                        'rates': rates,
                        'scraped_at': datetime.utcnow().isoformat() + 'Z'
                    }
                else:
                    logger.warning("no_rates_extracted", source=source_name)
                    return None
                
    except Exception as e:
        logger.error("rate_source_error", source=source_name, error=str(e))
        return None


def extract_rates_from_content(content: str, source_name: str) -> List[Dict[str, Any]]:
    """
    Extract personal loan rates from HTML content using regex patterns.
    
    Args:
        content: HTML content from rate source
        source_name: Name of the source for logging
        
    Returns:
        List of extracted rate information
    """
    rates = []
    
    try:
        # Common patterns for rate extraction
        rate_patterns = [
            r'(\d+\.?\d*)%?\s*(?:-|to)\s*(\d+\.?\d*)%',  # Range like "6.99% - 24.99%"
            r'(\d+\.?\d*)%\s*APR',  # Single rate like "12.99% APR"
            r'as low as\s*(\d+\.?\d*)%',  # "as low as 6.99%"
            r'starting at\s*(\d+\.?\d*)%',  # "starting at 7.99%"
            r'(\d+\.?\d*)%\s*to\s*(\d+\.?\d*)%',  # "8.99% to 29.99%"
        ]
        
        for pattern in rate_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            
            for match in matches:
                try:
                    groups = match.groups()
                    
                    if len(groups) == 2:
                        # Rate range
                        min_rate = float(groups[0])
                        max_rate = float(groups[1])
                        
                        if 0 < min_rate < 100 and 0 < max_rate < 100:
                            rates.append({
                                'type': 'range',
                                'min_rate': min_rate,
                                'max_rate': max_rate,
                                'median_rate': (min_rate + max_rate) / 2
                            })
                    elif len(groups) == 1:
                        # Single rate
                        rate = float(groups[0])
                        
                        if 0 < rate < 100:
                            rates.append({
                                'type': 'single',
                                'rate': rate
                            })
                            
                except (ValueError, IndexError) as e:
                    logger.debug("rate_parse_error", 
                               source=source_name, 
                               match=match.group(0), 
                               error=str(e))
                    continue
        
        # Remove duplicates and sort
        unique_rates = []
        seen_rates = set()
        
        for rate in rates:
            if rate['type'] == 'range':
                key = (rate['min_rate'], rate['max_rate'])
            else:
                key = rate['rate']
            
            if key not in seen_rates:
                seen_rates.add(key)
                unique_rates.append(rate)
        
        logger.debug("rates_processed", 
                   source=source_name, 
                   original_count=len(rates),
                   unique_count=len(unique_rates))
        
        return unique_rates
        
    except Exception as e:
        logger.error("rate_extraction_error", source=source_name, error=str(e))
        return []


def calculate_benchmark_rates(all_source_data: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calculate benchmark personal loan rates from scraped data.
    
    Args:
        all_source_data: List of data from all sources
        
    Returns:
        Dict with calculated benchmark rates
    """
    try:
        all_rates = []
        range_medians = []
        single_rates = []
        
        # Collect all rates from all sources
        for source_data in all_source_data:
            if not source_data or 'rates' not in source_data:
                continue
            
            for rate_info in source_data['rates']:
                if rate_info['type'] == 'range':
                    range_medians.append(rate_info['median_rate'])
                    all_rates.extend([rate_info['min_rate'], rate_info['max_rate']])
                else:
                    single_rates.append(rate_info['rate'])
                    all_rates.append(rate_info['rate'])
        
        if not all_rates:
            logger.warning("no_rates_for_benchmark")
            # Use fallback benchmark rates
            return {
                'personal_loan_median': BENCHMARK_RATES['good_credit']['median_rate'],
                'personal_loan_min': min(r['rate_range'] for r in BENCHMARK_RATES.values())[0],
                'personal_loan_max': max(r['rate_range'] for r in BENCHMARK_RATES.values())[1]
            }
        
        # Calculate benchmarks
        benchmarks = {
            'personal_loan_median': median(all_rates),
            'personal_loan_min': min(all_rates),
            'personal_loan_max': max(all_rates)
        }
        
        # Add credit tier benchmarks if we have enough data
        if len(all_rates) >= 4:
            sorted_rates = sorted(all_rates)
            quartile_size = len(sorted_rates) // 4
            
            benchmarks.update({
                'personal_loan_excellent_credit': sorted_rates[quartile_size],  # 25th percentile (best rates)
                'personal_loan_good_credit': median(sorted_rates[:len(sorted_rates)//2]),  # Lower half median
                'personal_loan_fair_credit': median(sorted_rates[len(sorted_rates)//2:]),  # Upper half median
                'personal_loan_poor_credit': sorted_rates[-quartile_size]  # 75th percentile (higher rates)
            })
        
        logger.info("benchmark_rates_calculated", 
                  rate_count=len(all_rates),
                  median=benchmarks['personal_loan_median'],
                  min_rate=benchmarks['personal_loan_min'],
                  max_rate=benchmarks['personal_loan_max'])
        
        return benchmarks
        
    except Exception as e:
        logger.error("benchmark_calculation_error", error=str(e))
        # Return fallback rates
        return {
            'personal_loan_median': BENCHMARK_RATES['good_credit']['median_rate'],
            'personal_loan_min': BENCHMARK_RATES['excellent_credit']['rate_range'][0],
            'personal_loan_max': BENCHMARK_RATES['poor_credit']['rate_range'][1]
        }


async def scrape_personal_loan_rates() -> Dict[str, bool]:
    """
    Scrape personal loan rates from multiple sources.
    
    Returns:
        Dict mapping metric names to success status
    """
    logger.info("scraping_personal_loan_rates", source_count=len(RATE_SOURCES))
    
    # Fetch data from all sources concurrently
    tasks = []
    for source_name, source_info in RATE_SOURCES.items():
        task = fetch_rate_source(source_name, source_info)
        tasks.append(task)
    
    try:
        source_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter successful results
        valid_data = []
        for result in source_results:
            if isinstance(result, dict) and result is not None:
                valid_data.append(result)
            elif isinstance(result, Exception):
                logger.warning("source_fetch_exception", error=str(result))
        
        logger.info("source_results_collected", 
                  valid_sources=len(valid_data),
                  total_sources=len(RATE_SOURCES))
        
        # Calculate benchmark rates
        benchmarks = calculate_benchmark_rates(valid_data)
        
        # Store benchmarks in cache
        results = {}
        current_time = datetime.utcnow().isoformat() + "Z"
        
        for metric_name, rate_value in benchmarks.items():
            try:
                success = write_metric(
                    key=metric_name,
                    value=rate_value,
                    asof=current_time,
                    extra_json={
                        'source': 'Personal Loan Benchmarks',
                        'description': f'Personal loan rate benchmark: {metric_name}',
                        'unit': 'percentage',
                        'sources_used': len(valid_data),
                        'calculation_method': 'median_of_scraped_rates'
                    }
                )
                
                results[metric_name] = success
                if success:
                    logger.info("benchmark_cached", 
                              metric=metric_name, 
                              value=rate_value)
                
            except Exception as e:
                logger.error("benchmark_cache_error", 
                           metric=metric_name, 
                           error=str(e))
                results[metric_name] = False
        
        success_count = sum(results.values())
        logger.info("personal_loan_scraping_complete", 
                    success_count=success_count, 
                    total_count=len(results))
        
        return results
        
    except Exception as e:
        logger.error("personal_loan_scraping_error", error=str(e))
        return {metric: False for metric in ['personal_loan_median', 'personal_loan_min', 'personal_loan_max']}


async def run_personal_loan_scraper() -> bool:
    """
    Main entry point for Personal Loan rates scraper.
    
    Returns:
        True if scraping successful, False otherwise
    """
    try:
        results = await scrape_personal_loan_rates()
        all_success = all(results.values())
        
        if all_success:
            logger.info("personal_loan_scraper_success")
        else:
            failed_keys = [k for k, v in results.items() if not v]
            logger.warning("personal_loan_scraper_partial_failure", failed_keys=failed_keys)
        
        return all_success
        
    except Exception as e:
        logger.error("personal_loan_scraper_failed", error=str(e))
        return False


if __name__ == "__main__":
    # Test the scraper
    asyncio.run(run_personal_loan_scraper())
