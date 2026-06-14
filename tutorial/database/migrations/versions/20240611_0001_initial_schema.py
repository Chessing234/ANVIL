"""Initial schema: create all ORM tables (mirrors ``Base.metadata``)."""

from __future__ import annotations

from alembic import op

from database.models import Base

revision = "20240611_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
