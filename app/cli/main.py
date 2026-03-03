"""Command-line interface for InvoiceForge.

Usage:
    invoiceforge convert input.xml -o output.pdf --format zugferd_pdf
    invoiceforge convert input.pdf -o output.xml --format xrechnung_cii
    invoiceforge validate invoice.xml
    invoiceforge serve --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.models.invoice import OutputFormat, ZUGFeRDProfile


def cli() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="invoiceforge",
        description="InvoiceForge – German E-Rechnung converter",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- serve ---
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    serve_parser.add_argument("--port", type=int, default=8000, help="Bind port")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    # --- convert ---
    convert_parser = subparsers.add_parser(
        "convert", help="Convert an invoice file (XML/PDF/JSON)"
    )
    convert_parser.add_argument("input", help="Input file (XML, PDF, or JSON)")
    convert_parser.add_argument("-o", "--output", help="Output file path")
    convert_parser.add_argument(
        "--format",
        choices=["zugferd_pdf", "xrechnung_cii", "xrechnung_ubl"],
        default="zugferd_pdf",
        help="Output format (default: zugferd_pdf)",
    )
    convert_parser.add_argument(
        "--profile",
        choices=["MINIMUM", "BASIC WL", "BASIC", "EN 16931", "EXTENDED", "XRECHNUNG"],
        default="EN 16931",
        help="ZUGFeRD profile (default: EN 16931)",
    )

    # --- validate ---
    validate_parser = subparsers.add_parser("validate", help="Validate an E-Rechnung XML")
    validate_parser.add_argument("input", help="XML file to validate")

    # --- extract ---
    extract_parser = subparsers.add_parser(
        "extract", help="Extract invoice data from ZUGFeRD PDF or XRechnung XML"
    )
    extract_parser.add_argument("input", help="Input file (PDF or XML)")
    extract_parser.add_argument(
        "-o", "--output", help="Output JSON file (default: stdout)"
    )

    args = parser.parse_args()

    if args.command == "serve":
        _run_server(args)
    elif args.command == "convert":
        _run_convert(args)
    elif args.command == "validate":
        _run_validate(args)
    elif args.command == "extract":
        _run_extract(args)
    else:
        parser.print_help()
        sys.exit(1)


def _run_server(args: argparse.Namespace) -> None:
    """Start the Uvicorn server."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def _run_convert(args: argparse.Namespace) -> None:
    """Convert an invoice file."""
    from app.core.extraction.xml_extractor import XMLExtractor
    from app.core.pipeline import ConversionPipeline
    from app.models.invoice import Invoice

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Determine input format and load invoice
    suffix = input_path.suffix.lower()
    if suffix == ".json":
        # Direct JSON invoice data
        invoice = Invoice.model_validate_json(input_path.read_text())
    elif suffix in (".xml", ".pdf"):
        # Extract from existing e-invoice
        extractor = XMLExtractor()
        try:
            invoice = extractor.extract_from_file(input_path)
        except Exception as e:
            print(f"Error extracting from {input_path}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Error: Unsupported input format: {suffix}", file=sys.stderr)
        sys.exit(1)

    # Apply output format and profile
    invoice.output_format = OutputFormat(args.format)
    invoice.profile = ZUGFeRDProfile(args.profile)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        ext = ".pdf" if args.format == "zugferd_pdf" else ".xml"
        output_path = input_path.with_suffix(ext)

    # Run conversion
    pipeline = ConversionPipeline()
    result, out_path = pipeline.convert_to_file(invoice, output_path.parent)

    if not result.success:
        print(f"Conversion failed:", file=sys.stderr)
        for err in result.errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # Move to requested output path if different
    if out_path != output_path:
        out_path.rename(output_path)

    print(f"Generated: {output_path}")
    print(f"  Format: {invoice.output_format.value}")
    print(f"  Profile: {invoice.profile.value}")
    print(f"  Invoice: {invoice.invoice_number} ({invoice.invoice_date})")
    print(f"  Total: {invoice.totals.gross_amount} {invoice.currency_code.value}")


def _run_validate(args: argparse.Namespace) -> None:
    """Validate an E-Rechnung XML file."""
    from drafthorse.models.document import Document
    from lxml import etree

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    xml_bytes = input_path.read_bytes()

    # Step 1: Basic XML parsing
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as e:
        print(f"INVALID: XML parse error: {e}", file=sys.stderr)
        sys.exit(1)

    # Step 2: XSD validation via drafthorse
    try:
        doc = Document()
        doc.parse(root)
        doc.serialize(schema="FACTUR-X_EN16931")
    except Exception as e:
        print(f"INVALID: XSD validation failed: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"VALID: {input_path} passes XSD validation (EN 16931)")
    print("Note: Full Schematron validation requires the KoSIT Validator (Docker sidecar)")


def _run_extract(args: argparse.Namespace) -> None:
    """Extract invoice data to JSON."""
    from app.core.extraction.xml_extractor import XMLExtractor

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    extractor = XMLExtractor()
    try:
        invoice = extractor.extract_from_file(input_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    json_str = invoice.model_dump_json(indent=2)

    if args.output:
        Path(args.output).write_text(json_str)
        print(f"Extracted to: {args.output}")
    else:
        print(json_str)


if __name__ == "__main__":
    cli()
