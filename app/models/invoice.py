"""Pydantic models for invoice data based on EN 16931 semantic model.

Field references (BT-xx / BG-xx) follow the EN 16931 Business Term numbering.
"""

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class InvoiceTypeCode(str, Enum):
    """UNTDID 1001 subset – common invoice type codes."""

    INVOICE = "380"
    CREDIT_NOTE = "381"
    CORRECTED_INVOICE = "384"
    SELF_BILLED_INVOICE = "389"


class CurrencyCode(str, Enum):
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"
    CHF = "CHF"


class ZUGFeRDProfile(str, Enum):
    MINIMUM = "MINIMUM"
    BASIC_WL = "BASIC WL"
    BASIC = "BASIC"
    EN16931 = "EN 16931"
    EXTENDED = "EXTENDED"
    XRECHNUNG = "XRECHNUNG"


class OutputFormat(str, Enum):
    ZUGFERD_PDF = "zugferd_pdf"
    XRECHNUNG_CII = "xrechnung_cii"
    XRECHNUNG_UBL = "xrechnung_ubl"


# --- BG-5: Seller postal address / BG-8: Buyer postal address ---


class Address(BaseModel):
    """Postal address (BG-5 / BG-8)."""

    street: str = Field(..., description="BT-35 / BT-50: Street name + number")
    additional_line: str | None = Field(None, description="BT-36 / BT-51: Additional line")
    city: str = Field(..., description="BT-37 / BT-52: City")
    postal_code: str = Field(..., description="BT-38 / BT-53: Post code")
    country_code: str = Field("DE", description="BT-40 / BT-55: Country code (ISO 3166-1 alpha-2)")
    country_subdivision: str | None = Field(
        None, description="BT-39 / BT-54: Country subdivision (e.g. Bundesland)"
    )


# --- BG-4: Seller / BG-7: Buyer ---


class InvoiceParty(BaseModel):
    """Invoice party – Seller (BG-4) or Buyer (BG-7)."""

    name: str = Field(..., description="BT-27 / BT-44: Party name")
    address: Address
    vat_id: str | None = Field(None, description="BT-31 / BT-48: VAT identifier (USt-IdNr.)")
    tax_number: str | None = Field(None, description="BT-32: Seller tax registration (Steuernummer)")
    registration_name: str | None = Field(
        None, description="BT-28 / BT-45: Trading / registration name"
    )
    electronic_address: str | None = Field(
        None, description="BT-34 / BT-49: Electronic address (e-mail)"
    )
    electronic_address_scheme: str = Field(
        "EM", description="BT-34-1 / BT-49-1: Electronic address scheme (EM=email)"
    )
    contact_name: str | None = Field(None, description="BT-41 / BT-56: Contact point name")
    contact_phone: str | None = Field(None, description="BT-42 / BT-57: Contact phone")
    contact_email: str | None = Field(None, description="BT-43 / BT-58: Contact email")


# --- BG-20: Payment terms ---


class PaymentTerms(BaseModel):
    """Payment terms (BG-16 / BT-20)."""

    description: str | None = Field(None, description="BT-20: Payment terms text")
    due_date: date | None = Field(None, description="BT-9: Payment due date")
    payment_means_code: str = Field("58", description="BT-81: Payment means code (58=SEPA)")
    iban: str | None = Field(None, description="BT-84: IBAN")
    bic: str | None = Field(None, description="BT-86: BIC")
    bank_name: str | None = Field(None, description="BT-85: Payment account name")
    payment_reference: str | None = Field(
        None, description="BT-83: Remittance information (Verwendungszweck)"
    )


# --- BG-23: VAT breakdown ---


class TaxBreakdown(BaseModel):
    """VAT breakdown line (BG-23)."""

    tax_category: str = Field("S", description="BT-118: VAT category code (S=standard)")
    tax_rate: Decimal = Field(..., description="BT-119: VAT rate in percent")
    taxable_amount: Decimal = Field(..., description="BT-116: Sum of net amounts for this rate")
    tax_amount: Decimal = Field(..., description="BT-117: VAT amount for this rate")


