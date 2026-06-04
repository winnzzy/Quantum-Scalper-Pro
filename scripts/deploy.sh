#!/bin/bash
set -e

echo "🚀 Quantum Scalper Pro - Deployment Script"

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "Docker required but not installed. Aborting." >&2; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo "Docker Compose required but not installed. Aborting." >&2; exit 1; }

# Create necessary directories
mkdir -p data logs backups

# Set permissions
chmod 755 data logs backups

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Pull latest images
docker-compose pull

# Build and start services
docker-compose up -d --build

# Run migrations
docker-compose exec backend alembic upgrade head

# Health check
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check backend health
if curl -f http://localhost:8000/api/v1/system/health >/dev/null 2>&1; then
    echo "✅ Backend is healthy"
else
    echo "⚠️  Backend health check failed"
fi

echo "✅ Deployment complete!"
echo "🌐 Dashboard: http://localhost"
echo "📊 Grafana: http://localhost:3001"
echo "📈 Prometheus: http://localhost:9090"
