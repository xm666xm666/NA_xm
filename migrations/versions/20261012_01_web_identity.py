"""initial website identity and operational metadata tables."""

from alembic import op

from webapp.identity import Base

revision = "20261012_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 初始版本以 SQLAlchemy 元数据创建，后续变更应使用显式 Alembic 迁移。
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
