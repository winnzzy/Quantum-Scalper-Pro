#!/bin/bash
set -euo pipefail

echo "🚀 Quantum Scalper Pro - Deployment Script"

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "Docker required but not installed. Aborting." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose plugin required. Aborting." >&2; exit 1; }

# Create necessary directories
mkdir -p data logs backups

# Set permissions
chmod 700 data logs backups

# Load environment variables
test -f .env || { echo ".env is required. Copy .env.example and replace every placeholder." >&2; exit 1; }
chmod 600 .env

# Pull latest images
docker compose config --quiet
docker compose pull

# Build and start services
docker compose up -d --build

# Run migrations
docker compose exec -T backend alembic upgrade head

# Health check
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check backend health
if docker compose exec -T backend python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/system/health', timeout=5)"; then
    echo "✅ Backend is healthy"
else
    echo "⚠️  Backend health check failed"
fi

echo "✅ Deployment complete!"
echo "🌐 Dashboard: http://localhost"
echo "📊 Grafana: http://localhost:3001"
echo "📈 Prometheus: http://localhost:9090"
