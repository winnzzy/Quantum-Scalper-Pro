"""Regression tests for complete SQLAlchemy model registration."""
from sqlalchemy import create_engine, inspect

from app.core.database import Base
import app.models  # noqa: F401 - registers every model on Base.metadata


def test_all_models_create_and_trade_index_targets_entry_time():
    engine = create_engine("sqlite:///:memory:")

    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    trade_indexes = {
        index["name"]: index["column_names"]
        for index in inspector.get_indexes("trades")
    }

    assert table_names == set(Base.metadata.tables)
    assert trade_indexes["idx_trade_opened"] == ["entry_time"]
