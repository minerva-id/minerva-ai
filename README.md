# Minerva AI — Crypto Trading Agent

Production-ready AI-powered autonomous crypto trading agent. Built with Python 3.12 asyncio for high-performance, low-latency operation on minimal infrastructure.

## 🧠 Architecture

```
Market Data (WebSocket) → AI Brain (Fast + Slow Path) → Execution Engine → Exchange
       ↓                        ↓                            ↓
   Redis Cache            LLM + RAG Memory            Risk Validation
       ↓                        ↓                            ↓
   Aggregator             Decision Engine              OMS + Gateway
```

### Components
1. **Data Ingestion** — Real-time market data via ccxtpro WebSocket (Binance, Bybit, OKX), on-chain monitoring, news, and social sentiment
2. **AI Brain** — Fast path (technical indicators, ML signals <10ms) + Slow path (LLM reasoning via Groq/OpenAI 1-5min intervals)
3. **Execution Engine** — Order management, risk validation, smart routing across exchanges, and real-time WebSocket execution tracking (`ccxt.pro`).
4. **Memory** — Redis hot cache, Supabase journal, Pinecone RAG
5. **Monitoring** — Prometheus metrics, Telegram alerts, health checks

## 🚀 Quick Start

### 1. Clone & Configure
```bash
cp .env.example .env
# Edit .env with your API keys
```

### 2. Run with Docker Compose
```bash
docker compose up -d
```

### 3. Run Locally (Development)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m minerva.main
```

### 4. Paper Trading (Default)
The agent starts in paper trading mode (`AGENT_MODE=paper`). No real orders are placed.

### 5. Live Trading
```bash
# ⚠️ WARNING: Real money at risk
# Set AGENT_MODE=live in .env
# Ensure all risk parameters are correct
```

## ⚙️ Configuration

All configuration via environment variables. See [.env.example](.env.example) for the full list.

### Key Settings
| Variable | Description | Default |
|---|---|---|
| `AGENT_MODE` | `paper` or `live` | `paper` |
| `AGENT_LOOP_INTERVAL` | Brain loop interval (seconds) | `60` |
| `TRADING_PAIRS` | Comma-separated pairs | `BTC/USDT,ETH/USDT` |
| `PRIMARY_EXCHANGE` | Default exchange | `binance` |
| `LLM_PROVIDER` | `groq` or `openai` | `groq` |
| `MAX_POSITION_SIZE_USD` | Max per-trade size | `1000` |
| `MAX_DRAWDOWN_PERCENT` | Circuit breaker threshold | `10` |

## 🗄️ Database Setup

Run the SQL migration in your Supabase SQL Editor:
```bash
cat migrations/001_initial.sql
# Copy and paste into Supabase SQL Editor
```

## 🧪 Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## 📊 Monitoring

- **Health Check**: `http://localhost:8080/health`
- **Telegram**: Trade alerts, daily reports, error notifications
- **Grafana**: Connect to Prometheus Push Gateway for dashboards

## 🛡️ Risk Management

- **Position size limits** per trade and total exposure
- **Circuit breaker** halts trading on max drawdown
- **Daily loss limit** prevents runaway losses
- **Token whitelist** restricts tradable pairs
- **Idempotent execution** prevents duplicate orders

## 📁 Project Structure

```
src/minerva/
├── main.py          # Entry point & agent orchestrator
├── config.py        # Environment configuration
├── logger.py        # Structured logging
├── models/          # Pydantic data models
├── ingestion/       # Market data feeds
├── brain/           # AI signals & reasoning
├── execution/       # Order management & risk
├── memory/          # Redis, Supabase, Pinecone
├── monitoring/      # Metrics, Telegram, health
└── backtest/        # Paper trading & backtesting
```

## License

MIT
