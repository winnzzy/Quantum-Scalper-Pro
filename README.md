# Quantum Scalper Pro

**Production-Grade Automated Trading Platform**

Quantum Scalper Pro is a fully deployable commercial-grade automated trading platform supporting Forex and Cryptocurrency trading with advanced risk management, AI filtering, and professional analytics.

## Features

### Trading
- **Forex Trading** via MetaTrader 5
- **Cryptocurrency Trading** via Binance (Spot, Futures, Testnet)
- **Paper Trading** for strategy testing
- **Live Trading** with real capital
- **Scalping Strategies** optimized for short-term trades

### Strategies (4 Built-in)
1. **EMA Scalper** - EMA 9/21/50 crossover with ATR
2. **VWAP Scalper** - VWAP pullback with RSI and volume
3. **Breakout Scalper** - Support/resistance breakout with volume confirmation
4. **Mean Reversion** - Bollinger Bands with RSI and Stochastic

### Risk Management (Highest Priority)
- Maximum risk per trade (0.25%, 0.5%, 1%, Custom)
- Daily/Weekly/Monthly loss limits
- Maximum drawdown protection (auto-pause)
- Consecutive loss protection
- Spread protection
- Volatility protection
- Weekend protection
- Mandatory stop loss
- Position sizing algorithms

### AI Filter
- XGBoost/LightGBM-based trade quality scoring
- Filters bad trades (does not generate them)
- Inputs: Volatility, Spread, Indicator Strength, Session, Volume
- Output: Quality Score (0-1), Confidence Score (0-1)

### News Filter
- Economic calendar integration
- Avoids trading during NFP, CPI, FOMC, Interest Rate decisions
- Configurable buffer periods

### Security
- JWT Authentication with refresh tokens
- Role-based access control (Admin, Trader, Viewer, Affiliate)
- Rate limiting
- Encrypted secrets
- Audit logs
- Two-factor authentication support

### Notifications
- Telegram bot integration
- Email notifications (SMTP)
- Web notifications
- Trade open/close alerts
- Stop loss / Take profit hits
- Daily/Weekly summaries
- Critical error alerts

### Analytics
- Performance reports (Win Rate, Profit Factor, Sharpe Ratio, Sortino Ratio)
- Drawdown analysis
- Trade journal
- Strategy comparison
- Time/Day analysis
- Equity curve visualization

### Commercial Features
- License key system
- Subscription plans (Free, Basic, Pro, Enterprise)
- User management
- Admin dashboard
- Affiliate tracking
- Usage analytics

## Tech Stack

### Backend
- Python 3.12
- FastAPI (async web framework)
- SQLAlchemy + asyncpg (PostgreSQL)
- Redis (caching, pub/sub)
- WebSockets (real-time data)
- CCXT (exchange integration)
- MetaTrader5 (forex integration)
- scikit-learn, XGBoost, LightGBM (AI)

### Frontend
- React 18 + TypeScript
- Tailwind CSS
- Zustand (state management)
- React Query (data fetching)
- Recharts (charts)
- Lucide React (icons)

### Infrastructure
- Docker + Docker Compose
- Nginx (reverse proxy, SSL)
- Prometheus + Grafana (monitoring)
- PostgreSQL 15
- Redis 7

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/quantum-scalper-pro.git
   cd quantum-scalper-pro
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Start the platform**
   ```bash
   docker-compose up -d
   ```

4. **Access the dashboard**
   - Web Dashboard: http://localhost
   - API Docs: http://localhost/docs
   - Prometheus: http://localhost:9090
   - Grafana: http://localhost:3001

### Default Credentials
- Email: `admin@quantumscalper.pro`
- Password: `Admin123!` (change immediately)

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `SECRET_KEY` | JWT secret key | `change-me-in-production` |
| `BINANCE_API_KEY` | Binance API key | - |
| `BINANCE_SECRET_KEY` | Binance secret key | - |
| `BINANCE_TESTNET` | Use testnet | `true` |
| `MT5_SERVER` | MT5 server path | - |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | - |
| `SMTP_HOST` | SMTP server | - |

### Broker Setup

#### Binance
1. Create API keys at [Binance](https://www.binance.com/en/my/settings/api-management)
2. Set `BINANCE_API_KEY` and `BINANCE_SECRET_KEY`
3. Use `BINANCE_TESTNET=true` for testing

#### MetaTrader 5
1. Install MT5 on your VPS
2. Set `MT5_SERVER`, `MT5_LOGIN`, `MT5_PASSWORD`
3. Ensure MT5 is running before connecting

## API Documentation

The API is documented using OpenAPI/Swagger. Access it at `/docs` when running in development mode.

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/login` | POST | User login |
| `/api/v1/auth/register` | POST | User registration |
| `/api/v1/trading/trades` | GET | List trades |
| `/api/v1/trading/start` | POST | Start trading engine |
| `/api/v1/trading/stop` | POST | Stop trading engine |
| `/api/v1/risk/profile` | GET/PUT | Risk profile |
| `/api/v1/analytics/performance` | GET | Performance metrics |
| `/api/v1/strategies/list` | GET | List strategies |

## Testing

```bash
# Run all tests
cd backend
pytest -v --cov=app

# Run specific test file
pytest tests/test_trading.py -v

# Run with coverage report
pytest --cov=app --cov-report=html
```

## Deployment

### Docker Compose (Recommended)
```bash
docker-compose up -d
```

### VPS Deployment
1. Provision a Linux VPS (Ubuntu 22.04 recommended)
2. Install Docker and Docker Compose
3. Clone the repository
4. Configure `.env`
5. Run `docker-compose up -d`
6. Configure Nginx with SSL (Let's Encrypt)

### Cloud Deployment
Supports AWS, GCP, Azure, DigitalOcean, and any Docker-compatible platform.

## Monitoring

- **Prometheus**: Metrics collection at `:9090`
- **Grafana**: Dashboards at `:3001` (default password: `admin`)
- **Application Logs**: `./logs/`
- **Trade Logs**: `./logs/trades.log`

## Backup & Restore

```bash
# Backup database
docker exec qsp-postgres pg_dump -U qsp_admin quantum_scalper_pro > backup.sql

# Restore database
docker exec -i qsp-postgres psql -U qsp_admin quantum_scalper_pro < backup.sql
```

## Security Considerations

1. **Never commit `.env` files** with real credentials
2. **Use strong `SECRET_KEY`** (min 32 chars in production)
3. **Enable 2FA** for admin accounts
4. **Use SSL/TLS** in production
5. **Restrict API access** with IP whitelisting
6. **Regular security audits** recommended
7. **Keep dependencies updated**

## License

Commercial License - See LICENSE.md for details.

## Support

- Documentation: [docs.quantumscalper.pro](https://docs.quantumscalper.pro)
- Support Email: support@quantumscalper.pro
- Telegram: [@QuantumScalperSupport](https://t.me/QuantumScalperSupport)

## Disclaimer

Trading involves substantial risk of loss. Past performance is not indicative of future results. Always use paper trading to validate strategies before live trading. Quantum Scalper Pro is a tool to assist traders, not a guarantee of profits.

---

**Built with care by the Quantum Scalper Pro Team**
