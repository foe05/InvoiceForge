"""Initial schema – tenants and invoices tables.

Revision ID: 001
Revises: None
Create Date: 2026-03-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tenants table
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("api_key_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # Invoice status enum
    invoice_status = postgresql.ENUM(
        "pending",
        "extracting",
        "extracted",
        "generating",
        "validating",
        "completed",
        "failed",
        name="invoice_status",
        create_type=True,
    )
    invoice_status.create(op.get_bind(), checkfirst=True)

    # Invoices table
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("invoice_number", sa.String(255), nullable=False),
        sa.Column("invoice_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seller_name", sa.String(255), nullable=False),
        sa.Column("buyer_name", sa.String(255), nullable=False),
        sa.Column("currency", sa.String(3), server_default="EUR"),
        sa.Column("net_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("gross_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "status",
            invoice_status,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_file_path", sa.String(500), nullable=True),
        sa.Column("output_file_path", sa.String(500), nullable=True),
        sa.Column("output_format", sa.String(50), server_default="zugferd_pdf"),
        sa.Column("zugferd_profile", sa.String(50), server_default="EN 16931"),
        sa.Column("invoice_data_json", sa.Text(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=True),
        sa.Column("validation_report", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # Indexes for common queries
    op.create_index(
        "ix_invoices_tenant_id", "invoices", ["tenant_id"]
    )
    op.create_index(
        "ix_invoices_created_at", "invoices", ["created_at"]
    )
    op.create_index(
        "ix_invoices_invoice_number", "invoices", ["invoice_number"]
    )


def downgrade() -> None:
    op.drop_index("ix_invoices_invoice_number")
    op.drop_index("ix_invoices_created_at")
    op.drop_index("ix_invoices_tenant_id")
    op.drop_table("invoices")

    # Drop enum type
    invoice_status = postgresql.ENUM(name="invoice_status")
    invoice_status.drop(op.get_bind(), checkfirst=True)

    op.drop_table("tenants")
