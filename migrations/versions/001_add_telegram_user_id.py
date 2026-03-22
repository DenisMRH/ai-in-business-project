"""Добавление telegram_user_id в users.

Revision ID: 001
Revises:
Create Date: 2025-03-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001_telegram"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_users_telegram_user_id",
        "users",
        ["telegram_user_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_telegram_user_id", "users", type_="unique")
    op.drop_column("users", "telegram_user_id")
