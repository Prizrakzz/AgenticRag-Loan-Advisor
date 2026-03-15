"""Structured logging configuration for the loan approval system."""

import logging
import sys
from typing import Any, Dict, Optional

import structlog
from structlog.typing import EventDict

from .config import settings


def add_request_id(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add request ID to log events if available."""
    # This will be populated by FastAPI middleware
    request_id = getattr(logger, '_request_id', None)
    if request_id:
        event_dict['request_id'] = request_id
    return event_dict


def add_timestamp(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add ISO timestamp to log events."""
    import datetime
    event_dict['timestamp'] = datetime.datetime.utcnow().isoformat() + "Z"
    return event_dict


def setup_logging():
    """Configure structured logging for the application."""
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.logging.level.upper()),
    )
    
    # Configure structlog processors
    processors = [
        structlog.contextvars.merge_contextvars,
        add_request_id,
        add_timestamp,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
    ]
    
    if settings.logging.format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.extend([
            structlog.dev.ConsoleRenderer(colors=True),
        ])
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.logging.level.upper())
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a configured logger instance."""
    return structlog.get_logger(name)


class RequestContextLogger:
    """Logger with request context for tracking user sessions."""
    
    def __init__(self, request_id: str, username: Optional[str] = None):
        self.logger = get_logger("loan_approval")
        self.request_id = request_id
        self.username = username
        
        # Bind context to logger
        self.logger = self.logger.bind(
            request_id=request_id,
            username=username
        )
    
    def info(self, event: str, **kwargs):
        """Log info level event."""
        self.logger.info(event, **kwargs)
    
    def warning(self, event: str, **kwargs):
        """Log warning level event."""
        self.logger.warning(event, **kwargs)
    
    def error(self, event: str, **kwargs):
        """Log error level event."""
        self.logger.error(event, **kwargs)
    
    def debug(self, event: str, **kwargs):
        """Log debug level event."""
        self.logger.debug(event, **kwargs)


class NodeLogger:
    """Logger for LangGraph nodes with automatic state logging."""
    
    def __init__(self, node_name: str, request_logger: RequestContextLogger):
        self.node_name = node_name
        self.request_logger = request_logger
        self.logger = request_logger.logger.bind(node=node_name)
    
    def log_input(self, state: Dict[str, Any]):
        """Log node input state."""
        self.logger.info(
            "node_input",
            node=self.node_name,
            input_state=self._sanitize_state(state)
        )
    
    def log_output(self, state: Dict[str, Any]):
        """Log node output state."""
        self.logger.info(
            "node_output", 
            node=self.node_name,
            output_state=self._sanitize_state(state)
        )
    
    def log_error(self, error: Exception, state: Dict[str, Any]):
        """Log node error with state context."""
        self.logger.error(
            "node_error",
            node=self.node_name,
            error=str(error),
            error_type=type(error).__name__,
            state=self._sanitize_state(state)
        )
    
    def info(self, event: str, **kwargs):
        """Log info level event with node context."""
        self.logger.info(event, node=self.node_name, **kwargs)
    
    def warning(self, event: str, **kwargs):
        """Log warning level event with node context."""
        self.logger.warning(event, node=self.node_name, **kwargs)
    
    def error(self, event: str, **kwargs):
        """Log error level event with node context."""
        self.logger.error(event, node=self.node_name, **kwargs)
    
    def _sanitize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive data from state before logging."""
        sanitized = state.copy()
        
        # Remove or mask sensitive fields
        sensitive_fields = ['client', 'username']  # Add more as needed
        for field in sensitive_fields:
            if field in sanitized:
                if field == 'username':
                    sanitized[field] = "***masked***"
                elif field == 'client':
                    # Keep only non-sensitive client fields
                    if isinstance(sanitized[field], dict):
                        sanitized[field] = {
                            'client_id': sanitized[field].get('client_id'),
                            'risk_grade': sanitized[field].get('risk_grade'),
                            'annual_income': sanitized[field].get('annual_income', 0) > 0,  # Boolean instead of amount
                        }
        
        return sanitized


# Initialize logging on module import
setup_logging() 