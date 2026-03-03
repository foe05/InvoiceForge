"""API v1 router – aggregates all endpoint modules."""

from fastapi import APIRouter

from app.api.v1 import invoices

api_router = APIRouter()

api_router.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
