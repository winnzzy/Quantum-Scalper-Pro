"""Create the initial Quantum Scalper Pro schema.

Revision ID: 20260901_0001
Revises:
Create Date: 2026-09-01
"""
from typing import Sequence, Union

from alembic import op

from app.core.database import Base
from app import models  # noqa: F401 - populate Base.metadata


revision: str = "20260901_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create every table registered by the application models."""
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    """Drop the initial schema in reverse dependency order."""
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
