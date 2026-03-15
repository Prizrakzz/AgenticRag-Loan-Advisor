"""SQLite storage for market data metrics."""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from contextlib import contextmanager

from ..utils.config import settings
from ..utils.logger import get_logger

logger = get_logger(__name__)


class MarketDataStore:
    """SQLite store for market data metrics."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.data.market_cache
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Ensure database and table exist."""
        db_file = Path(self.db_path)
        db_file.parent.mkdir(exist_ok=True)
        
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_snapshot (
                    key TEXT PRIMARY KEY,
                    value REAL,
                    asof TEXT,
                    extra_json TEXT DEFAULT '{}'
                )
            """)
            conn.commit()
        
        logger.debug("market_store_initialized", db_path=self.db_path)
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
        finally:
            conn.close()
    
    def write_metric(
        self,
        key: str,
        value: float,
        asof: str = None,
        extra_json: Dict[str, Any] = None
    ) -> bool:
        """
        Write or update a market metric.
        
        Args:
            key: Metric key (e.g., 'cbj_rate', 'cpi_yoy')
            value: Metric value
            asof: Timestamp (ISO format, defaults to now)
            extra_json: Additional metadata
        
        Returns:
            True if successful, False otherwise
        """
        if asof is None:
            asof = datetime.utcnow().isoformat() + "Z"
        
        if extra_json is None:
            extra_json = {}
        
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO market_snapshot 
                    (key, value, asof, extra_json) 
                    VALUES (?, ?, ?, ?)
                    """,
                    (key, value, asof, json.dumps(extra_json))
                )
                conn.commit()
            
            logger.info(
                "metric_stored",
                key=key,
                value=value,
                asof=asof,
                extra_fields=list(extra_json.keys()) if extra_json else []
            )
            
            return True
            
        except Exception as e:
            logger.error("failed_to_store_metric", key=key, error=str(e))
            return False
    
    def read_metric(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Read a single metric.
        
        Args:
            key: Metric key
        
        Returns:
            Metric data dict or None if not found
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT key, value, asof, extra_json FROM market_snapshot WHERE key = ?",
                    (key,)
                )
                row = cursor.fetchone()
                
                if row:
                    extra_json = json.loads(row["extra_json"]) if row["extra_json"] else {}
                    return {
                        "key": row["key"],
                        "value": row["value"],
                        "asof": row["asof"],
                        "extra": extra_json
                    }
                
                return None
                
        except Exception as e:
            logger.error("failed_to_read_metric", key=key, error=str(e))
            return None
    
    def read_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """
        Read all metrics.
        
        Returns:
            Dict mapping metric keys to metric data
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT key, value, asof, extra_json FROM market_snapshot"
                )
                
                metrics = {}
                for row in cursor.fetchall():
                    extra_json = json.loads(row["extra_json"]) if row["extra_json"] else {}
                    metrics[row["key"]] = {
                        "key": row["key"],
                        "value": row["value"],
                        "asof": row["asof"],
                        "extra": extra_json
                    }
                
                logger.debug("metrics_read", count=len(metrics))
                return metrics
                
        except Exception as e:
            logger.error("failed_to_read_all_metrics", error=str(e))
            return {}
    
    def get_metric_history(self, key: str, limit: int = 30) -> List[Dict[str, Any]]:
        """
        Get historical values for a metric (if we stored history).
        Currently just returns the single latest value.
        
        Args:
            key: Metric key
            limit: Maximum number of historical points
        
        Returns:
            List of historical metric data
        """
        current = self.read_metric(key)
        return [current] if current else []
    
    def is_metric_stale(self, key: str, max_age_hours: int = 48) -> bool:
        """
        Check if a metric is stale based on age.
        
        Args:
            key: Metric key
            max_age_hours: Maximum age in hours before considering stale
        
        Returns:
            True if metric is stale or missing
        """
        metric = self.read_metric(key)
        if not metric:
            return True
        
        try:
            asof_dt = datetime.fromisoformat(metric["asof"].replace("Z", "+00:00"))
            age_hours = (datetime.utcnow() - asof_dt.replace(tzinfo=None)).total_seconds() / 3600
            
            is_stale = age_hours > max_age_hours
            
            if is_stale:
                logger.warning(
                    "metric_stale",
                    key=key,
                    age_hours=age_hours,
                    max_age_hours=max_age_hours
                )
            
            return is_stale
            
        except Exception as e:
            logger.error("failed_to_check_staleness", key=key, error=str(e))
            return True
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get database information and statistics."""
        try:
            with self._get_connection() as conn:
                # Count metrics
                cursor = conn.execute("SELECT COUNT(*) as count FROM market_snapshot")
                metric_count = cursor.fetchone()["count"]
                
                # Get last update times
                cursor = conn.execute(
                    "SELECT key, asof FROM market_snapshot ORDER BY asof DESC"
                )
                recent_updates = [(row["key"], row["asof"]) for row in cursor.fetchall()]
                
                return {
                    "db_path": self.db_path,
                    "metric_count": metric_count,
                    "recent_updates": recent_updates[:5]  # Last 5 updates
                }
                
        except Exception as e:
            logger.error("failed_to_get_db_info", error=str(e))
            return {"db_path": self.db_path, "error": str(e)}


# Global store instance
_store: Optional[MarketDataStore] = None


def get_market_store() -> MarketDataStore:
    """Get global market data store instance (singleton pattern)."""
    global _store
    if _store is None:
        _store = MarketDataStore()
    return _store


# Convenience functions
def write_metric(key: str, value: float, asof: str = None, extra_json: Dict[str, Any] = None) -> bool:
    """Write a market metric using the global store."""
    return get_market_store().write_metric(key, value, asof, extra_json)


def read_metric(key: str) -> Optional[Dict[str, Any]]:
    """Read a market metric using the global store."""
    return get_market_store().read_metric(key)


def read_all_metrics() -> Dict[str, Dict[str, Any]]:
    """Read all market metrics using the global store."""
    return get_market_store().read_all_metrics()


def is_metric_stale(key: str, max_age_hours: int = 48) -> bool:
    """Check if a metric is stale using the global store."""
    return get_market_store().is_metric_stale(key, max_age_hours) 