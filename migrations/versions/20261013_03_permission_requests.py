"""store in-app permission requests for superadmin review.

Revision ID: 20261013_03
Revises: 20261013_02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261013_03"
down_revision = "20261013_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("web_permission_requests"):
        return
    op.create_table(
        "web_permission_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("requested_features_json", sa.Text(), nullable=False),
        sa.Column("approved_features_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("reviewer_note", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["web_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["web_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_web_permission_requests_user_id", "web_permission_requests", ["user_id"], unique=False)
    op.create_index("ix_web_permission_requests_status", "web_permission_requests", ["status"], unique=False)


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("web_permission_requests"):
        return
    op.drop_index("ix_web_permission_requests_status", table_name="web_permission_requests")
    op.drop_index("ix_web_permission_requests_user_id", table_name="web_permission_requests")
    op.drop_table("web_permission_requests")
