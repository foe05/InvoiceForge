"""Client for the KoSIT Validator Docker sidecar (HTTP API).

The KoSIT Validator runs as a separate container and provides full
Schematron-based validation for XRechnung and ZUGFeRD documents.

The validator accepts XML via POST and returns an SVRL/KoSIT report.
Report format: https://github.com/itplr-kosit/validator
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
from lxml import etree

from app.config import settings

# KoSIT report namespaces
_REPORT_NS = {
    "rep": "http://www.xoev.de/de/validator/varl/1",
    "s": "http://purl.oclc.org/dml/svrl",
    "svrl": "http://purl.oclc.org/dml/svrl",
}


@dataclass
class KoSITResult:
    """Result from KoSIT Validator."""

    is_valid: bool
    recommendation: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_report: str = ""


class KoSITClient:
    """HTTP client for the KoSIT Validator sidecar service.

    The KoSIT Validator can run in daemon mode (HTTP server) or be called via
    subprocess. This client uses the HTTP API.

    Docker Compose service example:
        kosit-validator:
            image: eclipse-temurin:21-jre-alpine
            command: java -jar validationtool-daemon.jar -s xrechnung_3.0.2-scenarios.xml
            ports:
                - "8080:8080"
    """

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
            except httpx.ConnectError:
                return KoSITResult(
                    is_valid=False,
                    recommendation="unavailable",
                    errors=["KoSIT Validator not reachable. Is the Docker sidecar running?"],
                )
            except httpx.HTTPError as e:
                return KoSITResult(
                    is_valid=False,
                    recommendation="error",
                    errors=[f"KoSIT Validator error: {e}"],
                )

        report_xml = response.text
        return self._parse_report(report_xml)

    async def is_available(self) -> bool:
        """Check if the KoSIT Validator sidecar is reachable."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(self.base_url)
                return resp.status_code < 500
            except httpx.HTTPError:
                return False

    def _parse_report(self, report_xml: str) -> KoSITResult:
        """Parse the KoSIT Validator XML report into a structured result.

        The KoSIT report follows this structure:
        <rep:report>
          <rep:assessment>
            <rep:accept/> or <rep:reject/>
          </rep:assessment>
          ... SVRL results with failed-assert / successful-report elements
        </rep:report>
        """
        errors: list[str] = []
        warnings: list[str] = []
        recommendation = ""
        is_valid = False

        try:
            root = etree.fromstring(report_xml.encode("utf-8"))
        except etree.XMLSyntaxError:
            # Fallback: simple text matching
            is_valid = "acceptable" in report_xml.lower() or "accept" in report_xml.lower()
            return KoSITResult(
                is_valid=is_valid,
                raw_report=report_xml,
                errors=["Could not parse KoSIT report XML"] if not is_valid else [],
            )

        # Check assessment element
        accept = root.find(".//rep:assessment/rep:accept", _REPORT_NS)
        reject = root.find(".//rep:assessment/rep:reject", _REPORT_NS)

        if accept is not None:
            is_valid = True
            recommendation = "accept"
        elif reject is not None:
            is_valid = False
            recommendation = "reject"
        else:
            # Try alternative: look for "acceptable" recommendation attribute
            assessment = root.find(".//rep:assessment", _REPORT_NS)
            if assessment is not None:
                rec = assessment.get("recommendation", "")
                recommendation = rec
                is_valid = rec.lower() in ("accept", "acceptable")

        # Extract SVRL failed assertions (errors)
        for failed in root.iter("{http://purl.oclc.org/dml/svrl}failed-assert"):
            text_el = failed.find("{http://purl.oclc.org/dml/svrl}text")
            location = failed.get("location", "")
            flag = failed.get("flag", "error")
            message = text_el.text.strip() if text_el is not None and text_el.text else ""

            if message:
                entry = f"[{flag}] {message}"
                if location:
                    entry += f" (at {location})"

                if flag in ("fatal", "error"):
                    errors.append(entry)
                else:
                    warnings.append(entry)

        # Extract SVRL successful reports (informational)
        for report in root.iter("{http://purl.oclc.org/dml/svrl}successful-report"):
            text_el = report.find("{http://purl.oclc.org/dml/svrl}text")
            flag = report.get("flag", "info")
            message = text_el.text.strip() if text_el is not None and text_el.text else ""
            if message and flag == "warning":
                warnings.append(f"[warning] {message}")

        return KoSITResult(
            is_valid=is_valid,
            recommendation=recommendation,
            errors=errors,
            warnings=warnings,
            raw_report=report_xml,
        )
