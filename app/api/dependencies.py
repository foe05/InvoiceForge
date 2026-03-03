"""FastAPI dependencies for authentication, tenant resolution, and DB sessions."""

from __future__ import annotations

import hashlib
import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Tenant
from app.db.session import get_session


def _hash_api_key(key: str) -> str:
    """Hash an API key for comparison against stored hashes."""
    return hashlib.sha256(key.encode()).hexdigest()


async def get_db(session: AsyncSession = Depends(get_session)) -> AsyncSession:
    """Yield an async database session."""
    return session


async def get_current_tenant(
    x_api_key: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> Tenant | None:
    """Resolve the current tenant from the X-API-Key header.

    In development mode, returns None (no tenant required).
    In production, requires a valid API key.
    """
    if settings.is_development and not x_api_key:
        return None

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    key_hash = _hash_api_key(x_api_key)
    result = await session.execute(
        select(Tenant).where(Tenant.api_key_hash == key_hash, Tenant.is_active == True)
    )
    tenant = result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return tenant


def get_tenant_id(tenant: Tenant | None = Depends(get_current_tenant)) -> str:
    """Get tenant ID string, defaulting to 'default' in dev mode."""
    if tenant is None:
        return "default"
    return str(tenant.id)


async def create_tenant(
    session: AsyncSession,
    name: str,
    slug: str,
    api_key: str,
) -> Tenant:
    """Create a new tenant with a hashed API key."""
    tenant = Tenant(
        id=uuid.uuid4(),
        name=name,
        slug=slug,
        api_key_hash=_hash_api_key(api_key),
        is_active=True,
    )
    session.add(tenant)
    await session.flush()
    return tenant
