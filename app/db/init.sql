-- Database initialization script for loan approval system
-- Run this to create tables if not using SQLAlchemy metadata.create_all()

-- Customer table (from Clientbase_scored.csv)
CREATE TABLE IF NOT EXISTS customers (
    client_id INTEGER PRIMARY KEY,
    annual_income NUMERIC,
    ccavg_income_ratio NUMERIC,
    ccavg_spend NUMERIC,
    credit_card_with_bank INTEGER,
    digital_user INTEGER,
    dti_z NUMERIC,
    education_level INTEGER,
    exp_age_gap INTEGER,
    experience_years INTEGER,
    family_size INTEGER,
    has_invest_acct INTEGER,
    has_personal_loan INTEGER,
    income_per_person_z NUMERIC,
    mortgage_balance_z NUMERIC,
    online_banking INTEGER,
    securities_acct INTEGER,
    risk_score NUMERIC,
    risk_grade TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for customer table
CREATE INDEX IF NOT EXISTS idx_customers_client_id ON customers(client_id);
CREATE INDEX IF NOT EXISTS idx_customers_risk_grade ON customers(risk_grade);
CREATE INDEX IF NOT EXISTS idx_customers_risk_score ON customers(risk_score);

-- Audit log table for LangGraph node tracking
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    req_id TEXT NOT NULL,
    username TEXT,
    node TEXT NOT NULL,
    state JSONB NOT NULL,
    ts TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for audit log table
CREATE INDEX IF NOT EXISTS idx_audit_log_req_id ON audit_log(req_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_username ON audit_log(username);
CREATE INDEX IF NOT EXISTS idx_audit_log_node ON audit_log(node);
CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(ts);

-- Market cache table (SQLite format for reference - will be created separately)
-- This is just for documentation; actual SQLite table created by scraper
/*
CREATE TABLE market_snapshot (
    key TEXT PRIMARY KEY,
    value REAL,
    asof TEXT,
    extra_json TEXT
);
*/

-- Add comments for clarity
COMMENT ON TABLE customers IS 'Customer data loaded from Clientbase_scored.csv with risk scores';
COMMENT ON COLUMN customers.client_id IS 'Internal row ID; primary key';
COMMENT ON COLUMN customers.annual_income IS 'Annual income in $K';
COMMENT ON COLUMN customers.ccavg_income_ratio IS 'ccavg_spend / annual_income';
COMMENT ON COLUMN customers.ccavg_spend IS 'Avg monthly credit card spend in $K';
COMMENT ON COLUMN customers.credit_card_with_bank IS '1 if customer has bank-issued credit card';
COMMENT ON COLUMN customers.digital_user IS 'online_banking OR credit_card_with_bank';
COMMENT ON COLUMN customers.dti_z IS 'z-score of mortgage_balance / annual_income';
COMMENT ON COLUMN customers.education_level IS '1=Undergrad, 2=Graduate, 3=Advanced/Professional';
COMMENT ON COLUMN customers.exp_age_gap IS 'max(age - experience_years, 0)';
COMMENT ON COLUMN customers.experience_years IS 'Years of professional experience';
COMMENT ON COLUMN customers.family_size IS 'Household members';
COMMENT ON COLUMN customers.has_invest_acct IS 'securities_acct OR cd_account';
COMMENT ON COLUMN customers.has_personal_loan IS '1 = took/approved for personal loan (current proxy label)';
COMMENT ON COLUMN customers.income_per_person_z IS 'z-scored income per family member';
COMMENT ON COLUMN customers.mortgage_balance_z IS 'z-scored mortgage balance';
COMMENT ON COLUMN customers.online_banking IS 'Uses online banking';
COMMENT ON COLUMN customers.securities_acct IS 'Has securities/investment account';
COMMENT ON COLUMN customers.risk_score IS '1 - p(approved); higher = riskier';
COMMENT ON COLUMN customers.risk_grade IS 'Quartiles of risk_score (A safest, D riskiest)';

COMMENT ON TABLE audit_log IS 'Audit trail for LangGraph node executions';
COMMENT ON COLUMN audit_log.req_id IS 'Request ID for correlation across nodes';
COMMENT ON COLUMN audit_log.username IS 'Authenticated user making the request';
COMMENT ON COLUMN audit_log.node IS 'LangGraph node name';
COMMENT ON COLUMN audit_log.state IS 'LangGraph state as JSON (sanitized)';
COMMENT ON COLUMN audit_log.ts IS 'Timestamp of node execution'; 