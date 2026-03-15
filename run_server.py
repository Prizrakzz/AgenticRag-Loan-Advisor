#!/usr/bin/env python3
"""
Simple server entry point for the Loan Approval Assistant API.

This script provides a convenient way to start the FastAPI server
with proper configuration and logging.
"""

import os
import sys
import uvicorn
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.utils.config import settings
from app.utils.logger import setup_logging, get_logger

# Setup logging
setup_logging()
logger = get_logger(__name__)


def main():
    """Main entry point for the server."""
    logger.info("starting_loan_approval_api_server")
    
    # Server configuration
    config = {
        "app": "app.api.main:app",
        "host": getattr(settings.api, 'host', '0.0.0.0'),
        "port": getattr(settings.api, 'port', 8000),
        "reload": getattr(settings.api, 'reload', False),
        "workers": getattr(settings.api, 'workers', 1),
        "log_config": None,  # Use our custom logging
        "access_log": False   # Handle access logging in middleware
    }
    
    # Adjust workers for reload mode
    if config["reload"] and config["workers"] > 1:
        logger.warning("reducing_workers_for_reload_mode", workers=1)
        config["workers"] = 1
    
    logger.info(
        "server_configuration",
        host=config["host"],
        port=config["port"],
        reload=config["reload"],
        workers=config["workers"]
    )
    
    try:
        # Start the server
        uvicorn.run(**config)
    except KeyboardInterrupt:
        logger.info("server_stopped_by_user")
    except Exception as e:
        logger.error("server_startup_failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main() 