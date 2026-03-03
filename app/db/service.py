"""Database service layer for invoice record persistence.

Provides CRUD operations for InvoiceRecord and Tenant models,
used by the API endpoints and background workers.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InvoiceRecord, Tenant
from app.models.invoice import Invoice


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
