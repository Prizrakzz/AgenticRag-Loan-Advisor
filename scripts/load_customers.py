#!/usr/bin/env python3
"""Customer data loader for the loan approval system."""

import sys
import argparse
from pathlib import Path
import pandas as pd
from typing import Dict, Any

# Add app directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.db.database import get_db_session
from app.db.models import Customer
from app.utils.logger import get_logger
from app.utils.config import settings

logger = get_logger(__name__)


def validate_csv_columns(df: pd.DataFrame) -> bool:
    """Validate that CSV has required columns."""
    required_columns = {
        'client_id', 'annual_income', 'ccavg_income_ratio', 'ccavg_spend',
        'credit_card_with_bank', 'digital_user', 'dti_z', 'education_level',
        'exp_age_gap', 'experience_years', 'family_size', 'has_invest_acct',
        'has_personal_loan', 'income_per_person_z', 'mortgage_balance_z',
        'online_banking', 'securities_acct', 'risk_grade'
    }
    
    csv_columns = set(df.columns)
    missing_columns = required_columns - csv_columns
    
    if missing_columns:
        logger.error(f"Missing required columns: {missing_columns}")
        return False
    
    extra_columns = csv_columns - required_columns
    if extra_columns:
        logger.info(f"Extra columns in CSV (will be ignored): {extra_columns}")
    
    return True


def clean_row_data(row: pd.Series) -> Dict[str, Any]:
    """Clean and convert row data for database insertion."""
    data = {}
    
    # Handle numeric columns - replace NaN with None
    numeric_columns = [
        'annual_income', 'ccavg_income_ratio', 'ccavg_spend', 'dti_z',
        'income_per_person_z', 'mortgage_balance_z'
    ]
    
    integer_columns = [
        'client_id', 'credit_card_with_bank', 'digital_user', 'education_level',
        'exp_age_gap', 'experience_years', 'family_size', 'has_invest_acct',
        'has_personal_loan', 'online_banking', 'securities_acct'
    ]
    
    # Process all columns from the model
    model_columns = [
        'client_id', 'annual_income', 'ccavg_income_ratio', 'ccavg_spend',
        'credit_card_with_bank', 'digital_user', 'dti_z', 'education_level',
        'exp_age_gap', 'experience_years', 'family_size', 'has_invest_acct',
        'has_personal_loan', 'income_per_person_z', 'mortgage_balance_z',
        'online_banking', 'securities_acct', 'risk_grade'
    ]
    
    for col in model_columns:
        if col not in row.index:
            continue  # Skip if column not in CSV
        
        value = row[col]
        
        # Handle NaN values
        if pd.isna(value):
            data[col] = None
        elif col in integer_columns:
            data[col] = int(value) if not pd.isna(value) else None
        elif col in numeric_columns:
            data[col] = float(value) if not pd.isna(value) else None
        elif col == 'risk_grade':
            data[col] = str(value).strip() if not pd.isna(value) else None
        else:
            data[col] = value
    
    return data


def load_customers_from_csv(csv_path: str, batch_size: int = 100, upsert: bool = True) -> bool:
    """Load customer data from CSV into database."""
    logger.info(f"Loading customers from: {csv_path}")
    
    csv_file = Path(csv_path)
    if not csv_file.exists():
        logger.error(f"CSV file not found: {csv_path}")
        return False
    
    try:
        # Read CSV file
        logger.info("Reading CSV file...")
        df = pd.read_csv(csv_file)
        logger.info(f"Loaded {len(df)} rows from CSV")
        
        # Validate columns
        if not validate_csv_columns(df):
            return False
        
        # Load data in batches
        with get_db_session() as db:
            total_inserted = 0
            total_updated = 0
            
            for start_idx in range(0, len(df), batch_size):
                batch_df = df.iloc[start_idx:start_idx + batch_size]
                batch_inserted = 0
                batch_updated = 0
                
                for _, row in batch_df.iterrows():
                    try:
                        # Clean row data
                        customer_data = clean_row_data(row)
                        client_id = customer_data['client_id']
                        
                        if upsert:
                            # Try to find existing customer
                            existing_customer = db.query(Customer).filter(
                                Customer.client_id == client_id
                            ).first()
                            
                            if existing_customer:
                                # Update existing customer
                                for key, value in customer_data.items():
                                    if key != 'client_id':  # Don't update PK
                                        setattr(existing_customer, key, value)
                                batch_updated += 1
                            else:
                                # Insert new customer
                                new_customer = Customer(**customer_data)
                                db.add(new_customer)
                                batch_inserted += 1
                        else:
                            # Insert only (will fail if duplicate)
                            new_customer = Customer(**customer_data)
                            db.add(new_customer)
                            batch_inserted += 1
                    
                    except Exception as e:
                        logger.warning(f"Error processing row {client_id}: {e}")
                        continue
                
                # Commit batch
                try:
                    db.commit()
                    total_inserted += batch_inserted
                    total_updated += batch_updated
                    logger.info(f"Batch {start_idx//batch_size + 1}: "
                              f"inserted {batch_inserted}, updated {batch_updated}")
                except Exception as e:
                    logger.error(f"Failed to commit batch: {e}")
                    db.rollback()
                    return False
        
        logger.info(f"Customer loading completed: {total_inserted} inserted, {total_updated} updated")
        return True
        
    except Exception as e:
        logger.error(f"Failed to load customers: {e}")
        return False


def count_customers() -> int:
    """Count total customers in database."""
    try:
        with get_db_session() as db:
            count = db.query(Customer).count()
            return count
    except Exception as e:
        logger.error(f"Failed to count customers: {e}")
        return -1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Load customer data from CSV")
    parser.add_argument(
        "--csv-path",
        default=settings.data.customer_file,
        help=f"Path to CSV file (default: {settings.data.customer_file})"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for database inserts (default: 100)"
    )
    parser.add_argument(
        "--no-upsert",
        action="store_true",
        help="Insert only, don't update existing records"
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="Only count existing customers"
    )
    
    args = parser.parse_args()
    
    if args.count_only:
        count = count_customers()
        if count >= 0:
            print(f"Total customers in database: {count}")
            sys.exit(0)
        else:
            print("Failed to count customers")
            sys.exit(1)
    
    success = load_customers_from_csv(
        csv_path=args.csv_path,
        batch_size=args.batch_size,
        upsert=not args.no_upsert
    )
    
    if success:
        final_count = count_customers()
        print(f"✅ Customer loading completed. Total customers: {final_count}")
        sys.exit(0)
    else:
        print("❌ Customer loading failed")
        sys.exit(1)


if __name__ == "__main__":
    main() 