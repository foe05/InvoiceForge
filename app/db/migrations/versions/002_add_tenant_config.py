"""Add config column to tenants table.

The Tenant SQLAlchemy model declared `config: Text NULL` from the start,
but migration 001 omitted the column — every tenant insert via the ORM
crashed with `column "config" of relation "tenants" does not exist`.

Revision ID: 002
Revises: 001
Create Date: 2026-04-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("config", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "config")
