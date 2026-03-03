"""LLM-based intelligent invoice data extraction.

Uses Claude (Anthropic API) or Ollama for semantic field extraction from
unstructured PDF text/tables. This is the "brain" that converts raw extracted
text into structured Invoice data following EN 16931.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal

from app.config import LLMProvider, settings
from app.models.invoice import (
    Address,
    CurrencyCode,
    Invoice,
    InvoiceLine,
    InvoiceParty,
    InvoiceTotals,
    PaymentTerms,
    TaxBreakdown,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Du bist ein Experte für deutsche Rechnungsverarbeitung (E-Rechnung, EN 16931).
Deine Aufgabe: Extrahiere alle relevanten Rechnungsdaten aus dem Text und gib sie als JSON zurück.

Antworte AUSSCHLIESSLICH mit einem validen JSON-Objekt (kein Markdown, kein Text davor/danach).
Das JSON muss exakt dieses Schema haben:

{
  "invoice_number": "string (BT-1: Rechnungsnummer)",
  "invoice_date": "YYYY-MM-DD (BT-2: Rechnungsdatum)",
  "invoice_type_code": "380 | 381 | 384 | 389",
  "currency_code": "EUR | USD | GBP | CHF",
  "buyer_reference": "string (BT-10: Leitweg-ID bei B2G, sonst '-')",
  "note": "string oder null",
  "seller": {
    "name": "string (BT-27: Verkäufername)",
    "street": "string (BT-35: Straße + Hausnummer)",
    "city": "string (BT-37: Stadt)",
    "postal_code": "string (BT-38: PLZ)",
    "country_code": "DE",
    "vat_id": "string oder null (BT-31: USt-IdNr.)",
    "tax_number": "string oder null (BT-32: Steuernummer)",
    "electronic_address": "string oder null (BT-34: E-Mail)",
    "contact_name": "string oder null",
    "contact_phone": "string oder null",
    "contact_email": "string oder null"
  },
  "buyer": {
    "name": "string (BT-44: Käufername)",
    "street": "string (BT-50: Straße)",
    "city": "string (BT-52: Stadt)",
    "postal_code": "string (BT-53: PLZ)",
    "country_code": "DE",
    "vat_id": "string oder null (BT-48: USt-IdNr.)",
    "electronic_address": "string oder null (BT-49: E-Mail)"
  },
  "lines": [
    {
      "line_id": "1",
      "description": "string (BT-153: Artikelname)",
      "quantity": "number (BT-129: Menge)",
      "unit_code": "C62 | HUR | KGM | MTR | LTR | ...",
      "unit_price": "number (BT-146: Einzelpreis netto)",
      "line_net_amount": "number (BT-131: Zeilennettobetrag)",
      "tax_rate": "number (BT-152: USt-Satz in Prozent)"
    }
  ],
  "totals": {
    "net_amount": "number (BT-106: Summe netto)",
    "tax_amount": "number (BT-110: USt-Betrag)",
    "gross_amount": "number (BT-112: Bruttobetrag)",
    "due_amount": "number (BT-115: Zahlbetrag)"
  },
  "tax_breakdown": [
    {
      "tax_rate": "number (Prozentsatz)",
      "taxable_amount": "number (Nettobetrag für diesen Satz)",
      "tax_amount": "number (USt-Betrag für diesen Satz)"
    }
  ],
  "payment": {
    "description": "string oder null (BT-20: Zahlungsbedingungen)",
    "due_date": "YYYY-MM-DD oder null (BT-9: Fälligkeitsdatum)",
    "payment_means_code": "58 (SEPA) | 30 (Überweisung) | ...",
    "iban": "string oder null (BT-84)",
    "bic": "string oder null (BT-86)",
    "bank_name": "string oder null",
    "payment_reference": "string oder null (BT-83: Verwendungszweck)"
  }
}

Regeln:
- Alle Beträge als Zahlen (nicht als Strings), Punkt als Dezimaltrenner.
- Deutsche Datumsformate (TT.MM.JJJJ) in ISO-Format (YYYY-MM-DD) konvertieren.
- Fehlende Felder mit sinnvollen Defaults füllen (z.B. tax_rate: 19 für DE).
- Bei Prozentsätzen: 19% -> 19, 7% -> 7 (nicht 0.19).
- unit_code: "Stk" / "Stück" -> "C62", "Std" / "Stunden" -> "HUR".
"""


