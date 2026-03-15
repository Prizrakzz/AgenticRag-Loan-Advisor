"""FastAPI application factory and main entry point."""

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import time
import traceback
import os
from datetime import datetime

from .auth import router as auth_router
from .loan import router as loan_router
from .middleware import setup_middleware, setup_metrics
from .deps import (
    setup_rate_limiting, get_request_id, check_database_health,
    check_vector_store_health, check_market_data_health, check_rag_health
)
from .schemas import HealthResponse, StatusResponse, DatabaseStatus, VectorStoreStatus, MarketDataStatus
from ..utils.config import settings
from ..utils.logger import get_logger, setup_logging
from ..scrape.scheduler import start_market_data_scheduler, stop_market_data_scheduler
from starlette.middleware import Middleware

logger = get_logger(__name__)

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]

cors = Middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,   # dev origins only
    allow_credentials=True,          # allow Authorization/cookies if needed
    allow_methods=["*"],             # includes OPTIONS (preflight)
    allow_headers=["*"],             # includes Authorization, Content-Type
    expose_headers=["X-Request-ID", "X-Processing-Time"],
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown tasks.
    
    Args:
        app: FastAPI application instance
    """
    # Startup
    logger.info("application_starting")
    
    try:
        # Initialize logging
        setup_logging()
        
        # Start market data scheduler
        start_market_data_scheduler()
        logger.info("market_data_scheduler_started")
        
        # Initialize memory/chat database tables (SQLite-safe migration)
        try:
            import sqlite3
            from app.db.models import ensure_chat_tables_exist
            from app.utils.config import settings
            
            db_path = settings.database.url.replace("sqlite:///", "")
            with sqlite3.connect(db_path) as conn:
                ensure_chat_tables_exist(conn)
            logger.info("memory_tables_initialized")
        except Exception as e:
            logger.warning("memory_table_init_failed", error=str(e))
            # Continue startup - memory will fall back to in-memory store
        
        # Additional startup tasks could go here
        # - Database migrations
        # - Cache warming
        # - Health checks
        
        logger.info("application_started_successfully")
        
        yield
        
    finally:
        # Shutdown
        logger.info("application_shutting_down")
        
        try:
            # Stop market data scheduler
            stop_market_data_scheduler()
            logger.info("market_data_scheduler_stopped")
            
            # Additional cleanup tasks could go here
            # - Close database connections
            # - Cleanup temporary files
            # - Flush logs
            
        except Exception as e:
            logger.error("application_shutdown_error", error=str(e))
        
        logger.info("application_shutdown_complete")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.
    
    Returns:
        Configured FastAPI application
    """
    # Assert required configuration is present
    assert hasattr(settings, 'openai_api_key') and settings.openai_api_key, "Missing OPENAI_API_KEY!"
    
    # Check Qdrant configuration (either URL or host+port)
    if not settings.qdrant_url:
        host, port = settings.qdrant_host_port
        qdrant_url = f"http://{host}:{port}"
        assert host and port, "Missing Qdrant configuration (QDRANT_URL or vector.host/port)!"
    else:
        qdrant_url = settings.qdrant_url
    
    assert hasattr(settings, 'database') and settings.database.url, "Missing DATABASE_URL!"
    
    logger.info("✅ Required configuration validated", 
               openai_configured=bool(settings.openai_api_key),
               qdrant_configured=bool(qdrant_url),
               database_configured=bool(getattr(settings, 'database', None)))
    
    # Create FastAPI app
    app = FastAPI(
        title="Loan Approval Assistant API",
        description="AI-powered loan approval system with deterministic decision logic",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        middleware=[cors],
    )
    
    # Add custom exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Return generic error to clients; log details server-side."""
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
    
    # Setup middleware
    setup_middleware(app)
    
    # Setup rate limiting
    setup_rate_limiting(app)
    
    # Setup optional metrics
    setup_metrics(app)
    
    # Include routers
    app.include_router(auth_router)
    app.include_router(loan_router, prefix="/v1")
    
    # Include loan router at root level for legacy compatibility 
    app.include_router(loan_router)

    
    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "Loan Approval Assistant API",
            "version": "1.0.0",
            "description": "AI-powered loan approval system",
            "docs": "/docs",
            "health": "/health",
            "status": "/status"
        }
    
    # Health check endpoint
    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="Health check",
        description="Quick health check for load balancers"
    )
    async def health_check(request_id: str = Depends(get_request_id)):
        """
        Quick health check endpoint.
        
        Args:
            request_id: Request ID for tracking
        
        Returns:
            Basic health status
        """
        try:
            # Quick checks
            db_health = await check_database_health()
            vector_health = await check_vector_store_health()
            market_health = await check_market_data_health()
            
            # Determine component status
            db_ok = db_health.get("connected", False)
            vector_ok = vector_health.get("connected", False)
            market_ok = market_health.get("metrics_available", 0) > 0
            
            # Check single-agent system status
            single_agent_enabled = os.getenv("SINGLE_AGENT_ENABLED", "true").lower() != "false"
            
            # Check RAG readiness
            rag_status = await check_rag_health()
            
            overall_status = "healthy" if all([db_ok, vector_ok, market_ok]) else "degraded"
            
            return HealthResponse(
                status=overall_status,
                timestamp=datetime.utcnow(),
                version="1.0.0",
                database="connected" if db_ok else "disconnected",
                vector_store="connected" if vector_ok else "disconnected",
                market_data="available" if market_ok else "unavailable",
                single_agent=single_agent_enabled,
                rag_ready=rag_status.get("rag_ready", False),
                vector_count=rag_status.get("vector_count", 0),
                last_indexed=rag_status.get("last_indexed")
            )
            
        except Exception as e:
            logger.error("health_check_failed", request_id=request_id, error=str(e))
            
            return HealthResponse(
                status="unhealthy",
                timestamp=datetime.utcnow(),
                version="1.0.0",
                database="unknown",
                vector_store="unknown",
                market_data="unknown",
                single_agent=os.getenv("SINGLE_AGENT_ENABLED", "true").lower() != "false",
                rag_ready=False,
                vector_count=0,
                last_indexed=None
            )
    
    # Detailed status endpoint
    @app.get(
        "/status",
        response_model=StatusResponse,
        tags=["Health"],
        summary="Detailed status",
        description="Detailed system status and health information"
    )
    async def status_check(request_id: str = Depends(get_request_id)):
        """
        Detailed status check endpoint.
        
        Args:
            request_id: Request ID for tracking
        
        Returns:
            Detailed system status
        """
        try:
            # Detailed health checks
            db_health = await check_database_health()
            vector_health = await check_vector_store_health()
            market_health = await check_market_data_health()
            
            # Format responses
            db_status = DatabaseStatus(
                connected=db_health.get("connected", False),
                customer_count=db_health.get("customer_count"),
                audit_log_count=db_health.get("audit_log_count")
            )
            
            vector_status = VectorStoreStatus(
                connected=vector_health.get("connected", False),
                collection_exists=vector_health.get("collection_exists", False),
                document_count=vector_health.get("document_count")
            )
            
            market_status = MarketDataStatus(
                metrics_available=market_health.get("metrics_available", 0),
                stale_metrics=market_health.get("stale_metrics", 0),
                last_update=market_health.get("last_update")
            )
            
            # Determine overall status
            all_healthy = all([
                db_status.connected,
                vector_status.connected,
                market_status.metrics_available > 0
            ])
            
            overall_status = "healthy" if all_healthy else "degraded"
            
            return StatusResponse(
                status=overall_status,
                timestamp=datetime.utcnow(),
                database=db_status,
                vector_store=vector_status,
                market_data=market_status
            )
            
        except Exception as e:
            logger.error("status_check_failed", request_id=request_id, error=str(e))
            
            # Return error status
            return StatusResponse(
                status="error",
                timestamp=datetime.utcnow(),
                database=DatabaseStatus(connected=False),
                vector_store=VectorStoreStatus(connected=False, collection_exists=False),
                market_data=MarketDataStatus(metrics_available=0, stale_metrics=0)
            )
    
    # Workflow info endpoint
    @app.get(
        "/workflow/info",
        tags=["Workflow"],
        summary="Workflow information",
        description="Get information about the loan approval workflow"
    )
    async def workflow_info():
        """
        Get workflow structure information.
        
        Returns:
            Workflow information
        """
        try:
            from ..graph.workflow import get_workflow_info
            return get_workflow_info()
            
        except Exception as e:
            logger.error("workflow_info_failed", error=str(e))
            return JSONResponse(
                status_code=500,
                content={"error": "Unable to retrieve workflow information"}
            )
    
    logger.info("fastapi_app_created")
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    # Configuration from settings
    host = getattr(settings.api, 'host', '0.0.0.0')
    port = getattr(settings.api, 'port', 8000)
    reload = getattr(settings.api, 'reload', False)
    workers = getattr(settings.api, 'workers', 1)
    
    logger.info(
        "starting_uvicorn_server",
        host=host,
        port=port,
        reload=reload,
        workers=workers
    )
    
    # Run with uvicorn
    uvicorn.run(
        "app.api.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,  # Workers > 1 incompatible with reload
        log_config=None,  # Use our custom logging
        access_log=False   # We handle access logging in middleware
    ) 