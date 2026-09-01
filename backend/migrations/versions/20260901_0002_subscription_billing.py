"""Add subscription, billing, device, and usage tables.

Revision ID: 20260901_0002
Revises: 20260901_0001
Create Date: 2026-09-01
"""
from typing import Sequence, Union

from alembic import op

from app.core.database import Base
from app.models import subscription  # noqa: F401 - register billing tables


revision: str = "20260901_0002"
down_revision: Union[str, None] = "20260901_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = (
    "subscription_plans",
    "customer_subscriptions",
    "payments",
    "devices",
    "license_activations",
    "webhook_events",
    "usage_records",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)
