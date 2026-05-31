use serde::Serialize;
use std::collections::HashMap;
use std::sync::LazyLock;
use std::sync::Mutex;
use std::time::{Duration, Instant};

const DEFAULT_BOT_TOKEN: &str = "8812686337:AAHOdk6HyBXPoa4_9c1TAhxLYtCcIw_Ro3Q";
const DEFAULT_CHAT_ID: &str = "-1003987224700";

#[derive(Serialize)]
struct TelegramPayload {
    chat_id: String,
    text: String,
    parse_mode: String,
    disable_web_page_preview: bool,
}

#[derive(Debug, Clone)]
pub struct SwapAlert {
    pub signature: String,
    pub wallet_address: String,
    pub wallet_name: String,
    pub action: String,
    pub token_address: String,
    pub amount_sol: f64,
    pub amount_tokens: f64,
    pub platform: String,
}

struct PendingAlert {
    wallet_address: String,
    wallet_name: String,
    action: String,
    token_address: String,
    amount_sol: f64,
    amount_tokens: f64,
    platform: String,
    signatures: Vec<String>,
    first_seen: Instant,
    last_seen: Instant,
}

static PENDING_ALERTS: LazyLock<Mutex<HashMap<String, PendingAlert>>> = LazyLock::new(|| {
    Mutex::new(HashMap::new())
});

#[derive(serde::Deserialize, Debug, Clone)]
struct DexTokenResponse {
    pairs: Option<Vec<DexPair>>,
}

#[derive(serde::Deserialize, Debug, Clone)]
struct DexPair {
    #[serde(rename = "pairCreatedAt")]
    pair_created_at: Option<i64>,
    #[serde(rename = "baseToken")]
    base_token: Option<DexBaseToken>,
    #[serde(rename = "priceUsd")]
    price_usd: Option<String>,
    #[serde(rename = "marketCap")]
    market_cap: Option<f64>,
}

#[derive(serde::Deserialize, Debug, Clone)]
struct DexBaseToken {
    name: Option<String>,
    symbol: Option<String>,
}

pub struct TokenMetadata {
    pub name: String,
    pub symbol: String,
    pub price_usd: f64,
    pub age_days: f64,
    pub market_cap: f64,
}

#[derive(serde::Deserialize, Debug, Clone)]
struct RugCheckReport {
    #[serde(rename = "totalHolders")]
    total_holders: Option<i64>,
    #[serde(rename = "topHolders")]
    top_holders: Option<Vec<RugHolder>>,
}

#[derive(serde::Deserialize, Debug, Clone)]
struct RugHolder {
    pct: Option<f64>,
}

pub struct HolderStats {
    pub total_holders: i64,
    pub whales: i64,
    pub dolphins: i64,
    pub shrimps: i64,
}

