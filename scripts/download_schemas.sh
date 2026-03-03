#!/usr/bin/env bash
# Download XSD and Schematron validation artefacts for offline validation.
#
# Sources:
#   XRechnung Schematron: https://github.com/itplr-kosit/xrechnung-schematron
#   EN 16931 validation:  https://github.com/ConnectingEurope/eInvoicing-EN16931
#   CII / UBL XSD schemas from UN/CEFACT and OASIS
#
# Usage:
#   ./scripts/download_schemas.sh [target-directory]
#
set -euo pipefail

SCHEMA_DIR="${1:-data/schemas}"
mkdir -p "$SCHEMA_DIR"

echo "=== InvoiceForge: Validierungsartefakte herunterladen ==="
echo "Zielverzeichnis: $SCHEMA_DIR"

# --- XRechnung Schematron (latest release) ---
XRECHNUNG_SCHEMATRON_VERSION="1.8.3"
XRECHNUNG_SCHEMATRON_URL="https://github.com/itplr-kosit/xrechnung-schematron/releases/download/release-${XRECHNUNG_SCHEMATRON_VERSION}/xrechnung-${XRECHNUNG_SCHEMATRON_VERSION}-schematron.zip"
XRECHNUNG_DIR="$SCHEMA_DIR/xrechnung-schematron"

if [ ! -d "$XRECHNUNG_DIR" ]; then
    echo "Lade XRechnung Schematron ${XRECHNUNG_SCHEMATRON_VERSION} herunter..."
    curl -fsSL -o /tmp/xrechnung-schematron.zip "$XRECHNUNG_SCHEMATRON_URL" || {
        echo "WARNUNG: Download fehlgeschlagen. Schematron-Validierung offline nicht verfügbar."
        echo "URL: $XRECHNUNG_SCHEMATRON_URL"
    }
    if [ -f /tmp/xrechnung-schematron.zip ]; then
        mkdir -p "$XRECHNUNG_DIR"
        unzip -qo /tmp/xrechnung-schematron.zip -d "$XRECHNUNG_DIR"
        rm -f /tmp/xrechnung-schematron.zip
        echo "OK: XRechnung Schematron entpackt nach $XRECHNUNG_DIR"
    fi
else
    echo "SKIP: XRechnung Schematron bereits vorhanden"
fi

# --- EN 16931 validation artefacts ---
EN16931_VERSION="1.3.13"
EN16931_URL="https://github.com/ConnectingEurope/eInvoicing-EN16931/releases/download/validation-${EN16931_VERSION}/en16931-${EN16931_VERSION}.zip"
EN16931_DIR="$SCHEMA_DIR/en16931"

if [ ! -d "$EN16931_DIR" ]; then
    echo "Lade EN 16931 Validierungsartefakte ${EN16931_VERSION} herunter..."
    curl -fsSL -o /tmp/en16931.zip "$EN16931_URL" || {
        echo "WARNUNG: Download fehlgeschlagen. EN 16931 Schematron nicht verfügbar."
        echo "URL: $EN16931_URL"
    }
    if [ -f /tmp/en16931.zip ]; then
        mkdir -p "$EN16931_DIR"
        unzip -qo /tmp/en16931.zip -d "$EN16931_DIR"
        rm -f /tmp/en16931.zip
        echo "OK: EN 16931 entpackt nach $EN16931_DIR"
    fi
else
    echo "SKIP: EN 16931 bereits vorhanden"
fi

# --- CII (Cross Industry Invoice) XSD schema ---
CII_XSD_DIR="$SCHEMA_DIR/cii"

if [ ! -d "$CII_XSD_DIR" ]; then
    echo "Lade CII XSD-Schema (Factur-X/ZUGFeRD) herunter..."
    mkdir -p "$CII_XSD_DIR"
    # The CII schemas are bundled in the Factur-X distribution
    FACTURX_XSD_URL="https://raw.githubusercontent.com/akretion/factur-x/master/facturx/xsd/Factur-X_1.07.2/FACTUR-X_EN16931.xsd"
    curl -fsSL -o "$CII_XSD_DIR/FACTUR-X_EN16931.xsd" "$FACTURX_XSD_URL" 2>/dev/null || {
        echo "WARNUNG: CII XSD Download fehlgeschlagen. Verwende eingebettete Schemas."
    }
    echo "OK: CII XSD-Schema gespeichert"
else
    echo "SKIP: CII XSD-Schema bereits vorhanden"
fi

# --- UBL 2.1 XSD schema ---
UBL_XSD_DIR="$SCHEMA_DIR/ubl"

if [ ! -d "$UBL_XSD_DIR" ]; then
    echo "Lade UBL 2.1 XSD-Schema herunter..."
    UBL_XSD_URL="http://docs.oasis-open.org/ubl/os-UBL-2.1/UBL-2.1.zip"
    curl -fsSL -o /tmp/ubl21.zip "$UBL_XSD_URL" 2>/dev/null || {
        echo "WARNUNG: UBL XSD Download fehlgeschlagen."
    }
    if [ -f /tmp/ubl21.zip ]; then
        mkdir -p "$UBL_XSD_DIR"
        unzip -qo /tmp/ubl21.zip -d "$UBL_XSD_DIR"
        rm -f /tmp/ubl21.zip
        echo "OK: UBL 2.1 XSD entpackt nach $UBL_XSD_DIR"
    fi
else
    echo "SKIP: UBL XSD bereits vorhanden"
fi

echo ""
echo "=== Fertig ==="
echo "Schemas in: $SCHEMA_DIR"
ls -la "$SCHEMA_DIR/" 2>/dev/null || true
