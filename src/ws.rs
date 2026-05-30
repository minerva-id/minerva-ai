use std::collections::{HashMap, HashSet};
use futures_util::{SinkExt, StreamExt};
use serde_json::Value;
use tokio::time::{sleep, Duration};
use crate::db::Wallet;

const DEFAULT_HELIUS_API_KEY: &str = "4d523832-c5ea-4733-bab4-071ac2f43329";

struct TradeDetails {
    action: String,
    token_address: String,
    amount_sol: f64,
    amount_tokens: f64,
    platform: String,
}

pub async fn run_ws_listener(
    mut rx_wallets: tokio::sync::mpsc::Receiver<Vec<Wallet>>,
    db_path: String,
) {
    let mut current_task: Option<tokio::task::JoinHandle<()>> = None;
    
    while let Some(wallets) = rx_wallets.recv().await {
        println!("[WS Master] Received new list of {} wallets. Restarting listener...", wallets.len());
        
        // Abort the existing listener task if it is running
        if let Some(task) = current_task.take() {
            task.abort();
            let _ = task.await; // Wait for it to clean up
        }
        
        // Spawn the new listener task
        let db_path_clone = db_path.clone();
        let handle = tokio::spawn(async move {
            if let Err(e) = ws_connection_loop(wallets, db_path_clone).await {
                eprintln!("[WS Listener] Connection loop exited with error: {:?}", e);
            }
        });
        current_task = Some(handle);
    }
}

