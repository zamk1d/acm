"""create tiktok_accounts

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tiktok_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("open_id", sa.String(length=128), nullable=False),
        sa.Column("union_id", sa.String(length=128), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tiktok_accounts")),
        sa.UniqueConstraint("open_id", name=op.f("uq_tiktok_accounts_open_id")),
    )


def downgrade() -> None:
    op.drop_table("tiktok_accounts")
