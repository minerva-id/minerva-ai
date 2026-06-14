-- ============================================================
-- Minerva AI — Supabase Database Migration
-- Run this in the Supabase SQL Editor to set up all tables.
-- ============================================================

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. Trades Journal
-- Records all completed trades for performance analysis.
-- ============================================================
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    entry_price DOUBLE PRECISION NOT NULL,
    exit_price DOUBLE PRECISION NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    pnl DOUBLE PRECISION NOT NULL,
    pnl_pct DOUBLE PRECISION NOT NULL,
    fees_total DOUBLE PRECISION DEFAULT 0,
    entry_time TIMESTAMPTZ NOT NULL,
    exit_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_seconds INTEGER DEFAULT 0,
    signal_score DOUBLE PRECISION,
    reasoning TEXT DEFAULT '',
    strategy TEXT DEFAULT 'minerva_v1',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_exit_time ON trades(exit_time DESC);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);

-- ============================================================
-- 2. Orders Log
-- Records all order events for auditing.
-- ============================================================
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    order_type TEXT NOT NULL,
    price DOUBLE PRECISION,
    amount DOUBLE PRECISION NOT NULL,
    filled_amount DOUBLE PRECISION DEFAULT 0,
    average_fill_price DOUBLE PRECISION,
    status TEXT NOT NULL,
    exchange_order_id TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    signal_score DOUBLE PRECISION,
    reasoning TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

-- ============================================================
-- 3. Reasoning Logs
-- Records AI decision reasoning for analysis and learning.
-- ============================================================
CREATE TABLE IF NOT EXISTS reasoning_logs (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    reasoning TEXT DEFAULT '',
    signals JSONB DEFAULT '{}',
    confidence DOUBLE PRECISION DEFAULT 0,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reasoning_symbol ON reasoning_logs(symbol);
CREATE INDEX IF NOT EXISTS idx_reasoning_timestamp ON reasoning_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_reasoning_action ON reasoning_logs(action);

-- ============================================================
-- 4. Daily Reports
-- Aggregated daily performance metrics.
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_reports (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    total_pnl DOUBLE PRECISION DEFAULT 0,
    max_drawdown DOUBLE PRECISION DEFAULT 0,
    win_rate DOUBLE PRECISION DEFAULT 0,
    sharpe_ratio DOUBLE PRECISION,
    summary TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports(date DESC);

-- ============================================================
-- 5. Row Level Security (RLS)
-- Supabase RLS to restrict access to authenticated users.
-- ============================================================

-- Enable RLS on all tables
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE reasoning_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_reports ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (for the agent)
-- The agent uses the service role key, which bypasses RLS.
-- For the anon key, these policies apply:

-- Read-only access for authenticated users
CREATE POLICY "Allow read access for authenticated users"
    ON trades FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Allow read access for authenticated users"
    ON orders FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Allow read access for authenticated users"
    ON reasoning_logs FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Allow read access for authenticated users"
    ON daily_reports FOR SELECT
    TO authenticated
    USING (true);

-- Insert access for service role only (agent writes)
CREATE POLICY "Allow insert for service role"
    ON trades FOR INSERT
    TO service_role
    WITH CHECK (true);

CREATE POLICY "Allow insert for service role"
    ON orders FOR INSERT
    TO service_role
    WITH CHECK (true);

CREATE POLICY "Allow insert for service role"
    ON reasoning_logs FOR INSERT
    TO service_role
    WITH CHECK (true);

CREATE POLICY "Allow insert for service role"
    ON daily_reports FOR INSERT
    TO service_role
    WITH CHECK (true);

-- ============================================================
-- 6. Views for dashboards
-- ============================================================

-- Recent performance summary
CREATE OR REPLACE VIEW v_performance_summary AS
SELECT
    COUNT(*) AS total_trades,
    COUNT(*) FILTER (WHERE pnl >= 0) AS winning_trades,
    COUNT(*) FILTER (WHERE pnl < 0) AS losing_trades,
    ROUND(CAST(COUNT(*) FILTER (WHERE pnl >= 0) AS NUMERIC) /
          NULLIF(COUNT(*), 0) * 100, 2) AS win_rate,
    ROUND(SUM(pnl)::NUMERIC, 2) AS total_pnl,
    ROUND(AVG(pnl)::NUMERIC, 2) AS avg_pnl,
    ROUND(AVG(CASE WHEN pnl >= 0 THEN pnl END)::NUMERIC, 2) AS avg_win,
    ROUND(AVG(CASE WHEN pnl < 0 THEN pnl END)::NUMERIC, 2) AS avg_loss,
    MIN(exit_time) AS first_trade,
    MAX(exit_time) AS last_trade
FROM trades;

-- Daily PnL breakdown
CREATE OR REPLACE VIEW v_daily_pnl AS
SELECT
    DATE(exit_time) AS trade_date,
    COUNT(*) AS trades,
    ROUND(SUM(pnl)::NUMERIC, 2) AS daily_pnl,
    ROUND(AVG(pnl)::NUMERIC, 2) AS avg_pnl,
    COUNT(*) FILTER (WHERE pnl >= 0) AS wins,
    COUNT(*) FILTER (WHERE pnl < 0) AS losses
FROM trades
GROUP BY DATE(exit_time)
ORDER BY trade_date DESC;

-- Per-symbol performance
CREATE OR REPLACE VIEW v_symbol_performance AS
SELECT
    symbol,
    COUNT(*) AS trades,
    ROUND(SUM(pnl)::NUMERIC, 2) AS total_pnl,
    ROUND(AVG(pnl_pct)::NUMERIC, 2) AS avg_pnl_pct,
    ROUND(CAST(COUNT(*) FILTER (WHERE pnl >= 0) AS NUMERIC) /
          NULLIF(COUNT(*), 0) * 100, 2) AS win_rate
FROM trades
GROUP BY symbol
ORDER BY total_pnl DESC;
