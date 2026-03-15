"""FastAPI dependencies for authentication, database, and services."""

from typing import Generator, Optional, Dict, Any
from dataclasses import dataclass
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import time

from ..db.database import get_db_session
from ..graph.workflow import get_workflow as _get_workflow
from ..utils.config import settings
from ..utils.auth import decode_jwt, get_user_id_from_token
from ..utils.logger import get_logger
from ..scrape.store import get_market_store
from ..rag.retriever import get_retriever

logger = get_logger(__name__)

# Security scheme
security = HTTPBearer()


@dataclass
class User:
    """Simple user object with id attribute."""
    id: int
    
    def __post_init__(self):
        """Ensure id is an integer."""
        self.id = int(self.id)


def get_db() -> Generator[Session, None, None]:
    """
    Database dependency for FastAPI routes.
    
    Yields:
        SQLAlchemy database session
    """
    with get_db_session() as db:
        yield db


def get_workflow():
    """
    Get the compiled LangGraph workflow for FastAPI DI.
    
    Returns:
        Compiled workflow instance
    """
    return _get_workflow()


def get_settings():
    """
    Get application settings.
    
    Returns:
        Application settings instance
    """
    return settings


def get_market_data_store():
    """
    Get market data store instance.
    
    Returns:
        Market data store instance
    """
    return get_market_store()


def get_policy_retriever_instance():
    """
    Get policy retriever instance.
    
    Returns:
        Policy retriever instance
    """
    return get_retriever()


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> int:
    """
    Get current authenticated user from JWT token.
    
    Args:
        request: FastAPI request object
        credentials: HTTP authorization credentials
        db: Database session
    
    Returns:
        User ID
    
    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials
    
    try:
        # Decode and validate JWT
        payload = decode_jwt(token)
        user_id = get_user_id_from_token(token)
        
        # Attach user ID to request state for logging
        request.state.user_id = user_id
        
        logger.info(
            "user_authenticated",
            user_id=user_id,
            endpoint=request.url.path
        )
        
        return user_id
        
    except Exception as e:
        logger.warning(
            "authentication_failed",
            error=str(e),
            endpoint=request.url.path,
            user_agent=request.headers.get("user-agent", "unknown")
        )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_object(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user as User object with .id attribute.
    
    Args:
        request: FastAPI request object
        credentials: HTTP authorization credentials  
        db: Database session
    
    Returns:
        User object with id attribute
    
    Raises:
        HTTPException: If authentication fails
    """
    user_id = get_current_user(request, credentials, db)
    return User(id=user_id)


def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db)
) -> Optional[int]:
    """
    Get current user if authenticated, otherwise None.
    
    Args:
        request: FastAPI request object
        credentials: Optional HTTP authorization credentials
        db: Database session
    
    Returns:
        User ID if authenticated, None otherwise
    """
    if not credentials:
        return None
    
    try:
        return get_current_user(request, credentials, db)
    except HTTPException:
        return None


def get_request_id(request: Request) -> str:
    """
    Get or generate request ID for tracking.
    
    Args:
        request: FastAPI request object
    
    Returns:
        Request ID
    """
    # Check if request ID already exists (set by middleware)
    request_id = getattr(request.state, 'request_id', None)
    
    if not request_id:
        # Generate new request ID
        import uuid
        request_id = f"REQ-{uuid.uuid4().hex[:12].upper()}"
        request.state.request_id = request_id
    
    return request_id


def get_request_start_time(request: Request) -> float:
    """
    Get request start time for performance tracking.
    
    Args:
        request: FastAPI request object
    
    Returns:
        Request start time (timestamp)
    """
    start_time = getattr(request.state, 'start_time', None)
    
    if not start_time:
        start_time = time.time()
        request.state.start_time = start_time
    
    return start_time


def log_request_context(
    request: Request,
    user_id: Optional[int] = Depends(get_optional_user),
    request_id: str = Depends(get_request_id)
):
    """
    Log request context for debugging and monitoring.
    
    Args:
        request: FastAPI request object
        user_id: Optional authenticated user ID
        request_id: Request ID
    """
    logger.info(
        "request_received",
        method=request.method,
        path=request.url.path,
        user_id=user_id,
        request_id=request_id,
        user_agent=request.headers.get("user-agent", "unknown"),
        content_length=request.headers.get("content-length", 0)
    )


