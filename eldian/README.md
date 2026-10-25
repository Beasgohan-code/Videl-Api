# Videl Music API

MIT License - Copyright (c) 2026 Videl Network

Simple FastAPI service for music bots:

- bots call the API with an API key
- the API downloads audio from YouTube using the supplied video ID
- the API returns the track file back to the caller
- API keys are stored in MongoDB
- a Telegram owner bot can create, list, and revoke keys
- downloads are retried and stale temporary files are cleaned up automatically

Support: <https://t.me/videl_bot_update>
Readme / contact: <https://t.me/EgoManiacMe>

## Features

- `GET /health`
- `POST /v1/track/by-video-id`
- Mongo-backed key issuance and lookup
- owner-only Telegram commands: `/start`, `/getapi`, `/listkey`, `/revoke`

## Environment variables

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=videl_music
API_HOST=0.0.0.0
API_PORT=8000
API_BASE_URL=http://localhost:8000
YT_DLP_FORMAT=bestaudio/best
YT_DLP_SOCKET_TIMEOUT=20
YT_DLP_RETRIES=3
DOWNLOAD_CLEANUP_SECONDS=900
YOUTUBE_PROXY=http://user:pass@127.0.0.1:8080
YOUTUBE_COOKIES="name=value; other=value"
YOUTUBE_COOKIES_FILE=/path/to/cookies.txt
OWNER_ID=123456789
TELEGRAM_BOT_TOKEN=123:abc
```

## Run the API

```bash
python -m uvicorn app.main:app --reload
```

## Run the Telegram bot

```bash
python telegram_bot.py
```

## API usage

```bash
curl -X POST "http://localhost:8000/v1/track/by-video-id" \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"video_id":"dQw4w9WgXcQ"}' --output track
```

## Ubuntu 22.04 hosting setup

Use the following commands on a fresh Ubuntu 22.04 server as `ubuntu`.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git curl nginx
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
cd /home/ubuntu
git clone https://github.com/Videl-Network/videl-music-api.git
cd videl-music-api
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env 2>/dev/null || true
```

Create a `.env` file:

```bash
nano /home/ubuntu/videl-music-api/.env
```

Example contents:

```bash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=videl_music
API_HOST=0.0.0.0
API_PORT=8000
API_BASE_URL=http://YOUR_SERVER_IP:8000
YT_DLP_FORMAT=bestaudio/best
YT_DLP_SOCKET_TIMEOUT=20
YT_DLP_RETRIES=3
DOWNLOAD_CLEANUP_SECONDS=900
OWNER_ID=123456789
TELEGRAM_BOT_TOKEN=your_bot_token
```

Run the API manually for testing:

```bash
cd /home/ubuntu/videl-music-api
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run the Telegram bot:

```bash
cd /home/ubuntu/videl-music-api
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
python telegram_bot.py
```

### Systemd services

Create the API service:

```bash
sudo tee /etc/systemd/system/videl-music-api.service > /dev/null <<'EOF'
[Unit]
Description=Videl Music API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/videl-music-api
EnvironmentFile=/home/ubuntu/videl-music-api/.env
ExecStart=/home/ubuntu/videl-music-api/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

Create the bot service:

```bash
sudo tee /etc/systemd/system/videl-music-bot.service > /dev/null <<'EOF'
[Unit]
Description=Videl Music Telegram Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/videl-music-api
EnvironmentFile=/home/ubuntu/videl-music-api/.env
ExecStart=/home/ubuntu/videl-music-api/.venv/bin/python /home/ubuntu/videl-music-api/telegram_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

Enable and start the services:

```bash
sudo systemctl daemon-reload
sudo systemctl enable videl-music-api videl-music-bot
sudo systemctl start videl-music-api videl-music-bot
sudo systemctl status videl-music-api videl-music-bot
```

### Nginx reverse proxy

Create an Nginx config:

```bash
sudo tee /etc/nginx/sites-available/videl-music-api > /dev/null <<'EOF'
server {
    listen 80;
    server_name YOUR_SERVER_DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
```

Enable it:

```bash
sudo ln -s /etc/nginx/sites-available/videl-music-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Notes

- The downloader uses `yt-dlp`, retries failures, and streams the file returned by YouTube for the selected video ID.
- Temporary download folders are cleaned after each request, and stale folders are pruned on startup.
- API keys can be created, listed, and revoked from the owner-only Telegram bot.
- For production use, run this behind a proxy, set proper rate limits, and review YouTube terms for your deployment.
