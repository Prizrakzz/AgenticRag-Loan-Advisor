#!/usr/bin/env python3
"""Load customer data into the new database"""

import pandas as pd
import sqlite3

def main():
    # Load customer data and insert into new database
    df = pd.read_csv('data/Clientbase_scored.csv')
    conn = sqlite3.connect('data/app_new.db')

    print(f'Loading {len(df)} customers...')

    for i, row in df.iterrows():
        conn.execute('''
            INSERT INTO customers (
                client_id, client_name, education_level, family_size,
                employment_status, employer_name, annual_income,
                existing_loan_amount, past_defaults, risk_grade, risk_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            row['client_id'],
            f'Client_{row["client_id"]}',
            row.get('education_level', 'Unknown'),
            row.get('family_size', 1),
            'Employed',
            f'Employer_{row["client_id"]}',
            row['annual_income'],
            0.0,
            0,
            row['risk_grade'],
            0.0
        ))
        
        if (i + 1) % 100 == 0:
            print(f'Loaded {i + 1} customers...')

    conn.commit()

    # Verify the data
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM customers')
    total = cursor.fetchone()[0]

    cursor.execute('SELECT * FROM customers LIMIT 3')
    samples = cursor.fetchall()

    print(f'✅ Loaded {total} customers successfully!')
    print('Sample customers:')
    for sample in samples:
        print(f'  ID: {sample[0]}, Client ID: {sample[1]}, Name: {sample[2]}, Risk Grade: {sample[10]}')

    conn.close()

if __name__ == "__main__":
    main() 