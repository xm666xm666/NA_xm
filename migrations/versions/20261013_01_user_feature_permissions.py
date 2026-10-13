"""store feature permissions per website user.

Revision ID: 20261013_01
Revises: 20261012_02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261013_01"
down_revision = "20261012_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("web_users")}
    if "features_json" in columns:
        return
    # Existing accounts start with no feature grants. A superadmin assigns access
    # explicitly from the user management page after deployment.
    op.add_column(
        "web_users",
        sa.Column("features_json", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("web_users")}
    if "features_json" in columns:
        op.drop_column("web_users", "features_json")