async fn ws_connection_loop(
    wallets: Vec<Wallet>,
    db_path: String,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let api_key = std::env::var("HELIUS_API_KEY")
        .unwrap_or_else(|_| DEFAULT_HELIUS_API_KEY.to_string());
        
    let ws_url = format!("wss://mainnet.helius-rpc.com/?api-key={}", api_key);
    let rpc_url = format!("https://mainnet.helius-rpc.com/?api-key={}", api_key);
    
    loop {
        println!("[WS Listener] Connecting to {}...", ws_url);
        
        let ws_stream = match tokio_tungstenite::connect_async(&ws_url).await {
            Ok((stream, _)) => stream,
            Err(e) => {
                eprintln!("[WS Listener] Connection error: {:?}. Retrying in 5 seconds...", e);
                sleep(Duration::from_secs(5)).await;
                continue;
            }
        };
        
        println!("[WS Listener] Connected! Sending subscriptions...");
        
        let (mut write, mut read) = ws_stream.split();
        
        let mut sub_id_map = HashMap::new();
        let mut req_id_map = HashMap::new();
        
        for (index, wallet) in wallets.iter().enumerate() {
            let req_id = (index + 1) as u64;
            req_id_map.insert(req_id, wallet.clone());
            
            let req = serde_json::json!({
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "logsSubscribe",
                "params": [
                    {
                        "mentions": [ wallet.wallet_address ]
                    },
                    {
                        "commitment": "processed"
                    }
                ]
            });
            
            let msg = tokio_tungstenite::tungstenite::Message::Text(req.to_string());
            if let Err(e) = write.send(msg).await {
                eprintln!("[WS Listener] Failed to send subscription: {:?}", e);
                break;
            }
        }
        
        println!("[WS Listener] All subscriptions sent. Listening for messages...");
        
        while let Some(msg_result) = read.next().await {
            let msg = match msg_result {
                Ok(m) => m,
                Err(e) => {
                    eprintln!("[WS Listener] Stream read error: {:?}. Reconnecting...", e);
                    break;
                }
            };
            
            if msg.is_text() {
                let text = msg.to_text().unwrap_or("");
                if let Ok(val) = serde_json::from_str::<Value>(text) {
                    // Check if it's a subscription response mapping
                    if let Some(req_id) = val.get("id").and_then(|id| id.as_u64()) {
                        if let Some(sub_id) = val.get("result").and_then(|r| r.as_u64()) {
                            if let Some(wallet) = req_id_map.get(&req_id) {
                                sub_id_map.insert(sub_id, wallet.clone());
                                println!("[WS Listener] Subscribed to {} ({}) -> sub_id={}", wallet.name, wallet.wallet_address, sub_id);
                            }
                        }
                    } else if let Some(method) = val.get("method").and_then(|m| m.as_str()) {
                        // Check if it's a notification
                        if method == "logsNotification" {
                            if let Some(params) = val.get("params") {
                                if let Some(sub_id) = params.get("subscription").and_then(|s| s.as_u64()) {
                                    if let Some(wallet) = sub_id_map.get(&sub_id) {
                                        if let Some(result) = params.get("result") {
                                            if let Some(value) = result.get("value") {
                                                let signature = value.get("signature").and_then(|s| s.as_str()).unwrap_or("");
                                                let err = value.get("err");
                                                
                                                if !signature.is_empty() && (err.is_none() || err.unwrap().is_null()) {
                                                    println!("[WS Listener] Notification received for {} ({}). Tx: {}", wallet.name, wallet.wallet_address, signature);
                                                    
                                                    // Spawn task to fetch transaction details and send telegram alerts
                                                    let wallet_clone = wallet.clone();
                                                    let sig = signature.to_string();
                                                    let db_path_clone = db_path.clone();
                                                    let rpc_url_clone = rpc_url.clone();
                                                    tokio::spawn(async move {
                                                        if let Err(e) = process_and_alert_tx(&sig, &wallet_clone, &db_path_clone, &rpc_url_clone).await {
                                                            eprintln!("[WS Processor] Error processing transaction {}: {:?}", sig, e);
                                                        }
                                                    });
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            } else if msg.is_ping() {
                let _ = write.send(tokio_tungstenite::tungstenite::Message::Pong(vec![])).await;
            } else if msg.is_close() {
                println!("[WS Listener] Connection closed by server. Reconnecting...");
                break;
            }
        }
        
        println!("[WS Listener] Connection lost. Reconnecting in 5 seconds...");
        sleep(Duration::from_secs(5)).await;
    }
}

async fn process_and_alert_tx(
    signature: &str,
    wallet: &Wallet,
    db_path: &str,
    rpc_url: &str,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    // Fetch transaction details with retries
    let tx_data = fetch_transaction_with_retry(signature, rpc_url).await?;
    
    // Parse the swap
    let trades = parse_trades(&tx_data, &wallet.wallet_address)
        .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.to_string().into() })?;
    
    if trades.is_empty() {
        println!("[WS Processor] No token swap detected in transaction {} for wallet {}", signature, wallet.wallet_address);
        return Ok(());
    }
    
    for trade in trades {
        println!("[WS Processor] Trade detected! {} {} of token {} for {} SOL", wallet.name, trade.action, trade.token_address, trade.amount_sol);
        
        // Log to database
        let db_path_clone = db_path.to_string();
        let sig = signature.to_string();
        let w_addr = wallet.wallet_address.clone();
        let w_name = wallet.name.clone();
        let t_addr = trade.token_address.clone();
        let act = trade.action.clone();
        let amt_sol = trade.amount_sol;
        let amt_tokens = trade.amount_tokens;
        let plat = trade.platform.clone();
        
        tokio::task::spawn_blocking(move || {
            if let Err(e) = crate::db::log_transaction(
                &db_path_clone,
                &sig,
                &w_addr,
                &w_name,
                &t_addr,
                &act,
                amt_sol,
                amt_tokens,
                &plat
            ) {
                eprintln!("[WS DB Log] Error saving transaction to DB: {:?}", e);
            }
        }).await
        .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.to_string().into() })?;
        
        // Send Telegram notification via debounce queue
        let alert = crate::telegram::SwapAlert {
            signature: signature.to_string(),
            wallet_address: wallet.wallet_address.clone(),
            wallet_name: wallet.name.clone(),
            action: trade.action.clone(),
            token_address: trade.token_address.clone(),
            amount_sol: trade.amount_sol,
            amount_tokens: trade.amount_tokens,
            platform: trade.platform.clone(),
        };
        
        crate::telegram::queue_telegram_notification(alert).await;
    }
    
    Ok(())
}

async fn fetch_transaction_with_retry(
    signature: &str,
    rpc_url: &str,
) -> Result<Value, Box<dyn std::error::Error + Send + Sync>> {
    let client = reqwest::Client::new();
    let payload = serde_json::json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {
                "encoding": "json",
                "maxSupportedTransactionVersion": 0
            }
        ]
    });
    
    for attempt in 1..=10 {
        let response = client.post(rpc_url)
            .json(&payload)
            .send()
            .await
            .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.into() })?;
            
        if response.status().is_success() {
            let res_json: Value = response.json().await
                .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.into() })?;
            if let Some(result) = res_json.get("result") {
                if !result.is_null() {
                    return Ok(result.clone());
                }
            }
        }
        
        println!("[WS Processor] Transaction details not indexed yet for signature {} (attempt {}/10). Retrying in 1s...", signature, attempt);
        sleep(Duration::from_secs(1)).await;
    }
    
    Err(format!("Failed to retrieve transaction details for signature after 10 attempts: {}", signature).into())
}

