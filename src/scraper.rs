use reqwest::header::{HeaderMap, HeaderValue};
use crate::db::{self, Wallet};
use std::collections::HashSet;

#[derive(serde::Deserialize, Debug)]
struct LeaderboardResponse {
    data: Vec<LeaderboardItem>,
}

#[derive(serde::Deserialize, Debug)]
struct LeaderboardItem {
    wallet_address: String,
    name: String,
    telegram: Option<String>,
    twitter: Option<String>,
    profit: f64,
    wins: i64,
    losses: i64,
    timeframe: i64,
}

#[derive(serde::Deserialize, Debug)]
struct AveResponse {
    #[allow(dead_code)]
    status: i64,
    #[allow(dead_code)]
    msg: String,
    data: Vec<AveWalletItem>,
}

#[derive(serde::Deserialize, Debug)]
struct AveWalletItem {
    wallet_address: String,
    remark: Option<String>,
    wallet_logo: Option<AveWalletLogo>,
    total_profit: f64,
    buy_trades: i64,
    sell_trades: i64,
}

#[derive(serde::Deserialize, Debug)]
struct AveWalletLogo {
    name: Option<String>,
    url: Option<String>,
}

#[derive(serde::Deserialize, Debug)]
struct CalloutResponse {
    callouts: Vec<CalloutItem>,
}

#[derive(serde::Deserialize, Debug)]
struct CalloutItem {
    #[serde(rename = "userId")]
    user_id: String,
    #[serde(rename = "avgMultiple")]
    avg_multiple: f64,
    #[serde(rename = "pct2xOrMore")]
    pct_2x_or_more: f64,
    #[serde(rename = "totalCallouts")]
    total_callouts: i64,
}

pub async fn scrape_kol_leaderboard() -> Result<Vec<Wallet>, Box<dyn std::error::Error + Send + Sync>> {
    println!("[Scraper] Starting kolscan.io leaderboard scrape...");
    let cookie = match std::env::var("KOLSCAN_COOKIE") {
        Ok(c) if !c.is_empty() => c,
        _ => {
            println!("[Scraper] KOLSCAN_COOKIE not set, skipping kolscan leaderboard");
            return Ok(Vec::new());
        }
    };

    let client = reqwest::Client::new();
    let mut headers = HeaderMap::new();
    headers.insert("accept", HeaderValue::from_static("*/*"));
    headers.insert("accept-language", HeaderValue::from_static("en-US,en;q=0.9,id;q=0.8"));
    headers.insert("content-type", HeaderValue::from_static("application/json"));
    headers.insert("cookie", HeaderValue::from_str(&cookie).map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.to_string().into() })?);
    headers.insert("origin", HeaderValue::from_static("https://kolscan.io"));
    headers.insert("priority", HeaderValue::from_static("u=1, i"));
    headers.insert("referer", HeaderValue::from_static("https://kolscan.io/leaderboard"));
    headers.insert("sec-ch-ua", HeaderValue::from_static("\"Chromium\";v=\"148\", \"Google Chrome\";v=\"148\", \"Not/A)Brand\";v=\"99\""));
    headers.insert("sec-ch-ua-mobile", HeaderValue::from_static("?0"));
    headers.insert("sec-ch-ua-platform", HeaderValue::from_static("\"Windows\""));
    headers.insert("sec-fetch-dest", HeaderValue::from_static("empty"));
    headers.insert("sec-fetch-mode", HeaderValue::from_static("cors"));
    headers.insert("sec-fetch-site", HeaderValue::from_static("same-origin"));
    headers.insert("user-agent", HeaderValue::from_static("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"));

    let payload = serde_json::json!({
        "timeframe": 1,
        "page": 1,
        "pageSize": 50
    });

    let response = client.post("https://kolscan.io/api/leaderboard")
        .headers(headers)
        .json(&payload)
        .send()
        .await
        .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.into() })?;

    let status = response.status();
    if !status.is_success() {
        let err_body = response.text().await.unwrap_or_default();
        return Err(format!("Kolscan leaderboard request failed with status: {}, body: {}", status, err_body).into());
    }

    let resp_data: LeaderboardResponse = response.json().await
        .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.into() })?;

    let wallets: Vec<Wallet> = resp_data.data.into_iter().map(|item| Wallet {
        wallet_address: item.wallet_address,
        name: item.name,
        telegram: item.telegram,
        twitter: item.twitter,
        profit: item.profit,
        wins: item.wins,
        losses: item.losses,
        timeframe: item.timeframe,
    }).collect();

    Ok(wallets)
}

