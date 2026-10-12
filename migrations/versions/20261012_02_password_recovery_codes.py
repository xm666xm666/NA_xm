"""add password recovery verification-code storage.

Revision ID: 20261012_02
Revises: 20261012_01
"""

from alembic import op
import sqlalchemy as sa


revision = "20261012_02"
down_revision = "20261012_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 20261012_01 historically calls Base.metadata.create_all().  On a fresh
    # installation it may already see this model; on an existing deployment it
    # will not.  Keep both upgrade paths safe without rewriting an applied migration.
    if sa.inspect(op.get_bind()).has_table("web_password_recovery_codes"):
        return
    op.create_table(
        "web_password_recovery_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=512), nullable=False),
        sa.Column("failed_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["web_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_web_password_recovery_codes_user_id"),
    )
    op.create_index("ix_web_password_recovery_codes_user_id", "web_password_recovery_codes", ["user_id"], unique=False)


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("web_password_recovery_codes"):
        return
    op.drop_index("ix_web_password_recovery_codes_user_id", table_name="web_password_recovery_codes")
    op.drop_table("web_password_recovery_codes")