# --- BG-25: Invoice line ---


class InvoiceLine(BaseModel):
    """Single invoice line item (BG-25)."""

    line_id: str = Field(..., description="BT-126: Invoice line identifier")
    description: str = Field(..., description="BT-153: Item name")
    quantity: Decimal = Field(..., description="BT-129: Invoiced quantity")
    unit_code: str = Field("C62", description="BT-130: Unit of measure (UN/ECE Rec 20)")
    unit_price: Decimal = Field(..., description="BT-146: Item net price")
    line_net_amount: Decimal = Field(..., description="BT-131: Invoice line net amount")
    tax_category: str = Field("S", description="BT-151: Line VAT category code")
    tax_rate: Decimal = Field(..., description="BT-152: Line VAT rate in percent")
    item_number: str | None = Field(None, description="BT-155: Item Seller's identifier")
    buyer_reference: str | None = Field(None, description="BT-156: Item Buyer's identifier")


# --- BG-22: Document totals ---


class InvoiceTotals(BaseModel):
    """Invoice document totals (BG-22)."""

    net_amount: Decimal = Field(..., description="BT-106: Sum of Invoice line net amounts")
    tax_amount: Decimal = Field(..., description="BT-110: Invoice total VAT amount")
    gross_amount: Decimal = Field(
        ..., description="BT-112: Invoice total with VAT"
    )
    prepaid_amount: Decimal = Field(Decimal("0.00"), description="BT-113: Paid amount")
    due_amount: Decimal = Field(..., description="BT-115: Amount due for payment")
    allowance_total: Decimal = Field(
        Decimal("0.00"), description="BT-107: Sum of allowances on document level"
    )
    charge_total: Decimal = Field(
        Decimal("0.00"), description="BT-108: Sum of charges on document level"
    )


# --- Top-level invoice ---


class Invoice(BaseModel):
    """Complete invoice model following EN 16931.

    This is the central data structure for InvoiceForge. All processing
    (extraction, generation, validation) operates on this model.
    """

    # --- Document level ---
    invoice_number: str = Field(..., description="BT-1: Invoice number")
    invoice_date: date = Field(..., description="BT-2: Invoice issue date")
    invoice_type_code: InvoiceTypeCode = Field(
        InvoiceTypeCode.INVOICE, description="BT-3: Invoice type code"
    )
    currency_code: CurrencyCode = Field(CurrencyCode.EUR, description="BT-5: Invoice currency")
    buyer_reference: str = Field(
        "-", description="BT-10: Buyer reference (Leitweg-ID for B2G, '-' for B2B)"
    )
    order_reference: str | None = Field(None, description="BT-13: Purchase order reference")
    note: str | None = Field(None, description="BT-22: Invoice note")

    # Business process type (required for XRechnung / PEPPOL)
    business_process: str = Field(
        "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0",
        description="BT-23: Business process type",
    )

    # --- Parties ---
    seller: InvoiceParty = Field(..., description="BG-4: Seller information")
    buyer: InvoiceParty = Field(..., description="BG-7: Buyer information")

    # --- Lines ---
    lines: list[InvoiceLine] = Field(..., min_length=1, description="BG-25: Invoice lines")

    # --- Totals ---
    totals: InvoiceTotals = Field(..., description="BG-22: Document totals")
    tax_breakdown: list[TaxBreakdown] = Field(
        ..., min_length=1, description="BG-23: VAT breakdown"
    )

    # --- Payment ---
    payment: PaymentTerms = Field(default_factory=PaymentTerms, description="BG-16: Payment terms")

    # --- Output control ---
    profile: ZUGFeRDProfile = Field(
        ZUGFeRDProfile.EN16931, description="Target ZUGFeRD profile"
    )
    output_format: OutputFormat = Field(
        OutputFormat.ZUGFERD_PDF, description="Desired output format"
    )
