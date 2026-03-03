"""SQLAlchemy ORM models for persistent storage."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class Tenant(Base):
    """Multi-tenant support – each tenant has isolated data.

    Jeder Mandant hat eigene:
      - Stammdaten (Firmenname, Adresse, Steuernummer, IBAN etc.)
      - Nextcloud-Zugangsdaten (optional: eigene Instanz)
      - Standard-Ausgabeformat (ZUGFeRD/XRechnung)
      - Standard-ZUGFeRD-Profil

    Die Konfiguration wird als JSON in der `config` Spalte gespeichert.
    """

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Tenant-specific configuration (JSON blob)
    # Structure:
    # {
    #   "company": {
    #     "name": "Muster GmbH",
    #     "street": "Musterstr. 1",
    #     "city": "Berlin",
    #     "postal_code": "10115",
    #     "country_code": "DE",
    #     "vat_id": "DE123456789",
    #     "tax_number": "30/123/45678",
    #     "iban": "DE89370400440532013000",
    #     "bic": "COBADEFFXXX",
    #     "email": "rechnung@muster.de",
    #     "phone": "+49 30 123456",
    #     "contact_name": "Max Mustermann"
    #   },
    #   "nextcloud": {
    #     "url": "https://cloud.example.com/remote.php/dav/files/user/",
    #     "username": "user",
    #     "password": "app-password",
    #     "root_path": "/InvoiceForge"
    #   },
    #   "defaults": {
    #     "output_format": "zugferd_pdf",
    #     "zugferd_profile": "EN 16931"
    #   }
    # }
    config: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    invoices: Mapped[list["InvoiceRecord"]] = relationship(back_populates="tenant")


class InvoiceRecord(Base):
    """Persisted invoice processing record."""

    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )

    # Invoice metadata
    invoice_number: Mapped[str] = mapped_column(String(255), nullable=False)
    invoice_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    seller_name: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    net_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    gross_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # Processing status
    status: Mapped[str] = mapped_column(
        Enum(
            "pending", "extracting", "extracted", "generating",
            "validating", "completed", "failed",
            name="invoice_status",
        ),
        default="pending",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # File references
    input_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    output_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    output_format: Mapped[str] = mapped_column(String(50), default="zugferd_pdf")
    zugferd_profile: Mapped[str] = mapped_column(String(50), default="EN 16931")

    # Invoice data (JSON blob for flexibility)
    invoice_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Validation
    is_valid: Mapped[bool | None] = mapped_column(nullable=True)
    validation_report: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="invoices")