pub async fn fetch_token_metadata(token_address: &str) -> Option<TokenMetadata> {
    let url = format!("https://api.dexscreener.com/latest/dex/tokens/{}", token_address);
    let client = reqwest::Client::new();
    let response = client.get(&url).send().await.ok()?;
    if !response.status().is_success() {
        return None;
    }
    let data: DexTokenResponse = response.json().await.ok()?;
    let pairs = data.pairs?;
    if pairs.is_empty() {
        return None;
    }

    // Find the oldest pair based on pairCreatedAt to get the true age
    let mut oldest_pair = &pairs[0];
    for pair in &pairs {
        if let (Some(t1), Some(t2)) = (pair.pair_created_at, oldest_pair.pair_created_at) {
            if t1 < t2 {
                oldest_pair = pair;
            }
        }
    }

    let pair_created_at = oldest_pair.pair_created_at.unwrap_or(0);
    let current_time_ms = std::time::SystemTime::now()
        .duration_since(std::time::SystemTime::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64;
    let age_ms = current_time_ms - pair_created_at;
    let age_days = age_ms as f64 / (1000.0 * 60.0 * 60.0 * 24.0);

    let base_token = oldest_pair.base_token.as_ref()?;
    let name = base_token.name.clone().unwrap_or_default();
    let symbol = base_token.symbol.clone().unwrap_or_default();
    let price_usd = oldest_pair.price_usd.as_ref()
        .and_then(|p| p.parse::<f64>().ok())
        .unwrap_or(0.0);
    let market_cap = oldest_pair.market_cap.unwrap_or(0.0);

    Some(TokenMetadata {
        name,
        symbol,
        price_usd,
        age_days,
        market_cap,
    })
}

pub async fn fetch_holder_stats(token_address: &str) -> Option<HolderStats> {
    let url = format!("https://api.rugcheck.xyz/v1/tokens/{}/report", token_address);
    let client = reqwest::Client::new();
    let response = client.get(&url).send().await.ok()?;
    if !response.status().is_success() {
        return None;
    }
    let report: RugCheckReport = response.json().await.ok()?;
    let total_holders = report.total_holders.unwrap_or(0);
    let top_holders = report.top_holders.unwrap_or_default();

    let mut whales = 0;
    let mut dolphins = 0;

    for holder in &top_holders {
        if let Some(pct) = holder.pct {
            if pct >= 1.0 {
                whales += 1;
            } else if pct >= 0.1 {
                dolphins += 1;
            }
        }
    }

    let mut shrimps = total_holders - whales - dolphins;
    if shrimps < 0 {
        shrimps = 0;
    }

    Some(HolderStats {
        total_holders,
        whales,
        dolphins,
        shrimps,
    })
}

pub async fn queue_telegram_notification(alert: SwapAlert) {
    let key = format!("{}:{}:{}", alert.wallet_address, alert.token_address, alert.action.to_uppercase());
    
    let mut map = PENDING_ALERTS.lock().unwrap();
    if let Some(pending) = map.get_mut(&key) {
        pending.amount_sol += alert.amount_sol;
        pending.amount_tokens += alert.amount_tokens;
        pending.last_seen = Instant::now();
        if !pending.signatures.contains(&alert.signature) {
            pending.signatures.push(alert.signature.clone());
        }
        println!("[Telegram Queue] Aggregated trade for {}, total SOL: {:.4}", alert.wallet_name, pending.amount_sol);
    } else {
        let pending = PendingAlert {
            wallet_address: alert.wallet_address.clone(),
            wallet_name: alert.wallet_name.clone(),
            action: alert.action.clone(),
            token_address: alert.token_address.clone(),
            amount_sol: alert.amount_sol,
            amount_tokens: alert.amount_tokens,
            platform: alert.platform.clone(),
            signatures: vec![alert.signature.clone()],
            first_seen: Instant::now(),
            last_seen: Instant::now(),
        };
        map.insert(key.clone(), pending);
        println!("[Telegram Queue] Created new pending trade for {}, SOL: {:.4}", alert.wallet_name, alert.amount_sol);
        
        tokio::spawn(async move {
            let debounce_duration = Duration::from_secs(30);
            loop {
                tokio::time::sleep(debounce_duration).await;
                
                let mut should_flush = false;
                let mut final_alert = None;
                
                {
                    let mut map = PENDING_ALERTS.lock().unwrap();
                    if let Some(pending) = map.get(&key) {
                        let elapsed_since_last = pending.last_seen.elapsed();
                        let elapsed_since_first = pending.first_seen.elapsed();
                        
                        // Flush if quiet period of 30s has passed, or if max wait of 60s is reached
                        if elapsed_since_last >= debounce_duration || elapsed_since_first >= Duration::from_secs(60) {
                            final_alert = map.remove(&key);
                            should_flush = true;
                        }
                    } else {
                        break;
                    }
                }
                
                if should_flush {
                    if let Some(alert) = final_alert {
                        if let Err(e) = flush_telegram_notification(alert).await {
                            eprintln!("[Telegram Queue] Error flushing notification: {:?}", e);
                        }
                    }
                    break;
                }
            }
        });
    }
}

async fn flush_telegram_notification(pending: PendingAlert) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    // 1. Fetch metadata from DexScreener
    let metadata = fetch_token_metadata(&pending.token_address).await;
    
    // 2. Filter by age if metadata is found
    if let Some(ref meta) = metadata {
        if meta.age_days < 7.0 {
            println!(
                "[Telegram Queue] Filtering out token {} (age: {:.2} days < 7 days limit)",
                pending.token_address, meta.age_days
            );
            return Ok(());
        }
    } else {
        // If metadata is not found on DexScreener, it's either not listed or extremely new.
        // We filter it out as a high-risk honeypot!
        println!(
            "[Telegram Queue] Filtering out token {} (no pair found on DexScreener, likely new/honeypot)",
            pending.token_address
        );
        return Ok(());
    }
    
    let meta = metadata.unwrap();
    let usd_value = pending.amount_tokens * meta.price_usd;
    
    // Filter by transaction USD value (must be >= $500.0 threshold or custom MIN_USD_THRESHOLD env)
    let usd_threshold = std::env::var("MIN_USD_THRESHOLD")
        .ok()
        .and_then(|val| val.parse::<f64>().ok())
        .unwrap_or(500.0);
        
    if usd_value < usd_threshold {
        println!(
            "[Telegram Queue] Filtering out swap for wallet {} (USD value: ${:.2} < ${:.2} threshold)",
            pending.wallet_name, usd_value, usd_threshold
        );
        return Ok(());
    }
    
    // 3. Fetch holder stats from RugCheck (graceful fallback if it fails)
    let holder_stats = fetch_holder_stats(&pending.token_address).await;
    
    let bot_token = std::env::var("TELEGRAM_BOT_TOKEN")
        .or_else(|_| std::env::var("TELEGRAM_BOT_TOKEN2"))
        .unwrap_or_else(|_| DEFAULT_BOT_TOKEN.to_string());
        
    let chat_id = std::env::var("TELEGRAM_CHAT_ID")
        .or_else(|_| std::env::var("TELEGRAM_CHAT_ID2"))
        .unwrap_or_else(|_| DEFAULT_CHAT_ID.to_string());
        
    let client = reqwest::Client::new();
    let url = format!("https://api.telegram.org/bot{}/sendMessage", bot_token);
    
    let escaped_name = escape_html(&pending.wallet_name);
    let action_emoji = match pending.action.to_uppercase().as_str() {
        "BUY" => "🟢 BUY",
        "SELL" => "🔴 SELL",
        _ => &pending.action,
    };
    
    let title = if pending.signatures.len() > 1 {
        format!("🎯 <b>SOL SWAP DETECTED ({} Combined Tx)</b> 🎯", pending.signatures.len())
    } else {
        "🎯 <b>SOL SWAP DETECTED</b> 🎯".to_string()
    };
    
    let mut tx_links = String::new();
    if pending.signatures.len() == 1 {
        tx_links = format!("🔗 <a href=\"https://solscan.io/tx/{}\">View Transaction on Solscan</a>", pending.signatures[0]);
    } else {
        tx_links.push_str("🔗 <b>Transactions:</b>\n");
        for (i, sig) in pending.signatures.iter().enumerate() {
            tx_links.push_str(&format!("   {}. <a href=\"https://solscan.io/tx/{}\">Tx {}</a>\n", i + 1, sig, &sig[0..8]));
        }
    }

    // Format Market Cap beautifully
    let mc_formatted = if meta.market_cap >= 1_000_000.0 {
        format!("${:.2}M", meta.market_cap / 1_000_000.0)
    } else if meta.market_cap >= 1_000.0 {
        format!("${:.2}K", meta.market_cap / 1_000.0)
    } else {
        format!("${:.2}", meta.market_cap)
    };

    // Format Holder Stats beautifully
    let holders_formatted = match holder_stats {
        Some(stats) => format!(
            "{} (🐳 Whales: {}, 🐬 Dolphins: {}, 🦐 Shrimps: {})",
            stats.total_holders, stats.whales, stats.dolphins, stats.shrimps
        ),
        None => "N/A (Failed to fetch)".to_string(),
    };
    
    let text = format!(
        "{}\n\n\
         👤 <b>Name:</b> {}\n\
         🌐 <b>Wallet:</b> <code>{}</code>\n\n\
         ⚡ <b>Action:</b> <b>{}</b>\n\
         🪙 <b>Token Name:</b> {} ({})\n\
         🪙 <b>Token Addr:</b> <code>{}</code>\n\
         💰 <b>Amount SOL:</b> {:.4} SOL\n\
         🔢 <b>Amount Tokens:</b> {:.2}\n\
         💵 <b>USD Value:</b> ${:.2}\n\
         📊 <b>Market Cap:</b> {}\n\
         📅 <b>Token Age:</b> {:.1} days\n\
         👥 <b>Holders:</b> {}\n\
         🎯 <b>Platform:</b> {}\n\n\
         {}\n\
         🔗 <a href=\"https://dexscreener.com/solana/{}\">View Coin on DexScreener</a>",
        title,
        escaped_name,
        pending.wallet_address,
        action_emoji,
        meta.name,
        meta.symbol,
        pending.token_address,
        pending.amount_sol,
        pending.amount_tokens,
        usd_value,
        mc_formatted,
        meta.age_days,
        holders_formatted,
        pending.platform,
        tx_links,
        pending.token_address
    );
    
    let payload = TelegramPayload {
        chat_id,
        text,
        parse_mode: "HTML".to_string(),
        disable_web_page_preview: false,
    };
    
    let response = client.post(&url)
        .json(&payload)
        .send()
        .await
        .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.into() })?;
        
    let status = response.status();
    if !status.is_success() {
        let err_body = response.text().await.unwrap_or_default();
        eprintln!("[Telegram] Failed to send notification: status={}, body={}", status, err_body);
        return Err(format!("Telegram API returned error status: {}", status).into());
    }
    
    println!("[Telegram] Notification sent successfully for wallet {}", pending.wallet_name);

    // 4. Send to Discord if webhook URL is configured in environment
    if let Ok(discord_url) = std::env::var("DISCORD_WEBHOOK_SOL_SWAP") {
        if !discord_url.is_empty() {
            if let Err(e) = send_discord_webhook(&discord_url, &pending, &meta, usd_value, &mc_formatted, &holders_formatted).await {
                eprintln!("[Discord] Error sending notification: {:?}", e);
            }
        }
    }
    
    Ok(())
}

