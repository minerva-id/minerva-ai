-- ============================================================
-- Minerva AI — Backtest Results Table Migration
-- Run this in the Supabase SQL Editor.
-- ============================================================

-- ============================================================
-- 1. Backtest Results
-- Records backtest simulations for strategy analysis.
-- ============================================================
CREATE TABLE IF NOT EXISTS backtest_results (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    candles INTEGER DEFAULT 0,
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    win_rate DOUBLE PRECISION DEFAULT 0,
    total_pnl DOUBLE PRECISION DEFAULT 0,
    pnl_pct DOUBLE PRECISION DEFAULT 0,
    total_fees DOUBLE PRECISION DEFAULT 0,
    final_balance DOUBLE PRECISION DEFAULT 0,
    avg_win DOUBLE PRECISION DEFAULT 0,
    avg_loss DOUBLE PRECISION DEFAULT 0,
    run_timestamp TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_symbol ON backtest_results(symbol);
CREATE INDEX IF NOT EXISTS idx_backtest_run_timestamp ON backtest_results(run_timestamp DESC);

-- ============================================================
-- 2. Row Level Security
-- ============================================================
ALTER TABLE backtest_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow read access for authenticated users"
    ON backtest_results FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Allow insert for service role"
    ON backtest_results FOR INSERT
    TO service_role
    WITH CHECK (true);