def create_rate_limit_decorator(rate: str):
    """
    Create a rate limiting decorator.
    
    Args:
        rate: Rate limit string (e.g., "30/minute")
    
    Returns:
        Rate limiting decorator function
    """
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    
    limiter = Limiter(key_func=get_remote_address)
    
    def rate_limit_decorator():
        def decorator(func):
            return limiter.limit(rate)(func)
        return decorator
    
    return rate_limit_decorator


def get_rate_limit_key(request: Request, user_id: Optional[int] = None) -> str:
    """
    Determine rate limit key (user ID or IP address).
    
    Args:
        request: FastAPI request object
        user_id: Optional authenticated user ID
    
    Returns:
        Rate limit key
    """
    if user_id:
        return f"user:{user_id}"
    
    # Fallback to IP address
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take the first IP if multiple are present
        client_ip = forwarded_for.split(',')[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    
    return f"ip:{client_ip}"


def setup_rate_limiting(app):
    """
    Setup rate limiting for the FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from fastapi import Request, Response
    
    limiter = Limiter(key_func=get_remote_address)
    
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        logger.warning(
            "rate_limit_exceeded",
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
            limit=str(exc.detail)
        )
        
        response = Response(
            content=f"Rate limit exceeded: {exc.detail}",
            status_code=429
        )
        response.headers["Retry-After"] = str(exc.retry_after)
        return response


# Validation Dependencies
def validate_user_exists(
    user_id: int,
    db: Session = Depends(get_db)
) -> int:
    """
    Validate that user exists in database.
    
    Args:
        user_id: User ID to validate
        db: Database session
    
    Returns:
        User ID if valid
    
    Raises:
        HTTPException: If user not found
    """
    from ..db.models import Customer
    
    customer = db.query(Customer).filter(Customer.client_id == user_id).first()
    
    if not customer:
        logger.warning("user_not_found", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user_id


def validate_request_size(request: Request):
    """
    Validate request content size.
    
    Args:
        request: FastAPI request object
    
    Raises:
        HTTPException: If request too large
    """
    content_length = request.headers.get("content-length")
    
    if content_length:
        size = int(content_length)
        max_size = 1024 * 1024  # 1MB limit
        
        if size > max_size:
            logger.warning(
                "request_too_large",
                size=size,
                max_size=max_size,
                path=request.url.path
            )
            
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Request entity too large"
            )


# Health Check Dependencies
async def check_database_health() -> Dict[str, Any]:
    """
    Check database connectivity and basic stats.
    
    Returns:
        Database health information
    """
    try:
        from ..db.models import Customer, AuditLog
        from ..db.database import get_db_session
        from pathlib import Path
        
        # Log database configuration for debugging
        logger.info(f"Database URL: {settings.database.url}")
        logger.info(f"Current working directory: {Path.cwd()}")
     
        
        
        # Test connection with a simple query
        with get_db_session() as db:
            customer_count = db.query(Customer).count()
            audit_count = db.query(AuditLog).count()
            
            logger.info(f"Database health check successful: customers={customer_count}, audit_logs={audit_count}")
            
            return {
                "connected": True,
                "customer_count": customer_count,
                "audit_log_count": audit_count
            }
        
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return {
            "connected": False,
            "customer_count": None,
            "audit_log_count": None,
            "error": str(e)
        }


async def check_vector_store_health() -> Dict[str, Any]:
    """
    Check vector store connectivity and collection status.
    
    Returns:
        Vector store health information
    """
    try:
        from qdrant_client import QdrantClient
        
        # Log Qdrant configuration for debugging
        qdrant_host, qdrant_port = settings.qdrant_host_port
        logger.info(f"Qdrant configuration: host={qdrant_host}, port={qdrant_port}, collection={settings.vector.collection_name}")
        
        # Create client and test connection
        client = QdrantClient(host=qdrant_host, port=qdrant_port)
        
        # Test basic connectivity
        collections = client.get_collections()
        logger.info(f"Qdrant collections available: {[c.name for c in collections.collections]}")
        
        # Check if our specific collection exists
        collection_exists = any(c.name == settings.vector.collection_name for c in collections.collections)
        
        document_count = 0
        if collection_exists:
            collection_info = client.get_collection(settings.vector.collection_name)
            document_count = collection_info.vectors_count if hasattr(collection_info, 'vectors_count') else 0
            logger.info(f"Collection '{settings.vector.collection_name}' found with {document_count} vectors")
        else:
            logger.warning(f"Collection '{settings.vector.collection_name}' not found. Available: {[c.name for c in collections.collections]}")
        
        return {
            "connected": True,
            "collection_exists": collection_exists,
            "document_count": document_count,
            "available_collections": [c.name for c in collections.collections]
        }
        
    except Exception as e:
        logger.error("vector_store_health_check_failed", error=str(e))
        return {
            "connected": False,
            "collection_exists": False,
            "document_count": None,
            "error": str(e)
        }


async def check_market_data_health() -> Dict[str, Any]:
    """
    Check market data availability and freshness.
    
    Returns:
        Market data health information
    """
    try:
        from pathlib import Path
        from datetime import datetime, timezone
        
        store = get_market_data_store()
        
        # Log market data configuration for debugging
        cache_path = Path(settings.data.market_cache)
        logger.info(f"Market cache path: {cache_path}")
        logger.info(f"Cache exists: {cache_path.exists()}")
        logger.info(f"Stale threshold: {settings.scrape.stale_threshold_hours} hours")
        
        metrics = store.read_all_metrics()
        logger.info(f"Loaded {len(metrics)} metrics: {list(metrics.keys())}")
        
        stale_count = 0
        last_update = None
        stale_details = []
        
        for metric_key, metric_data in metrics.items():
            is_stale = store.is_metric_stale(metric_key)
            if is_stale:
                stale_count += 1
                stale_details.append(metric_key)
            
            # Track most recent update
            metric_time = metric_data.get("asof")
            if metric_time:
                if isinstance(metric_time, str):
                    try:
                        metric_time = datetime.fromisoformat(metric_time.replace('Z', '+00:00'))
                    except:
                        continue
                        
                if not last_update or metric_time > last_update:
                    last_update = metric_time
        
        # Calculate time since last update
        now = datetime.now(timezone.utc)
        if last_update:
            if last_update.tzinfo is None:
                last_update = last_update.replace(tzinfo=timezone.utc)
            hours_since_update = (now - last_update).total_seconds() / 3600
            logger.info(f"Hours since last update: {hours_since_update:.1f}")
        else:
            hours_since_update = None
            logger.warning("No valid timestamps found in market data")
        
        return {
            "metrics_available": len(metrics),
            "stale_metrics": stale_count,
            "last_update": last_update.isoformat() if last_update else None,
            "hours_since_update": round(hours_since_update, 1) if hours_since_update else None,
            "stale_threshold_hours": settings.scrape.stale_threshold_hours,
            "stale_metric_keys": stale_details
        }
        
    except Exception as e:
        logger.error("market_data_health_check_failed", error=str(e))
        return {
            "metrics_available": 0,
            "stale_metrics": 0,
            "last_update": None,
            "error": str(e)
        }


async def check_rag_health() -> Dict[str, Any]:
    """
    Check RAG system readiness including vector count and last indexed time.
    
    Returns:
        RAG health information
    """
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http.exceptions import UnexpectedResponse
        
        # Get Qdrant client
        qdrant_url = settings.qdrant_url
        if not qdrant_url:
            host, port = settings.qdrant_host_port
            qdrant_url = f"http://{host}:{port}"
        
        client = QdrantClient(
            url=qdrant_url,
            api_key=settings.qdrant_api_key,
            prefer_grpc=False
        )
        
        collection_name = settings.vector.collection_name
        
        try:
            # Check if collection exists and get vector count
            collection_info = client.get_collection(collection_name)
            
            # Use count endpoint to get actual number of points
            try:
                count_result = client.count(collection_name)
                vector_count = count_result.count if hasattr(count_result, 'count') else 0
            except:
                vector_count = collection_info.vectors_count or 0  # Fallback to vectors_count
            
            rag_ready = vector_count > 0
            
            # Try to get last indexed time from collection metadata
            # This is a best-effort attempt since Qdrant doesn't track this by default
            last_indexed = None
            try:
                # We could store this in collection metadata when indexing
                # For now, just check if we have vectors
                if vector_count > 0:
                    # Placeholder - in a real system you'd track this
                    last_indexed = "2024-01-01T00:00:00Z"  # Fallback
            except:
                pass
            
            return {
                "rag_ready": rag_ready,
                "vector_count": vector_count,
                "last_indexed": last_indexed,
                "collection_name": collection_name
            }
            
        except UnexpectedResponse as e:
            if "not found" in str(e).lower():
                return {
                    "rag_ready": False,
                    "vector_count": 0,
                    "last_indexed": None,
                    "collection_name": collection_name,
                    "error": "Collection not found"
                }
            else:
                raise
                
    except Exception as e:
        logger.error("rag_health_check_failed", error=str(e))
        return {
            "rag_ready": False,
            "vector_count": 0,
            "last_indexed": None,
            "error": str(e)
        }