fn parse_trades(
    tx_result: &Value,
    wallet_address: &str,
) -> Result<Vec<TradeDetails>, Box<dyn std::error::Error>> {
    let account_keys_val = tx_result.pointer("/transaction/message/accountKeys")
        .ok_or("Missing accountKeys")?;
    let account_keys: Vec<String> = serde_json::from_value(account_keys_val.clone())?;
    
    let wallet_index = account_keys.iter().position(|k| k == wallet_address)
        .ok_or_else(|| format!("Wallet address {} not found in accountKeys", wallet_address))?;
        
    let pre_balances_val = tx_result.pointer("/meta/preBalances")
        .ok_or("Missing preBalances")?;
    let pre_balances: Vec<u64> = serde_json::from_value(pre_balances_val.clone())?;
    
    let post_balances_val = tx_result.pointer("/meta/postBalances")
        .ok_or("Missing postBalances")?;
    let post_balances: Vec<u64> = serde_json::from_value(post_balances_val.clone())?;
    
    if wallet_index >= pre_balances.len() || wallet_index >= post_balances.len() {
        return Err("Wallet index out of bounds of balances arrays".into());
    }
    
    let pre_sol = pre_balances[wallet_index] as f64 / 1_000_000_000.0;
    let post_sol = post_balances[wallet_index] as f64 / 1_000_000_000.0;
    let sol_change = post_sol - pre_sol;
    
    let pre_tbl_val = tx_result.pointer("/meta/preTokenBalances");
    let post_tbl_val = tx_result.pointer("/meta/postTokenBalances");
    
    let pre_tbl: Vec<Value> = if let Some(v) = pre_tbl_val {
        serde_json::from_value(v.clone()).unwrap_or_default()
    } else {
        Vec::new()
    };
    
    let post_tbl: Vec<Value> = if let Some(v) = post_tbl_val {
        serde_json::from_value(v.clone()).unwrap_or_default()
    } else {
        Vec::new()
    };
    
    let mut pre_map = HashMap::new();
    for tb in &pre_tbl {
        let owner = tb.get("owner").and_then(|o| o.as_str());
        let account_index = tb.get("accountIndex").and_then(|ai| ai.as_u64()).unwrap_or(9999) as usize;
        
        let is_owner = if let Some(o) = owner {
            o == wallet_address
        } else {
            account_index < account_keys.len() && account_keys[account_index] == wallet_address
        };
        
        if is_owner {
            if let Some(mint) = tb.get("mint").and_then(|m| m.as_str()) {
                if let Some(amount) = tb.pointer("/uiTokenAmount/uiAmount").and_then(|a| a.as_f64()) {
                    pre_map.insert(mint.to_string(), amount);
                }
            }
        }
    }
    
    let mut post_map = HashMap::new();
    for tb in &post_tbl {
        let owner = tb.get("owner").and_then(|o| o.as_str());
        let account_index = tb.get("accountIndex").and_then(|ai| ai.as_u64()).unwrap_or(9999) as usize;
        
        let is_owner = if let Some(o) = owner {
            o == wallet_address
        } else {
            account_index < account_keys.len() && account_keys[account_index] == wallet_address
        };
        
        if is_owner {
            if let Some(mint) = tb.get("mint").and_then(|m| m.as_str()) {
                if let Some(amount) = tb.pointer("/uiTokenAmount/uiAmount").and_then(|a| a.as_f64()) {
                    post_map.insert(mint.to_string(), amount);
                }
            }
        }
    }
    
    let is_pump_fun = account_keys.iter().any(|k| k == "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
        || if let Some(logs_val) = tx_result.pointer("/meta/logMessages") {
            let logs: Vec<String> = serde_json::from_value(logs_val.clone()).unwrap_or_default();
            logs.iter().any(|l| l.contains("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"))
        } else {
            false
        };
        
    let platform = if is_pump_fun { "Pump.fun" } else { "Solana Swap" };
    
    let mut mints = HashSet::new();
    for k in pre_map.keys() {
        mints.insert(k.clone());
    }
    for k in post_map.keys() {
        mints.insert(k.clone());
    }
    
    let mut trades = Vec::new();
    for mint in mints {
        let pre_val = pre_map.get(&mint).copied().unwrap_or(0.0);
        let post_val = post_map.get(&mint).copied().unwrap_or(0.0);
        let token_change = post_val - pre_val;
        
        if mint == "So11111111111111111111111111111111111111112" {
            continue;
        }
        
        if token_change.abs() > 0.000001 {
            let action = if token_change > 0.0 { "BUY" } else { "SELL" };
            trades.push(TradeDetails {
                action: action.to_string(),
                token_address: mint,
                amount_sol: sol_change.abs(),
                amount_tokens: token_change.abs(),
                platform: platform.to_string(),
            });
        }
    }
    
    Ok(trades)
}