pub async fn scrape_ave_list(
    url: &str,
    label: &str,
) -> Result<Vec<Wallet>, Box<dyn std::error::Error + Send + Sync>> {
    println!("[Scraper] Starting Ave.ai {} scrape...", label);
    let x_auth = match std::env::var("AVE_X_AUTH") {
        Ok(a) if !a.is_empty() => a,
        _ => {
            println!("[Scraper] AVE_X_AUTH not set, skipping Ave.ai {}", label);
            return Ok(Vec::new());
        }
    };

    // Replace 30zjs.com with api.agacve.com to bypass Tencent edge authentication checks
    let target_url = if url.contains("30zjs.com") {
        url.replace("30zjs.com", "api.agacve.com")
    } else {
        url.to_string()
    };

    let client = reqwest::Client::new();
    let mut headers = HeaderMap::new();
    headers.insert("accept", HeaderValue::from_static("*/*"));
    headers.insert("ave-platform", HeaderValue::from_static("web"));
    headers.insert("lang", HeaderValue::from_static("en"));
    headers.insert("origin", HeaderValue::from_static("https://pro.ave.ai"));
    headers.insert("referer", HeaderValue::from_static("https://pro.ave.ai/"));
    headers.insert("x-auth", HeaderValue::from_str(&x_auth).map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.to_string().into() })?);
    headers.insert("user-agent", HeaderValue::from_static("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"));

    let response = client.get(&target_url)
        .headers(headers)
        .send()
        .await
        .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.into() })?;

    let status = response.status();
    if !status.is_success() {
        let err_body = response.text().await.unwrap_or_default();
        return Err(format!("Ave.ai {} request failed with status: {}, body: {}", label, status, err_body).into());
    }

    let resp_data: AveResponse = response.json().await
        .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.into() })?;

    println!("[Scraper] Retrieved {} items from Ave.ai {}", resp_data.data.len(), label);

    let wallets: Vec<Wallet> = resp_data.data.into_iter().map(|item| {
        // Resolve name
        let mut name = String::new();
        if let Some(ref logo) = item.wallet_logo {
            if let Some(ref n) = logo.name {
                name = n.clone();
            }
        }
        if name.is_empty() {
            if let Some(ref rem) = item.remark {
                name = rem.clone();
            }
        }
        if name.is_empty() {
            name = format!("{} {}", label, &item.wallet_address[0..4]);
        }

        // Resolve twitter
        let mut twitter = None;
        if let Some(ref logo) = item.wallet_logo {
            if let Some(ref url) = logo.url {
                if url.contains("twitter.com") || url.contains("x.com") {
                    twitter = Some(url.clone());
                }
            }
        }

        Wallet {
            wallet_address: item.wallet_address,
            name,
            telegram: None,
            twitter,
            profit: item.total_profit,
            wins: item.buy_trades,
            losses: item.sell_trades,
            timeframe: 30,
        }
    }).collect();

    Ok(wallets)
}

pub async fn scrape_callout_leaderboard() -> Result<Vec<Wallet>, Box<dyn std::error::Error + Send + Sync>> {
    println!("[Scraper] Starting pump.fun callout leaderboard scrape...");
    let cookie = match std::env::var("PUMP_COOKIE") {
        Ok(c) if !c.is_empty() => c,
        _ => {
            println!("[Scraper] PUMP_COOKIE not set, skipping pump.fun callout leaderboard");
            return Ok(Vec::new());
        }
    };

    let client = reqwest::Client::new();
    let mut headers = HeaderMap::new();
    headers.insert("accept", HeaderValue::from_static("*/*"));
    headers.insert("cookie", HeaderValue::from_str(&cookie).map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.to_string().into() })?);
    headers.insert("origin", HeaderValue::from_static("https://pump.fun"));
    headers.insert("referer", HeaderValue::from_static("https://pump.fun/"));
    headers.insert("user-agent", HeaderValue::from_static("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"));

    let response = client.get("https://frontend-api-v3.pump.fun/callout/leaderboard?limit=50")
        .headers(headers)
        .send()
        .await
        .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.into() })?;

    let status = response.status();
    if !status.is_success() {
        let err_body = response.text().await.unwrap_or_default();
        return Err(format!("Pump.fun callout leaderboard request failed with status: {}, body: {}", status, err_body).into());
    }

    let resp_data: CalloutResponse = response.json().await
        .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.into() })?;

    println!("[Scraper] Retrieved {} items from pump.fun callout leaderboard", resp_data.callouts.len());

    let wallets: Vec<Wallet> = resp_data.callouts.into_iter().map(|item| {
        let wins = (item.total_callouts as f64 * item.pct_2x_or_more).round() as i64;
        let losses = item.total_callouts - wins;
        let name = format!("Smart Wallet {} (Callout)", &item.user_id[0..4]);

        Wallet {
            wallet_address: item.user_id,
            name,
            telegram: None,
            twitter: None,
            profit: item.avg_multiple,
            wins,
            losses,
            timeframe: 30,
        }
    }).collect();

    Ok(wallets)
}

