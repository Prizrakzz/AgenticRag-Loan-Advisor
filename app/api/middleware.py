"""FastAPI middleware for CORS, logging, and error handling."""

import time
import uuid
from typing import Callable
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from starlette.middleware.base import BaseHTTPMiddleware

from ..utils.config import settings
from ..utils.logger import get_logger
from .schemas import ErrorResponse

logger = get_logger(__name__)


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware for request ID generation and timing."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Add request ID and timing to all requests.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
        
        Returns:
            Response with tracking headers
        """
        # Generate request ID if not provided
        request_id = request.headers.get("X-Request-ID", f"REQ-{uuid.uuid4().hex[:12].upper()}")
        request.state.request_id = request_id
        request.state.start_time = time.time()
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate processing time
            processing_time = time.time() - request.state.start_time
            
            # Add tracking headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Processing-Time"] = f"{processing_time:.3f}s"
            
            # Log successful request
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                processing_time_ms=int(processing_time * 1000),
                request_id=request_id,
                user_id=getattr(request.state, 'user_id', None)
            )
            
            return response
            
        except Exception as e:
            processing_time = time.time() - request.state.start_time
            
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                processing_time_ms=int(processing_time * 1000),
                request_id=request_id,
                error=str(e),
                user_id=getattr(request.state, 'user_id', None)
            )
            
            # Re-raise to let error handlers deal with it
            raise


class SecurityMiddleware(BaseHTTPMiddleware):
    """Middleware for security headers and validation."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Add security headers and basic validation.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
        
        Returns:
            Response with security headers
        """
        # Check content length
        content_length = request.headers.get("content-length")
        if content_length:
            size = int(content_length)
            max_size = 1024 * 1024  # 1MB limit
            
            if size > max_size:
                logger.warning(
                    "request_too_large",
                    size=size,
                    max_size=max_size,
                    path=request.url.path,
                    request_id=getattr(request.state, 'request_id', 'unknown')
                )
                
                return JSONResponse(
                    status_code=413,
                    content=jsonable_encoder({
                        "error": "REQUEST_TOO_LARGE",
                        "message": "Request entity too large",
                        "max_size_mb": max_size // (1024 * 1024)
                    })
                )
        
        # Process request
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Add HSTS for HTTPS
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response


def setup_cors(app: FastAPI):
    """
    Setup CORS middleware based on environment.
    
    Args:
        app: FastAPI application instance
    """
    environment = getattr(settings, 'environment', 'development')
    
    if environment == "development":
        # Specific CORS origins for development
        allowed_origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000"
        ]
        
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "X-Processing-Time"]
        )
        
        logger.info("cors_configured", mode="development", allow_origins=allowed_origins)
        
    else:
        # Restrictive CORS for production
        allowed_origins = [
            "https://yourdomain.com",
            "https://www.yourdomain.com",
            "https://app.yourdomain.com"
        ]
        
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=[
                "Accept",
                "Accept-Language",
                "Content-Language",
                "Content-Type",
                "Authorization",
                "X-Request-ID"
            ],
            expose_headers=["X-Request-ID", "X-Processing-Time"]
        )
        
        logger.info("cors_configured", mode="production", allow_origins=allowed_origins)


def setup_trusted_hosts(app: FastAPI):
    """
    Setup trusted host middleware for production.
    
    Args:
        app: FastAPI application instance
    """
    environment = getattr(settings, 'environment', 'development')
    
    if environment != "development":
        trusted_hosts = [
            "yourdomain.com",
            "*.yourdomain.com",
            "localhost",
            "127.0.0.1"
        ]
        
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=trusted_hosts
        )
        
        logger.info("trusted_hosts_configured", hosts=trusted_hosts)


def setup_error_handlers(app: FastAPI):
    """
    Setup global error handlers.
    
    Args:
        app: FastAPI application instance
    """
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions with consistent format."""
        request_id = getattr(request.state, 'request_id', 'unknown')
        
        # Log the exception
        logger.warning(
            "http_exception",
            status_code=exc.status_code,
            detail=exc.detail,
            path=request.url.path,
            request_id=request_id,
            user_id=getattr(request.state, 'user_id', None)
        )
        
        # Create error response
        error_response = ErrorResponse(
            error=f"HTTP_{exc.status_code}",
            message=exc.detail,
            request_id=request_id
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(error_response.model_dump()),
            headers={"X-Request-ID": request_id}
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions."""
        request_id = getattr(request.state, 'request_id', 'unknown')
        
        # Log the exception
        logger.error(
            "unhandled_exception",
            error=str(exc),
            error_type=type(exc).__name__,
            path=request.url.path,
            request_id=request_id,
            user_id=getattr(request.state, 'user_id', None),
            exc_info=True
        )
        
        # Create sanitized error response
        error_response = ErrorResponse(
            error="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred. Please try again later.",
            request_id=request_id
        )
        
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(error_response.model_dump()),
            headers={"X-Request-ID": request_id}
        )
    
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Handle validation errors."""
        request_id = getattr(request.state, 'request_id', 'unknown')
        
        logger.warning(
            "validation_error",
            error=str(exc),
            path=request.url.path,
            request_id=request_id
        )
        
        error_response = ErrorResponse(
            error="VALIDATION_ERROR",
            message=str(exc),
            request_id=request_id
        )
        
        return JSONResponse(
            status_code=400,
            content=jsonable_encoder(error_response.model_dump()),
            headers={"X-Request-ID": request_id}
        )


def setup_middleware(app: FastAPI):
    """
    Setup all middleware for the FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    # Order matters - middleware is applied in reverse order of addition
    
    # 1. Error handlers (should be set up first)
    setup_error_handlers(app)
    
    # 2. Security middleware
    app.add_middleware(SecurityMiddleware)
    
    # 3. Request tracking middleware
    app.add_middleware(RequestTrackingMiddleware)
    
    # 4. CORS (should be close to the top)
    setup_cors(app)
    
    # 5. Trusted hosts (production only)
    setup_trusted_hosts(app)
    
    logger.info("middleware_configured")


# Optional: Prometheus metrics middleware
def setup_metrics(app: FastAPI):
    """
    Setup Prometheus metrics collection (optional).
    
    Args:
        app: FastAPI application instance
    """
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        
        instrumentator = Instrumentator(
            should_group_status_codes=False,
            should_ignore_untemplated=True,
            should_respect_env_var=True,
            should_instrument_requests_inprogress=True,
            excluded_handlers=["/health", "/metrics"],
            env_var_name="ENABLE_METRICS",
            inprogress_name="fastapi_inprogress",
            inprogress_labels=True,
        )
        
        instrumentator.instrument(app)
        instrumentator.expose(app, endpoint="/metrics")
        
        logger.info("prometheus_metrics_enabled", endpoint="/metrics")
        
    except ImportError:
        logger.info("prometheus_metrics_not_available", reason="instrumentator not installed")
    except Exception as e:
        logger.warning("prometheus_metrics_setup_failed", error=str(e)) 