"""Broker factory for creating broker instances."""
from app.brokers.base import BaseBroker, BrokerConfig
from app.brokers.binance import BinanceBroker
from app.brokers.mt5 import MT5Broker
from app.brokers.paper import PaperBroker
from app.core.config import settings
from app.core.logging import logger


class BrokerFactory:
    """Factory for creating broker instances."""

    _brokers: dict[str, BaseBroker] = {}

    @classmethod
    async def get_broker(cls, broker_type: str, user_id: int | None = None) -> BaseBroker:
        """Get or create broker instance."""
        cache_key = f"{broker_type}_{user_id}"

        if cache_key in cls._brokers:
            broker = cls._brokers[cache_key]
            if broker.is_connected:
                healthy = await broker.health_check()
                if healthy:
                    return broker
                logger.warning(f"Broker instance unhealthy, reconnecting: {cache_key}")
            await broker.disconnect()

        config = cls._create_config(broker_type)

        if broker_type == "binance_spot":
            broker = BinanceBroker(config)
        elif broker_type == "binance_futures":
            config.testnet = False
            broker = BinanceBroker(config)
        elif broker_type == "binance_testnet":
            config.testnet = True
            broker = BinanceBroker(config)
        elif broker_type == "mt5":
            broker = MT5Broker(config)
        elif broker_type == "paper":
            broker = PaperBroker(config)
        else:
            raise ValueError(f"Unknown broker type: {broker_type}")

        cls._brokers[cache_key] = broker
        await broker.connect()
        return broker

    @classmethod
    def _create_config(cls, broker_type: str) -> BrokerConfig:
        """Create broker configuration."""
        if "binance" in broker_type:
            return BrokerConfig(
                api_key=settings.BINANCE_API_KEY,
                secret_key=settings.BINANCE_SECRET_KEY,
                testnet=settings.BINANCE_TESTNET,
            )
        elif broker_type == "mt5":
            return BrokerConfig(
                server=settings.MT5_SERVER,
                login=settings.MT5_LOGIN,
                password=settings.MT5_PASSWORD,
                path=settings.MT5_PATH,
            )
        else:
            return BrokerConfig()

    @classmethod
    async def disconnect_all(cls):
        """Disconnect all brokers."""
        for key, broker in list(cls._brokers.items()):
            try:
                await broker.disconnect()
                logger.info(f"Disconnected broker: {key}")
            except Exception as e:
                logger.error(f"Error disconnecting {key}: {e}")
        cls._brokers.clear()