#[derive(Serialize)]
struct DiscordPayload {
    embeds: Vec<DiscordEmbed>,
}

#[derive(Serialize)]
struct DiscordEmbed {
    title: String,
    description: String,
    color: u32,
    fields: Vec<DiscordField>,
}

#[derive(Serialize)]
struct DiscordField {
    name: String,
    value: String,
    #[serde(default)]
    inline: bool,
}

async fn send_discord_webhook(
    webhook_url: &str,
    pending: &PendingAlert,
    meta: &TokenMetadata,
    usd_value: f64,
    mc_formatted: &str,
    holders_formatted: &str,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let client = reqwest::Client::new();
    
    let is_buy = pending.action.to_uppercase() == "BUY";
    let color = if is_buy { 3066993 } else { 15158332 }; // Green or Red
    
    let title = if pending.signatures.len() > 1 {
        format!("🎯 SOL SWAP DETECTED ({} Combined Tx) 🎯", pending.signatures.len())
    } else {
        "🎯 SOL SWAP DETECTED 🎯".to_string()
    };

    let mut description = String::new();
    if pending.signatures.len() == 1 {
        description.push_str(&format!(
            "🔗 [View Transaction on Solscan](https://solscan.io/tx/{})\n",
            pending.signatures[0]
        ));
    } else {
        description.push_str("**Transactions:**\n");
        for (i, sig) in pending.signatures.iter().enumerate() {
            description.push_str(&format!(
                "{}. [Tx {}](https://solscan.io/tx/{})\n",
                i + 1,
                &sig[0..8],
                sig
            ));
        }
    }
    description.push_str(&format!(
        "\n🔗 [View Coin on DexScreener](https://dexscreener.com/solana/{})",
        pending.token_address
    ));

    let fields = vec![
        DiscordField {
            name: "👤 Name".to_string(),
            value: pending.wallet_name.clone(),
            inline: true,
        },
        DiscordField {
            name: "⚡ Action".to_string(),
            value: format!("**{}**", pending.action.to_uppercase()),
            inline: true,
        },
        DiscordField {
            name: "🪙 Token".to_string(),
            value: format!("{} ({})", meta.name, meta.symbol),
            inline: true,
        },
        DiscordField {
            name: "💰 Amount SOL".to_string(),
            value: format!("{:.4} SOL", pending.amount_sol),
            inline: true,
        },
        DiscordField {
            name: "🔢 Amount Tokens".to_string(),
            value: format!("{:.2}", pending.amount_tokens),
            inline: true,
        },
        DiscordField {
            name: "💵 USD Value".to_string(),
            value: format!("${:.2}", usd_value),
            inline: true,
        },
        DiscordField {
            name: "📊 Market Cap".to_string(),
            value: mc_formatted.to_string(),
            inline: true,
        },
        DiscordField {
            name: "📅 Token Age".to_string(),
            value: format!("{:.1} days", meta.age_days),
            inline: true,
        },
        DiscordField {
            name: "🎯 Platform".to_string(),
            value: pending.platform.clone(),
            inline: true,
        },
        DiscordField {
            name: "👥 Holders".to_string(),
            value: holders_formatted.to_string(),
            inline: false,
        },
        DiscordField {
            name: "🌐 Wallet".to_string(),
            value: format!("`{}`", pending.wallet_address),
            inline: false,
        },
    ];

    let payload = DiscordPayload {
        embeds: vec![DiscordEmbed {
            title,
            description,
            color,
            fields,
        }],
    };

    let response = client.post(webhook_url)
        .json(&payload)
        .send()
        .await
        .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.into() })?;

    let status = response.status();
    if !status.is_success() {
        let err_body = response.text().await.unwrap_or_default();
        eprintln!("[Discord] Failed to send notification: status={}, body={}", status, err_body);
        return Err(format!("Discord API returned error status: {}", status).into());
    }

    println!("[Discord] Notification sent successfully for wallet {}", pending.wallet_name);
    Ok(())
}

fn escape_html(input: &str) -> String {
    input.replace('&', "&amp;")
         .replace('<', "&lt;")
         .replace('>', "&gt;")
}
