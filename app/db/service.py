"""Database service layer for invoice record and tenant persistence.

Provides CRUD operations for InvoiceRecord and Tenant models,
used by the API endpoints, CLI, and background workers.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InvoiceRecord, Tenant
from app.models.invoice import Invoice


def _hash_api_key(api_key: str) -> str:
    """Hash an API key for storage (SHA-256)."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _generate_api_key() -> str:
    """Generate a secure random API key."""
    return f"if_{secrets.token_urlsafe(32)}"


class TenantService:
    """Service for managing Tenant CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_tenant(
        self,
        name: str,
        slug: str,
        config: dict | None = None,
        api_key: str | None = None,
    ) -> tuple[Tenant, str]:
        """Mandant anlegen.

        Args:
            name: Anzeigename des Mandanten.
            slug: Eindeutiger URL-sicherer Bezeichner.
            config: Mandantenkonfiguration (JSON-Struktur).
            api_key: Optionaler API-Key (wird generiert wenn nicht angegeben).

        Returns:
            Tuple aus (Tenant-Objekt, klartext API-Key).
        """
        if api_key is None:
            api_key = _generate_api_key()

        tenant = Tenant(
            id=uuid.uuid4(),
            name=name,
            slug=slug,
            api_key_hash=_hash_api_key(api_key),
            config=json.dumps(config) if config else None,
            is_active=True,
        )
        self.session.add(tenant)
        await self.session.flush()
        return tenant, api_key

    async def get_tenant(self, tenant_id: uuid.UUID) -> Tenant | None:
        """Mandant per ID laden."""
        return await self.session.get(Tenant, tenant_id)

    async def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        """Mandant per Slug laden."""
        result = await self.session.execute(
            select(Tenant).where(Tenant.slug == slug)
        )
        return result.scalar_one_or_none()

    async def authenticate_by_api_key(self, api_key: str) -> Tenant | None:
        """Mandant über API-Key authentifizieren."""
        key_hash = _hash_api_key(api_key)
        result = await self.session.execute(
            select(Tenant).where(
                Tenant.api_key_hash == key_hash,
                Tenant.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def list_tenants(self, active_only: bool = True) -> list[Tenant]:
        """Alle Mandanten auflisten."""
        query = select(Tenant).order_by(Tenant.name)
        if active_only:
            query = query.where(Tenant.is_active == True)  # noqa: E712
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_tenant(
        self,
        tenant_id: uuid.UUID,
        name: str | None = None,
        config: dict | None = None,
        is_active: bool | None = None,
    ) -> Tenant | None:
        """Mandant aktualisieren."""
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None:
            return None

        if name is not None:
            tenant.name = name
        if config is not None:
            tenant.config = json.dumps(config)
        if is_active is not None:
            tenant.is_active = is_active

        await self.session.flush()
        return tenant

    async def delete_tenant(self, tenant_id: uuid.UUID) -> bool:
        """Mandant deaktivieren (soft delete)."""
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None:
            return False
        tenant.is_active = False
        await self.session.flush()
        return True

    @staticmethod
    def get_tenant_config(tenant: Tenant) -> dict:
        """Parse tenant configuration JSON."""
        if tenant.config:
            return json.loads(tenant.config)
        return {}

    @staticmethod
    def get_tenant_company(tenant: Tenant) -> dict:
        """Firmenstammdaten des Mandanten."""
        config = TenantService.get_tenant_config(tenant)
        return config.get("company", {})

    @staticmethod
    def get_tenant_nextcloud(tenant: Tenant) -> dict:
        """Nextcloud-Konfiguration des Mandanten."""
        config = TenantService.get_tenant_config(tenant)
        return config.get("nextcloud", {})

    @staticmethod
    def get_tenant_defaults(tenant: Tenant) -> dict:
        """Standard-Einstellungen des Mandanten."""
        config = TenantService.get_tenant_config(tenant)
        return config.get("defaults", {})


class InvoiceService:
    """Service for managing InvoiceRecord persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_record(
        self,
        invoice: Invoice,
        tenant_id: uuid.UUID | str,
        input_file_path: str | None = None,
    ) -> InvoiceRecord:
        """Create a new invoice processing record."""
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id) if tenant_id != "default" else uuid.UUID(int=0)

        record = InvoiceRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            invoice_number=invoice.invoice_number,
            invoice_date=datetime.combine(
                invoice.invoice_date, datetime.min.time(), tzinfo=timezone.utc
            ),
            seller_name=invoice.seller.name,
            buyer_name=invoice.buyer.name,
            currency=invoice.currency_code.value,
            net_amount=float(invoice.totals.net_amount),
            gross_amount=float(invoice.totals.gross_amount),
            output_format=invoice.output_format.value,
            zugferd_profile=invoice.profile.value,
            invoice_data_json=invoice.model_dump_json(),
            input_file_path=input_file_path,
            status="pending",
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def update_status(
        self,
        record_id: uuid.UUID,
        status: str,
        error_message: str | None = None,
        output_file_path: str | None = None,
        is_valid: bool | None = None,
        validation_report: str | None = None,
    ) -> InvoiceRecord | None:
        """Update the processing status of an invoice record."""
        record = await self.session.get(InvoiceRecord, record_id)
        if record is None:
            return None

        record.status = status
        if error_message is not None:
            record.error_message = error_message
        if output_file_path is not None:
            record.output_file_path = output_file_path
        if is_valid is not None:
            record.is_valid = is_valid
        if validation_report is not None:
            record.validation_report = validation_report

        await self.session.flush()
        return record

    async def get_record(self, record_id: uuid.UUID) -> InvoiceRecord | None:
        """Get a single invoice record by ID."""
        return await self.session.get(InvoiceRecord, record_id)

    async def list_records(
        self,
        tenant_id: uuid.UUID | str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[InvoiceRecord]:
        """List invoice records for a tenant, newest first."""
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id) if tenant_id != "default" else uuid.UUID(int=0)

        result = await self.session.execute(
            select(InvoiceRecord)
            .where(InvoiceRecord.tenant_id == tenant_id)
            .order_by(InvoiceRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_invoice_data(self, record_id: uuid.UUID) -> Invoice | None:
        """Retrieve the stored Invoice model from a record."""
        record = await self.session.get(InvoiceRecord, record_id)
        if record is None or record.invoice_data_json is None:
            return None
        return Invoice.model_validate_json(record.invoice_data_json)
