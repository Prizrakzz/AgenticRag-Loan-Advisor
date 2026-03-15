#!/usr/bin/env python3
"""Database setup script for the loan approval system."""

import sys
import argparse
from pathlib import Path

# Add app directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.db.database import engine, create_tables, drop_tables, check_connection
from app.utils.logger import get_logger
from app.utils.config import settings

logger = get_logger(__name__)


def setup_database(reset: bool = False):
    """Set up the database tables using SQLAlchemy metadata."""
    logger.info("Setting up database using SQLAlchemy metadata.create_all()")
    logger.info(f"Database URL: {settings.database.url}")
    
    # Check connection first
    if not check_connection():
        logger.error("Cannot connect to database. Please check your DATABASE_URL.")
        return False
    
    try:
        if reset:
            logger.warning("Dropping existing tables...")
            drop_tables()
        
        # Use SQLAlchemy metadata to create tables
        logger.info("Creating tables using SQLAlchemy...")
        create_tables()
        
        logger.info("Database setup completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Database setup failed: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Set up the loan approval database")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop existing tables before creating new ones"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check database connection"
    )
    
    args = parser.parse_args()
    
    if args.check_only:
        if check_connection():
            print("✅ Database connection successful")
            sys.exit(0)
        else:
            print("❌ Database connection failed")
            sys.exit(1)
    
    success = setup_database(reset=args.reset)
    
    if success:
        print("✅ Database setup completed successfully")
        sys.exit(0)
    else:
        print("❌ Database setup failed")
        sys.exit(1)


if __name__ == "__main__":
    main() 