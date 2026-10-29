# Videl-Api Docker Deployment

## Quick Start

```bash
# Copy environment template
cp .env.docker .env
# Edit .env with your configuration

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f videl-api

# Stop all services
docker-compose down
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| videl-api | 8000 | Main REST API |
| aria2c | 6800, 6888 | Multi-connection downloader |
| mongodb | 27017 | Optional persistent storage |

## API Endpoints

- `GET  /health` - Health check
- `GET  /` - API info (v3.2.0)
- `GET  /v1/version` - Version info
- `GET  /v1/watchdog/health` - Component health (admin only)
- `GET  /docs` - Interactive API documentation
- `GET  /app` - Telegram WebApp

## Environment Variables

See `.env.docker` for all available configuration options.

## Volumes

- `videl-downloads` - Persistent download storage
- `videl-logs` - Application logs
- `videl-mongodb` - MongoDB data

## Security

The container runs as a non-root user (`videl`). The `.env` file is mounted read-only. Secrets like `TELEGRAM_BOT_TOKEN` and `ARIA2C_RPC_SECRET` should be set in `.env` (never committed to version control).
