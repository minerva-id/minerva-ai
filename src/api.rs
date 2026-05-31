use axum::{
    extract::State,
    http::StatusCode,
    response::Json,
    routing::get,
    Router,
};
use serde_json::json;
use std::sync::Arc;
use tower_http::cors::{CorsLayer, Any};

use crate::db::{self, Wallet, Transaction};

#[derive(Clone)]
pub struct AppState {
    pub db_path: String,
}

pub fn create_router(db_path: String) -> Router {
    let state = Arc::new(AppState { db_path });

    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    Router::new()
        .route("/", get(health_check))
        .route("/api/wallets", get(get_wallets))
        .route("/api/transactions", get(get_transactions))
        .layer(cors)
        .with_state(state)
}

async fn health_check() -> Json<serde_json::Value> {
    Json(json!({
        "status": "ok",
        "service": "minerva-ai",
        "version": "0.1.0"
    }))
}

async fn get_wallets(
    State(state): State<Arc<AppState>>,
) -> Result<Json<Vec<Wallet>>, StatusCode> {
    let db_path = state.db_path.clone();
    
    let wallets = tokio::task::spawn_blocking(move || {
        db::get_active_wallets(db_path)
    })
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok(Json(wallets))
}

async fn get_transactions(
    State(state): State<Arc<AppState>>,
) -> Result<Json<Vec<Transaction>>, StatusCode> {
    let db_path = state.db_path.clone();
    
    let transactions = tokio::task::spawn_blocking(move || {
        db::get_recent_transactions(db_path, 100)
    })
    .await
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok(Json(transactions))
}
