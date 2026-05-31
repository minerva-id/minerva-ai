# Deploy Minerva AI ke Railway

## Persiapan

### 1. Install Railway CLI (Opsional)
```bash
npm install -g @railway/cli
railway login
```

### 2. Atau gunakan GitHub Integration (Recommended)

## Cara Deploy

### Opsi A: Deploy via Railway CLI

1. **Login ke Railway**
```bash
railway login
```

2. **Inisialisasi Project**
```bash
cd /home/minerva/minerva-ai
railway init
```

3. **Deploy**
```bash
railway up
```

4. **Set Environment Variables**
```bash
# Set semua environment variables yang diperlukan
railway variables set HELIUS_API_KEY=your_key_here
railway variables set TELEGRAM_BOT_TOKEN=your_token_here
railway variables set TELEGRAM_CHAT_ID=your_chat_id_here
# ... dan seterusnya untuk semua variables di .env
```

5. **Generate Domain**
```bash
railway domain
```

### Opsi B: Deploy via GitHub (Recommended)

1. **Push code ke GitHub repository**
```bash
git add .
git commit -m "Add API server for Railway deployment"
git push origin master
```

2. **Buka Railway Dashboard**
   - Pergi ke https://railway.app
   - Login dengan GitHub
   - Klik "New Project"
   - Pilih "Deploy from GitHub repo"
   - Pilih repository `minerva-ai`

3. **Railway akan otomatis detect Dockerfile dan deploy**

4. **Set Environment Variables di Railway Dashboard**
   - Klik project yang baru dibuat
   - Pergi ke tab "Variables"
   - Tambahkan semua environment variables dari `.env.example`:
     - `HELIUS_API_KEY`
     - `TELEGRAM_BOT_TOKEN`
     - `TELEGRAM_CHAT_ID`
     - `SOLANA_RPC_URL`
     - `DISCORD_WEBHOOK_AI_BULLETIN`
     - `DISCORD_WEBHOOK_ARKHAM_TRANSACTIONS`
     - `DISCORD_WEBHOOK_SOL_SWAP`
     - `DISCORD_WEBHOOK_PERPS_SIGNAL`
     - Dan semua variables lainnya yang diperlukan

5. **Generate Public Domain**
   - Pergi ke tab "Settings"
   - Scroll ke "Networking"
   - Klik "Generate Domain"
   - Copy URL yang digenerate (contoh: `minerva-ai-production.up.railway.app`)

## Environment Variables yang Wajib

Minimal environment variables yang harus di-set:

```bash
# Core API Keys
HELIUS_API_KEY=your_helius_api_key
SOLANA_RPC_URL=https://mainnet.helius-rpc.com/?api-key=your_helius_api_key

# Telegram Notifications
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Database (Railway akan provide persistent storage)
WALLETS_DB_PATH=/app/data/wallets.db

# Port (Railway set otomatis, tapi bisa override)
PORT=3000
```

## Setelah Deploy

### Test API Endpoints

1. **Health Check**
```bash
curl https://your-app.up.railway.app/
```

Response:
```json
{
  "status": "ok",
  "service": "minerva-ai",
  "version": "0.1.0"
}
```

2. **Get Wallets**
```bash
curl https://your-app.up.railway.app/api/wallets
```

3. **Get Transactions**
```bash
curl https://your-app.up.railway.app/api/transactions
```

## Update Dashboard Configuration

Setelah backend deploy, update dashboard untuk connect ke Railway:

1. Edit `dashboard/src/App.tsx`
2. Set default API URL ke Railway domain:
```typescript
const [apiUrl, setApiUrl] = useState('https://your-app.up.railway.app');
```

## Monitoring

- **Logs**: `railway logs` atau lihat di Railway Dashboard
- **Metrics**: Tersedia di Railway Dashboard
- **Restart**: `railway restart` atau via Dashboard

## Persistent Storage

Railway menyediakan persistent volumes. Untuk database SQLite:

1. Di Railway Dashboard, pergi ke project settings
2. Tambahkan Volume di tab "Volumes"
3. Mount path: `/app/data`
4. Set `WALLETS_DB_PATH=/app/data/wallets.db`

## Troubleshooting

### Build Failed
- Check Dockerfile syntax
- Pastikan semua dependencies di Cargo.toml valid
- Check Railway build logs

### Runtime Error
- Check environment variables sudah di-set semua
- Check Railway logs: `railway logs`
- Pastikan PORT binding ke `0.0.0.0` bukan `127.0.0.1`

### Database Issues
- Pastikan volume mounted dengan benar
- Check WALLETS_DB_PATH environment variable
- Database akan auto-create saat pertama kali run

## Cost Estimation

Railway pricing (as of 2026):
- Free tier: $5 credit/month
- Hobby plan: $5/month + usage
- Estimated cost untuk app ini: ~$5-10/month

## Next Steps

1. ✅ Backend deployed ke Railway
2. 🔄 Update dashboard untuk connect ke Railway API
3. 🔄 Test end-to-end integration
4. 🔄 Deploy dashboard ke Vercel/Netlify