class LLMExtractor:
    """Extract structured invoice data from raw text using an LLM."""

    def __init__(self) -> None:
        self.provider = settings.llm_provider

    async def extract(self, text: str, tables: list | None = None) -> Invoice:
        """Extract Invoice from raw PDF text and tables.

        Args:
            text: Extracted text from the PDF.
            tables: Optional list of extracted tables.

        Returns:
            Parsed Invoice model.

        Raises:
            ValueError: If extraction fails or LLM provider is not configured.
        """
        if self.provider == LLMProvider.NONE:
            raise ValueError(
                "No LLM provider configured. "
                "Set LLM_PROVIDER=anthropic or LLM_PROVIDER=ollama in .env"
            )

        prompt = self._build_prompt(text, tables)

        if self.provider == LLMProvider.ANTHROPIC:
            raw_json = await self._call_anthropic(prompt)
        elif self.provider == LLMProvider.OLLAMA:
            raw_json = await self._call_ollama(prompt)
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

        return self._parse_response(raw_json)

    def _build_prompt(self, text: str, tables: list | None = None) -> str:
        parts = [f"Extrahiere die Rechnungsdaten aus folgendem Text:\n\n---\n{text}\n---"]
        if tables:
            parts.append("\nExtrahierte Tabellen:")
            for i, table in enumerate(tables, 1):
                parts.append(f"\nTabelle {i}:")
                for row in table:
                    parts.append("  | " + " | ".join(str(c) if c else "" for c in row) + " |")
        return "\n".join(parts)

    async def _call_anthropic(self, prompt: str) -> str:
        """Call Claude via the Anthropic API."""
        import anthropic

        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    async def _call_ollama(self, prompt: str) -> str:
        """Call a local LLM via Ollama API."""
        import httpx

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": "llama3.1",
                    "system": _SYSTEM_PROMPT,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
            )
            response.raise_for_status()
            return response.json()["response"]

    def _parse_response(self, raw_json: str) -> Invoice:
        """Parse the LLM JSON response into an Invoice model."""
        # Strip any markdown code fences
        text = raw_json.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        data = json.loads(text)

        seller_data = data.get("seller", {})
        buyer_data = data.get("buyer", {})

        seller = InvoiceParty(
            name=seller_data.get("name", "Unknown"),
            address=Address(
                street=seller_data.get("street", "-"),
                city=seller_data.get("city", "-"),
                postal_code=seller_data.get("postal_code", "-"),
                country_code=seller_data.get("country_code", "DE"),
            ),
            vat_id=seller_data.get("vat_id"),
            tax_number=seller_data.get("tax_number"),
            electronic_address=seller_data.get("electronic_address"),
            contact_name=seller_data.get("contact_name"),
            contact_phone=seller_data.get("contact_phone"),
            contact_email=seller_data.get("contact_email"),
        )

        buyer = InvoiceParty(
            name=buyer_data.get("name", "Unknown"),
            address=Address(
                street=buyer_data.get("street", "-"),
                city=buyer_data.get("city", "-"),
                postal_code=buyer_data.get("postal_code", "-"),
                country_code=buyer_data.get("country_code", "DE"),
            ),
            vat_id=buyer_data.get("vat_id"),
            electronic_address=buyer_data.get("electronic_address"),
        )

        lines = []
        for i, line_data in enumerate(data.get("lines", []), start=1):
            lines.append(InvoiceLine(
                line_id=str(line_data.get("line_id", i)),
                description=line_data.get("description", "Item"),
                quantity=Decimal(str(line_data.get("quantity", 1))),
                unit_code=line_data.get("unit_code", "C62"),
                unit_price=Decimal(str(line_data.get("unit_price", 0))),
                line_net_amount=Decimal(str(line_data.get("line_net_amount", 0))),
                tax_rate=Decimal(str(line_data.get("tax_rate", 19))),
            ))

        totals_data = data.get("totals", {})
        totals = InvoiceTotals(
            net_amount=Decimal(str(totals_data.get("net_amount", 0))),
            tax_amount=Decimal(str(totals_data.get("tax_amount", 0))),
            gross_amount=Decimal(str(totals_data.get("gross_amount", 0))),
            due_amount=Decimal(str(totals_data.get("due_amount", totals_data.get("gross_amount", 0)))),
        )

        tax_breakdown = []
        for tb_data in data.get("tax_breakdown", []):
            tax_breakdown.append(TaxBreakdown(
                tax_rate=Decimal(str(tb_data.get("tax_rate", 19))),
                taxable_amount=Decimal(str(tb_data.get("taxable_amount", 0))),
                tax_amount=Decimal(str(tb_data.get("tax_amount", 0))),
            ))

        if not tax_breakdown:
            tax_breakdown.append(TaxBreakdown(
                tax_rate=Decimal("19"),
                taxable_amount=totals.net_amount,
                tax_amount=totals.tax_amount,
            ))

        payment_data = data.get("payment", {})
        from datetime import date as dt_date

        due_date_str = payment_data.get("due_date")
        due_date = None
        if due_date_str:
            try:
                due_date = dt_date.fromisoformat(due_date_str)
            except ValueError:
                pass

        payment = PaymentTerms(
            description=payment_data.get("description"),
            due_date=due_date,
            payment_means_code=str(payment_data.get("payment_means_code", "58")),
            iban=payment_data.get("iban"),
            bic=payment_data.get("bic"),
            bank_name=payment_data.get("bank_name"),
            payment_reference=payment_data.get("payment_reference"),
        )

        currency_str = data.get("currency_code", "EUR")
        try:
            currency = CurrencyCode(currency_str)
        except ValueError:
            currency = CurrencyCode.EUR

        invoice_date_str = data.get("invoice_date")
        invoice_date = dt_date.today()
        if invoice_date_str:
            try:
                invoice_date = dt_date.fromisoformat(invoice_date_str)
            except ValueError:
                pass

        return Invoice(
            invoice_number=data.get("invoice_number", "UNKNOWN"),
            invoice_date=invoice_date,
            currency_code=currency,
            buyer_reference=data.get("buyer_reference", "-"),
            note=data.get("note"),
            seller=seller,
            buyer=buyer,
            lines=lines,
            totals=totals,
            tax_breakdown=tax_breakdown,
            payment=payment,
        )
