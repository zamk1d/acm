"""users + tiktok_accounts.user_id

Revision ID: 0002
Revises: 0001
Create Date: 2026-01-02 00:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    # Dev-stage shortcut: old rows have no owner, so they can't satisfy NOT NULL.
    op.execute("DELETE FROM tiktok_accounts")
    op.add_column("tiktok_accounts", sa.Column("user_id", sa.Uuid(), nullable=False))
    op.create_index(op.f("ix_tiktok_accounts_user_id"), "tiktok_accounts", ["user_id"])
    op.create_foreign_key(
        op.f("fk_tiktok_accounts_user_id_users"),
        "tiktok_accounts",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_tiktok_accounts_user_id_users"), "tiktok_accounts", type_="foreignkey")
    op.drop_index(op.f("ix_tiktok_accounts_user_id"), table_name="tiktok_accounts")
    op.drop_column("tiktok_accounts", "user_id")
    op.drop_table("users")