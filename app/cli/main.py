"""Command-line interface for InvoiceForge.

Usage:
    invoiceforge convert input.pdf -o output.xml --format xrechnung_cii
    invoiceforge validate invoice.xml
    invoiceforge serve --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
import sys


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
    convert_parser = subparsers.add_parser("convert", help="Convert an invoice file")
    convert_parser.add_argument("input", help="Input file path")
    convert_parser.add_argument("-o", "--output", help="Output file path")
    convert_parser.add_argument(
        "--format",
        choices=["zugferd_pdf", "xrechnung_cii", "xrechnung_ubl"],
        default="zugferd_pdf",
        help="Output format",
    )
    convert_parser.add_argument(
        "--profile",
        choices=["MINIMUM", "BASIC WL", "BASIC", "EN 16931", "EXTENDED", "XRECHNUNG"],
        default="EN 16931",
        help="ZUGFeRD profile",
    )

    # --- validate ---
    validate_parser = subparsers.add_parser("validate", help="Validate an E-Rechnung XML")
    validate_parser.add_argument("input", help="XML file to validate")

    args = parser.parse_args()

    if args.command == "serve":
        _run_server(args)
    elif args.command == "convert":
        print("Convert command not yet implemented.", file=sys.stderr)
        sys.exit(1)
    elif args.command == "validate":
        print("Validate command not yet implemented.", file=sys.stderr)
        sys.exit(1)
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


if __name__ == "__main__":
    cli()
