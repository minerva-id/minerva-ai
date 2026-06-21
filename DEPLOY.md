# Panduan Deployment Minerva AI

Dokumen ini berisi instruksi langkah demi langkah (*step-by-step*) untuk melakukan *deployment* agen trading Minerva AI ke lingkungan produksi menggunakan Docker.

## Prasyarat (Prerequisites)

Sebelum memulai, pastikan server atau komputer Anda sudah memiliki hal-hal berikut:
1. **Sistem Operasi**: Linux (Ubuntu/Debian direkomendasikan) atau macOS.
2. **Docker & Docker Compose**: Sudah terinstal dan berjalan.
3. **Akun Layanan**:
   - Akun Exchange (Binance/Bybit/OKX) beserta API Key dan Secret-nya (aktifkan izin *trading*, jangan izinkan penarikan/*withdrawal*).
   - Akun [Supabase](https://supabase.com) untuk *database*.
   - Akun [Pinecone](https://pinecone.io) untuk *vector database* (opsional, untuk RAG/memori jangka panjang).
   - Akun LLM provider seperti [Groq](https://groq.com/) atau [OpenAI](https://openai.com/).
   - Akun [CryptoPanic](https://cryptopanic.com/) untuk berita sentimen (opsional).
   - [Telegram Bot](https://core.telegram.org/bots/features#botfather) Token dan *Chat ID* Anda.

---

## Langkah 1: Persiapan Server

1. **Kloning Repository (jika belum)**:
   ```bash
   git clone <url-repo-minerva>
   cd minerva-ai
   ```

2. **Siapkan Direktori Data**:
   Buat direktori untuk menyimpan *model machine learning* (jika ada):
   ```bash
   mkdir -p models
   ```

---

## Langkah 2: Persiapan Konfigurasi (Environment Variables)

1. **Salin file template `.env`**:
   ```bash
   cp .env.example .env
   ```

2. **Edit file `.env`**:
   Buka file `.env` menggunakan *editor* teks favorit Anda (contoh: `nano .env` atau `vim .env`), lalu isi nilai-nilainya:

   - **Mode Agen**:
     *Gunakan mode `paper` terlebih dahulu saat pertama kali mencoba agar uang asli Anda tidak terpakai.*
     ```env
     AGENT_MODE=paper # Ubah ke 'live' jika sudah siap
     TRADING_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT
     PRIMARY_EXCHANGE=binance
     ```
   
   - **Exchange API Keys**:
     Isi salah satu atau semuanya sesuai *exchange* yang Anda gunakan.
     Jika Anda ingin menggunakan akun Demo/Testnet (seperti Bybit Testnet), tambahkan `EXCHANGE_SANDBOX=true`.
     ```env
     BINANCE_API_KEY=kunci_api_binance_anda
     BINANCE_API_SECRET=rahasia_api_binance_anda
     EXCHANGE_SANDBOX=true # Ubah ke 'false' jika menggunakan akun real
     ```

   - **LLM Provider (Groq / OpenAI)**:
     ```env
     LLM_PROVIDER=groq
     GROQ_API_KEY=kunci_api_groq_anda
     ```

   - **Telegram Notifikasi**:
     ```env
     TELEGRAM_BOT_TOKEN=token_bot_telegram_anda
     TELEGRAM_CHAT_ID=chat_id_telegram_anda
     ```

   - **Supabase (Database)**:
     ```env
     SUPABASE_URL=url_project_supabase_anda
     SUPABASE_KEY=service_role_key_supabase_anda # Gunakan service_role key, bukan anon key
     ```

---

## Langkah 3: Setup Database (Supabase)

1. Buka *dashboard* [Supabase](https://app.supabase.com/) proyek Anda.
2. Navigasi ke menu **SQL Editor**.
3. Buka file `migrations/001_initial.sql` di repository lokal Anda, *copy* seluruh isinya.
4. *Paste* dan jalankan (*Run*) di SQL Editor Supabase.
5. Anda akan melihat pemberitahuan bahwa tabel `trades`, `orders`, `reasoning_logs`, dan `daily_reports` berhasil dibuat.

---

## Langkah 4: Membangun (Build) Docker Image

Minerva AI menggunakan Docker agar mudah dijalankan di environment apa pun tanpa masalah *dependency*.

Jalankan perintah berikut untuk mem-build *image* (ini akan memakan waktu beberapa menit saat pertama kali dijalankan):
```bash
docker compose build
```

---

## Langkah 5: Menjalankan Minerva AI (Deployment)

1. **Jalankan *container* di *background* (*detached mode*)**:
   ```bash
   docker compose up -d
   ```

2. **Periksa Status *Container***:
   Pastikan *container* `minerva-agent` dan `minerva-redis` berstatus `Up` dan `Healthy`.
   ```bash
   docker compose ps
   ```

3. **Melihat Log secara *Real-time***:
   Ini sangat penting untuk memastikan agen berhasil terkoneksi ke *exchange* dan tidak ada *error*.
   ```bash
   docker compose logs -f agent
   ```
   *Anda seharusnya melihat log bertuliskan `minerva_started`.*

---

## Langkah 6: Pemantauan (Monitoring) & Operasional

### Notifikasi Telegram
Jika Anda mengonfigurasi Telegram, Anda akan segera menerima pesan dari Bot Anda:
> 🚀 **Minerva AI Started**
> Mode: PAPER
> Pairs: BTC/USDT, ETH/USDT, SOL/USDT

### Pengecekan Kesehatan (*Health Check*)
Agen Minerva memiliki server *health check* internal yang terus dipantau oleh Docker. Jika Anda ingin memeriksanya secara manual dari *host machine*:
```bash
curl -s http://localhost:8080/health
# Output: {"status": "running", "uptime_seconds": ...}
```

### Mematikan / Menghentikan Agen
Jika Anda ingin menghentikan agen secara aman (agar *order* ditutup/dihentikan dengan benar):
```bash
docker compose down
```

### Memperbarui (Update) Kode
Jika Anda telah menarik (*pull*) pembaruan kode baru dari Git, gunakan langkah berikut untuk memperbarui versi di *production*:
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

---

## Langkah 7: Transisi dari Paper Trading ke Live Trading ⚠️

Setelah Anda mengevaluasi kinerja agen selama beberapa hari di mode `paper` dan merasa yakin:

1. Hentikan sistem: `docker compose down`
2. Buka dan edit file `.env`
3. Ubah `AGENT_MODE=paper` menjadi `AGENT_MODE=live`
4. **PERHATIKAN**: Pastikan Anda telah mengatur `MAX_POSITION_SIZE_USD`, `MAX_TOTAL_EXPOSURE_USD`, dan `MAX_DRAWDOWN_PERCENT` sesuai profil risiko yang sanggup Anda tanggung! Agen akan memakai dana riil dari akun *exchange* Anda.
5. Jalankan kembali: `docker compose up -d`
6. Pantau *log* secara ketat selama beberapa jam pertama: `docker compose logs -f agent`.
