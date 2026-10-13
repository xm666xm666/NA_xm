"""set the default module and derive user/admin roles from permissions.

Revision ID: 20261013_02
Revises: 20261013_01
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "20261013_02"
down_revision = "20261013_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    users = sa.table(
        "web_users",
        sa.column("id", sa.Integer()),
        sa.column("role", sa.String()),
        sa.column("features_json", sa.Text()),
    )
    rows = connection.execute(sa.select(users.c.id, users.c.role, users.c.features_json)).mappings()
    for row in rows:
        role = str(row["role"] or "user")
        try:
            features = json.loads(row["features_json"] or "[]")
        except (TypeError, ValueError):
            features = []
        if not isinstance(features, list):
            features = []
        features = sorted({str(value) for value in features if str(value) in {
            "workspace", "extraction", "batch", "data_summary", "upstream",
            "upstream_bill", "overview", "agent",
        }})
        if not features and role != "superadmin":
            features = ["extraction"]
        if role != "superadmin":
            role = "admin" if set(features) - {"extraction"} else "user"
        connection.execute(
            users.update().where(users.c.id == row["id"]).values(
                role=role,
                features_json=json.dumps(features, ensure_ascii=False),
            )
        )


def downgrade() -> None:
    # Permission grants are retained; role labels can no longer be reliably
    # reconstructed into the former role-based access matrix.
    pass
