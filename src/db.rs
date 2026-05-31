use rusqlite::{params, Connection, Result};
use std::path::Path;
use chrono::Utc;
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Wallet {
    pub wallet_address: String,
    pub name: String,
    pub telegram: Option<String>,
    pub twitter: Option<String>,
    pub profit: f64,
    pub wins: i64,
    pub losses: i64,
    pub timeframe: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Transaction {
    pub signature: String,
    pub wallet_address: String,
    pub wallet_name: String,
    pub token_address: String,
    pub action: String,
    pub amount_sol: f64,
    pub amount_tokens: f64,
    pub platform: String,
    pub timestamp: String,
}

pub fn init_db<P: AsRef<Path>>(path: P) -> Result<()> {
    let conn = Connection::open(path)?;
    
    // Create wallets table
    conn.execute(
        "CREATE TABLE IF NOT EXISTS wallets (
            wallet_address TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            telegram TEXT,
            twitter TEXT,
            profit REAL NOT NULL,
            wins INTEGER NOT NULL,
            losses INTEGER NOT NULL,
            timeframe INTEGER NOT NULL,
            last_scraped_at TEXT NOT NULL
        )",
        [],
    )?;

    // Create transactions table
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tracked_transactions (
            signature TEXT PRIMARY KEY,
            wallet_address TEXT NOT NULL,
            wallet_name TEXT NOT NULL,
            token_address TEXT NOT NULL,
            action TEXT NOT NULL,
            amount_sol REAL NOT NULL,
            amount_tokens REAL NOT NULL,
            platform TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(wallet_address) REFERENCES wallets(wallet_address)
        )",
        [],
    )?;

    Ok(())
}

pub fn save_wallets<P: AsRef<Path>>(path: P, wallets: &[Wallet]) -> Result<()> {
    let mut conn = Connection::open(path)?;
    let tx = conn.transaction()?;

    let now = Utc::now().to_rfc3339();

    for wallet in wallets {
        tx.execute(
            "INSERT INTO wallets (
                wallet_address, name, telegram, twitter, profit, wins, losses, timeframe, last_scraped_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)
            ON CONFLICT(wallet_address) DO UPDATE SET
                name = excluded.name,
                telegram = excluded.telegram,
                twitter = excluded.twitter,
                profit = excluded.profit,
                wins = excluded.wins,
                losses = excluded.losses,
                timeframe = excluded.timeframe,
                last_scraped_at = excluded.last_scraped_at",
            params![
                wallet.wallet_address,
                wallet.name,
                wallet.telegram,
                wallet.twitter,
                wallet.profit,
                wallet.wins,
                wallet.losses,
                wallet.timeframe,
                now
            ],
        )?;
    }

    tx.commit()?;
    Ok(())
}

pub fn get_active_wallets<P: AsRef<Path>>(path: P) -> Result<Vec<Wallet>> {
    let conn = Connection::open(path)?;
    let mut stmt = conn.prepare(
        "SELECT wallet_address, name, telegram, twitter, profit, wins, losses, timeframe FROM wallets"
    )?;
    
    let wallet_iter = stmt.query_map([], |row| {
        Ok(Wallet {
            wallet_address: row.get(0)?,
            name: row.get(1)?,
            telegram: row.get(2)?,
            twitter: row.get(3)?,
            profit: row.get(4)?,
            wins: row.get(5)?,
            losses: row.get(6)?,
            timeframe: row.get(7)?,
        })
    })?;

    let mut wallets = Vec::new();
    for wallet in wallet_iter {
        wallets.push(wallet?);
    }
    
    Ok(wallets)
}

pub fn log_transaction<P: AsRef<Path>>(
    path: P,
    signature: &str,
    wallet_address: &str,
    wallet_name: &str,
    token_address: &str,
    action: &str,
    amount_sol: f64,
    amount_tokens: f64,
    platform: &str,
) -> Result<()> {
    let conn = Connection::open(path)?;
    let now = Utc::now().to_rfc3339();
    
    conn.execute(
        "INSERT OR IGNORE INTO tracked_transactions (
            signature, wallet_address, wallet_name, token_address, action, amount_sol, amount_tokens, platform, timestamp
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
        params![
            signature,
            wallet_address,
            wallet_name,
            token_address,
            action,
            amount_sol,
            amount_tokens,
            platform,
            now
        ],
    )?;

    Ok(())
}

pub fn get_recent_transactions<P: AsRef<Path>>(path: P, limit: usize) -> Result<Vec<Transaction>> {
    let conn = Connection::open(path)?;
    let mut stmt = conn.prepare(
        "SELECT signature, wallet_address, wallet_name, token_address, action, amount_sol, amount_tokens, platform, timestamp 
         FROM tracked_transactions 
         ORDER BY timestamp DESC 
         LIMIT ?1"
    )?;
    
    let transaction_iter = stmt.query_map([limit], |row| {
        Ok(Transaction {
            signature: row.get(0)?,
            wallet_address: row.get(1)?,
            wallet_name: row.get(2)?,
            token_address: row.get(3)?,
            action: row.get(4)?,
            amount_sol: row.get(5)?,
            amount_tokens: row.get(6)?,
            platform: row.get(7)?,
            timestamp: row.get(8)?,
        })
    })?;

    let mut transactions = Vec::new();
    for transaction in transaction_iter {
        transactions.push(transaction?);
    }
    
    Ok(transactions)
}
