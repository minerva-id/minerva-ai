# Minerva AI Tracker - AWS Deployment Guide using Docker

This guide details the step-by-step process of deploying the **Minerva AI** tracker container onto an **AWS EC2** instance using **Docker** and **Docker Compose**.

---

## 1. Prerequisites on AWS
Before beginning, ensure you have:
1. An **AWS EC2 Instance** (Recommended: `t3.medium` or larger for compiling/running stable WebSocket listeners).
2. **Security Group Config**:
   * Outbound traffic allowed (needed for connecting to Helius RPC WebSocket, DexScreener API, RugCheck API, Telegram Bot API, and Discord Webhooks).
   * Inbound traffic: Only SSH (port 22) is required since this is a background daemon that doesn't expose external ports.
3. **Docker** and **Docker Compose** installed on the EC2 instance.

---

## 2. Docker & Docker Compose Installation on AWS EC2
If Docker is not already installed on your Amazon Linux/Ubuntu instance, run:

### For Ubuntu:
```bash
# Update package list
sudo apt-get update

# Install Docker
sudo apt-get install -y docker.io

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Start and enable Docker service
sudo systemctl start docker
sudo systemctl enable docker

# Allow your user to run docker commands without sudo
sudo usermod -aG docker $USER
# Log out and log back in to apply group changes!
```

---

## 3. Project Configuration

### Directory Structure
On your EC2 instance, place the codebase in a folder (e.g., `/home/ubuntu/minerva-ai`):
```text
/home/ubuntu/minerva-ai/
├── Dockerfile
├── docker-compose.yml
├── Cargo.toml
├── Cargo.lock
├── src/
│   ├── main.rs
│   ├── db.rs
│   ├── scraper.rs
│   ├── telegram.rs
│   └── ws.rs
└── .env
```

### Environment File (`.env`)
Create a `.env` file in the root of `/home/ubuntu/minerva-ai/` containing your API keys, tokens, and webhooks:
```env
# Database configuration (leave as is for container volume path)
WALLETS_DB_PATH=/app/data/wallets.db

# API Credentials
HELIUS_API_KEY=4d523832-c5ea-4733-bab4-071ac2f43329

# Scraper Cookies & Auth Tokens
KOLSCAN_COOKIE=your_kolscan_cookie_here
AVE_X_AUTH=2c8ca614a557a2a4e013bc77b8f00e851779896937984062900
PUMP_COOKIE=your_pump_cookie_here

# Notification Channels
TELEGRAM_BOT_TOKEN=8812686337:AAHOdk6HyBXPoa4_9c1TAhxLYtCcIw_Ro3Q
TELEGRAM_CHAT_ID=-1003987224700

# Discord Webhook integration
DISCORD_WEBHOOK_SOL_SWAP=https://discord.com/api/webhooks/your_webhook_url_here
```

---

## 4. Deployment Steps

Navigate to the project directory and build the container:

```bash
# 1. Navigate to the project directory
cd /home/ubuntu/minerva-ai

# 2. Build the Docker image and start the container in background daemon mode
docker-compose up -d --build
```

### Verification
Check if the tracker started successfully and is fetching log alerts:
```bash
# View active container status
docker-compose ps

# Monitor real-time logs
docker-compose logs -f
```

---

## 5. Persistence and Maintenance

### SQLite Database Backup
The SQLite database file `wallets.db` is stored inside the local `./data` directory on the host machine which is mapped directly inside the container (`/app/data`). 
* Updates to the wallets database will persist even if the container is rebuilt, updated, or restarted.
* To perform a backup of the active wallets, simply copy the `./data/wallets.db` file to a secure backup directory.

### Stopping/Updating the Tracker
To update the app code or `.env` configuration:
```bash
# Stop the container
docker-compose down

# (Make your edits to .env or pull new code via git)

# Restart and rebuild
docker-compose up -d --build
```

### Automatic Restart
The `restart: unless-stopped` flag in `docker-compose.yml` ensures that the tracking daemon automatically boots up if the EC2 instance restarts or if the app crashes.
```
