mod db;
mod scraper;
mod ws;
mod telegram;
mod api;

use tokio::sync::mpsc;
use tokio::time::{interval, Duration};

fn load_env() {
    if let Ok(file) = std::fs::File::open(".env") {
        let reader = std::io::BufReader::new(file);
        use std::io::BufRead;
        for line in reader.lines() {
            if let Ok(line) = line {
                let trimmed = line.trim();
                if trimmed.is_empty() || trimmed.starts_with('#') {
                    continue;
                }
                if let Some((key, val)) = trimmed.split_once('=') {
                    let val_clean = val.trim().trim_matches('"').trim_matches('\'');
                    unsafe {
                        std::env::set_var(key.trim(), val_clean);
                    }
                }
            }
        }
        println!("[Env] Loaded environment configuration from .env file");
    } else {
        println!("[Env] No .env file found, using system environment variables or defaults");
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("==============================================");
    println!("    MINERVA SOLANA WALLET TRACKER INITIALIZING");
    println!("==============================================");

    // Load environment variables from .env if present
    load_env();

    let db_path = std::env::var("WALLETS_DB_PATH").unwrap_or_else(|_| "wallets.db".to_string());

    // 1. Initialize DB
    let db_path_clone = db_path.clone();
    tokio::task::spawn_blocking(move || {
        if let Err(e) = db::init_db(&db_path_clone) {
            eprintln!("[DB Error] Failed to initialize SQLite database: {:?}", e);
            std::process::exit(1);
        }
        println!("[DB] SQLite database initialized successfully at {}", db_path_clone);
    }).await?;

    // 2. Start HTTP API Server
    let api_db_path = db_path.clone();
    let api_handle = tokio::spawn(async move {
        let app = api::create_router(api_db_path);
        let port = std::env::var("PORT")
            .unwrap_or_else(|_| "3000".to_string())
            .parse::<u16>()
            .unwrap_or(3000);
        
        let addr = format!("0.0.0.0:{}", port);
        println!("[API] Starting HTTP server on {}", addr);
        
        let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
        axum::serve(listener, app).await.unwrap();
    });

    // 3. Set up channels
    // We send a Vec<Wallet> whenever the KOL wallet list is updated
    let (tx_wallets, rx_wallets) = mpsc::channel(10);

    // 4. Spawn WebSocket Listener Task Coordinator
    let db_path_clone = db_path.clone();
    let ws_coordinator_handle = tokio::spawn(async move {
        ws::run_ws_listener(rx_wallets, db_path_clone).await;
    });

    // 5. Start the Scraper Loop Task
    let scraper_handle = tokio::spawn(async move {
        // Run scraper every 12 hours
        let mut scrape_interval = interval(Duration::from_secs(12 * 3600));
        
        loop {
            scrape_interval.tick().await;
            println!("[Main Loop] Running scheduled scraper...");
            
            match scraper::scrape_and_update_db(
                db_path.clone(),
            ).await {
                Ok(wallets) => {
                    println!("[Main Loop] Scrape successful! {} wallets fetched and saved.", wallets.len());
                    // Send to WS coordinator to refresh subscriptions
                    if let Err(e) = tx_wallets.send(wallets).await {
                        eprintln!("[Main Loop] Failed to send updated wallets to WS coordinator: {:?}", e);
                    }
                }
                Err(e) => {
                    eprintln!("[Main Loop] Scraper error: {:?}", e);
                    // Fallback: load existing active wallets from database to keep tracking
                    println!("[Main Loop] Loading existing active wallets from database as fallback...");
                    let db_path_clone = db_path.clone();
                    let fallback_wallets_res = tokio::task::spawn_blocking(move || {
                        db::get_active_wallets(db_path_clone)
                    }).await;
                    
                    match fallback_wallets_res {
                        Ok(Ok(wallets)) => {
                            if !wallets.is_empty() {
                                println!("[Main Loop] Found {} wallets in database. Refreshing connections...", wallets.len());
                                if let Err(send_err) = tx_wallets.send(wallets).await {
                                    eprintln!("[Main Loop] Failed to send fallback wallets to WS coordinator: {:?}", send_err);
                                }
                            } else {
                                eprintln!("[Main Loop] No wallets found in database. WebSocket tracking cannot start until a scrape succeeds.");
                            }
                        }
                        _ => {
                            eprintln!("[Main Loop] Failed to query fallback wallets from DB.");
                        }
                    }
                }
            }
        }
    });

    // Keep running
    tokio::select! {
        res = api_handle => {
            println!("[Fatal] API Server task exited: {:?}", res);
        }
        res = ws_coordinator_handle => {
            println!("[Fatal] WS Coordinator task exited: {:?}", res);
        }
        res = scraper_handle => {
            println!("[Fatal] Scraper task exited: {:?}", res);
        }
    }

    Ok(())
}