pub async fn scrape_and_update_db(
    db_path: String,
) -> Result<Vec<Wallet>, Box<dyn std::error::Error + Send + Sync>> {
    println!("[Scraper] Starting database update with all sources from env...");
    
    let mut all_wallets = Vec::new();
    
    // 1. Scrape kolscan.io KOL leaderboard
    match scrape_kol_leaderboard().await {
        Ok(kol_wallets) => {
            println!("[Scraper] Fetched {} KOL wallets from kolscan.io successfully", kol_wallets.len());
            all_wallets.extend(kol_wallets);
        }
        Err(e) => {
            eprintln!("[Scraper] Error scraping KOL leaderboard from kolscan: {:?}", e);
        }
    }
    
    // 2. Scrape Ave.ai Smart Wallets
    match scrape_ave_list(
        "https://api.agacve.com/v1api/v4/tokens/smart_wallet/list?chain=solana&sort=rank_score&sort_dir=desc&interval=30D",
        "Smart Wallet"
    ).await {
        Ok(smart_wallets) => {
            println!("[Scraper] Fetched {} smart wallets from Ave.ai successfully", smart_wallets.len());
            all_wallets.extend(smart_wallets);
        }
        Err(e) => {
            eprintln!("[Scraper] Error scraping smart wallets from Ave.ai: {:?}", e);
        }
    }
    
    // 3. Scrape Ave.ai KOLs
    match scrape_ave_list(
        "https://api.agacve.com/v1api/v4/tokens/kol/list?chain=solana&sort=rank_score&sort_dir=desc&interval=1D",
        "KOL"
    ).await {
        Ok(ave_kols) => {
            println!("[Scraper] Fetched {} KOL wallets from Ave.ai successfully", ave_kols.len());
            all_wallets.extend(ave_kols);
        }
        Err(e) => {
            eprintln!("[Scraper] Error scraping KOLs from Ave.ai: {:?}", e);
        }
    }
    
    // 4. Scrape Pump.fun Callout Leaderboard
    match scrape_callout_leaderboard().await {
        Ok(callout_wallets) => {
            println!("[Scraper] Fetched {} smart wallets from pump.fun callout successfully", callout_wallets.len());
            all_wallets.extend(callout_wallets);
        }
        Err(e) => {
            eprintln!("[Scraper] Error scraping pump.fun callouts: {:?}", e);
        }
    }
    
    if all_wallets.is_empty() {
        return Err("All wallet scraper sources failed or returned no wallets".into());
    }
    
    // Deduplicate by wallet address
    let mut seen = HashSet::new();
    let mut deduplicated_wallets = Vec::new();
    for wallet in all_wallets {
        if seen.insert(wallet.wallet_address.clone()) {
            deduplicated_wallets.push(wallet);
        }
    }
    
    println!("[Scraper] Total merged & deduplicated wallets across all sources: {}", deduplicated_wallets.len());
    
    // Save to DB
    let db_path_clone = db_path;
    let wallets_clone = deduplicated_wallets.clone();
    tokio::task::spawn_blocking(move || {
        db::save_wallets(&db_path_clone, &wallets_clone)
    }).await
    .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.to_string().into() })?
    .map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.to_string().into() })?;
    
    println!("[Scraper] Successfully updated wallets in DB");
    
    Ok(deduplicated_wallets)
}
