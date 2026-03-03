"""Client for the KoSIT Validator Docker sidecar (HTTP API).

The KoSIT Validator runs as a separate container and provides full
Schematron-based validation for XRechnung and ZUGFeRD documents.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.config import settings


@dataclass
class KoSITResult:
    """Result from KoSIT Validator."""

    is_valid: bool
    recommendation: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_report: str = ""


class KoSITClient:
    """HTTP client for the KoSIT Validator sidecar service."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or settings.kosit_validator_url

    async def validate(self, xml_bytes: bytes) -> KoSITResult:
        """Send XML to the KoSIT Validator for full Schematron validation.

        Args:
            xml_bytes: The CII or UBL XML to validate.

        Returns:
            KoSITResult with validation outcome.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    self.base_url,
                    content=xml_bytes,
                    headers={"Content-Type": "application/xml"},
                )
                response.raise_for_status()
            except httpx.HTTPError as e:
                return KoSITResult(
                    is_valid=False,
                    errors=[f"KoSIT Validator unavailable: {e}"],
                )

        # Parse KoSIT report XML
        report_xml = response.text
        # TODO: Parse the KoSIT report XML to extract structured results
        # The report follows the KoSIT report format with
        # <rep:report> / <rep:assessment> elements

        is_valid = "acceptable" in report_xml.lower()
        return KoSITResult(
            is_valid=is_valid,
            raw_report=report_xml,
        )
