# InvoiceForge – Phase 0: Recherche & Technologieentscheidung

**Projekt:** InvoiceForge – Open-Source E-Rechnungs-Konverter (ZUGFeRD & XRechnung)
**Datum:** 03.03.2026
**Status:** Phase 0 abgeschlossen

---

## Inhaltsverzeichnis

1. [Rechtliche Grundlagen](#1-rechtliche-grundlagen)
   1. [E-Rechnungspflicht Deutschland](#11-e-rechnungspflicht-deutschland--14-ustg)
   2. [XRechnung](#12-xrechnung)
   3. [ZUGFeRD](#13-zugferd)
   4. [EN 16931](#14-en-16931--europäische-norm)
   5. [PEPPOL](#15-peppol)
2. [Open-Source-Alternativen](#2-open-source-alternativen-auf-github)
3. [Technologieentscheidung](#3-technologieentscheidung)
4. [Quellen](#4-quellen)

---

## 1. Rechtliche Grundlagen

### 1.1 E-Rechnungspflicht Deutschland (§ 14 UStG)

#### Gesetzliche Basis

Mit dem **Wachstumschancengesetz** (verabschiedet 22.03.2024) wurden die Regelungen zur Rechnungsausstellung nach **§ 14 UStG** für nach dem 31.12.2024 ausgeführte Umsätze grundlegend neu gefasst:

- **E-Rechnung (neue Definition):** Eine Rechnung in einem strukturierten elektronischen Format, die elektronische Verarbeitung ermöglicht und der CEN-Norm EN 16931 entspricht (§ 14 Abs. 1 Satz 3 UStG n.F.).
- **Sonstige Rechnung:** Papierrechnungen und unstrukturierte PDFs gelten nun als „sonstige Rechnungen" – sie sind nicht mehr der Standard.

#### Stufenweise Einführung (Timeline)

| Zeitraum | Regelung |
|---|---|
| **Ab 01.01.2025** | **Empfangspflicht** für alle inländischen Unternehmen – ohne Ausnahme. Auch Kleinunternehmer, Vereine und Nebenerwerbsunternehmer müssen E-Rechnungen empfangen können. Ein E-Mail-Postfach genügt. |
| **01.01.2025 – 31.12.2026** | **Übergangsphase 1:** Beim Versand besteht Wahlfreiheit. Papierrechnungen bleiben zulässig. Andere elektronische Formate (z.B. einfache PDF per E-Mail) nur mit Zustimmung des Empfängers (§ 27 Abs. 38 Nr. 1 UStG). |
| **01.01.2027** | **Verschärfung:** Unternehmen mit **Vorjahresumsatz > 800.000 EUR** müssen E-Rechnungen im EN-16931-Format versenden. Papier und unstrukturierte elektronische Formate sind für diese Unternehmen nicht mehr zulässig. |
| **01.01.2027 – 31.12.2027** | **Übergangsphase 2:** Unternehmen mit Vorjahresumsatz **≤ 800.000 EUR** dürfen noch sonstige Rechnungen (Papier, PDF) ausstellen. EDI-basierte Rechnungen bleiben bis Ende 2027 zulässig, sofern die umsatzsteuerlichen Angaben extrahierbar sind. |
| **Ab 01.01.2028** | **Vollständige Pflicht** für **alle** Unternehmen im inländischen B2B-Bereich. Keine Übergangsregelungen mehr. |

#### Aktueller Status (März 2026)

Wir befinden uns in der **Übergangsphase 1**. Seit dem 01.01.2025:
- Alle Unternehmen müssen E-Rechnungen **empfangen** können
- Beim **Versand** besteht noch Wahlfreiheit
- **In 10 Monaten** (01.01.2027) greift die Versandpflicht für Unternehmen > 800.000 EUR Umsatz
- **InvoiceForge-Relevanz:** Hohe Dringlichkeit – viele Unternehmen suchen jetzt Lösungen

#### Betroffene Geschäftsarten

| Bereich | E-Rechnungspflicht | Anmerkung |
|---|---|---|
| **B2B** (inländisch) | Ja, stufenweise 2025–2028 | Kern der neuen Regelung |
| **B2G** (an Behörden) | Ja, bereits seit 27.11.2020 (Bund) | E-Rechnungsverordnung des Bundes; Länder haben eigene Regelungen |
| **B2C** (an Endverbraucher) | Nein | Keine E-Rechnungspflicht |
| **Grenzüberschreitend** | Nein (vorerst) | EU-ViDA geplant ab 01.07.2030 |

#### Kleinunternehmer (§ 19 UStG)

- **Empfangspflicht:** Ja, ab 01.01.2025 – ohne Ausnahme
- **Versandpflicht:** **Dauerhaft befreit** gemäß § 34a UStDV (eingeführt durch Jahressteuergesetz 2024)
- Kleinunternehmer können auch nach 2028 weiterhin Papier- oder PDF-Rechnungen ausstellen
- **Achtung:** „Kleinunternehmer" (§ 19 UStG, Grenze 25.000 EUR) ≠ „kleines Unternehmen" (≤ 800.000 EUR Umsatz für Übergangsfristen)

#### Ausnahmen (auch ab 2028 gültig)

- **Kleinbetragsrechnungen** bis 250 EUR (§ 33 UStDV)
- **Steuerfreie Leistungen** nach § 4 Nr. 8 bis 29 UStG
- **Fahrausweise** (§ 34 UStDV)
- **Dauerrechnungen:** Vor dem 01.01.2027 als sonstige Rechnung erteilte Dauerrechnungen müssen nicht zusätzlich als E-Rechnung ausgestellt werden, solange sich die Rechnungsangaben nicht ändern

#### Vorsteuerabzug in der Übergangszeit

In der Übergangszeit (01.01.2025 – 31.12.2027) soll der Vorsteuerabzug nicht allein wegen eines falschen Rechnungsformats versagt werden, sofern der Empfänger davon ausgehen konnte, dass der Aussteller die Übergangsregelungen in Anspruch nehmen konnte.

#### Sanktionen

Stellt ein Unternehmer keine E-Rechnung aus, obwohl er dazu verpflichtet ist, begeht er eine Ordnungswidrigkeit. Der Leistungsempfänger darf dann nur unter strengem Maßstab Vorsteuer abziehen.

---

### 1.2 XRechnung

#### Aktuelle Version

- **XRechnung 3.0.2** (Stand März 2026)
- Bugfix Release **2026-01-31** mit KoSIT Validator v1.6.0, CEN Schematron Rules 1.3.15, Schxslt 1.10.1
- Betrieben von der **KoSIT** (Koordinierungsstelle für IT-Standards) seit 01.01.2019
- Mittelfristig nur noch **ein Hauptrelease pro Jahr** geplant

#### Pflichtfelder

**Neue Pflichtfelder seit XRechnung 3.0.1 (Harmonisierung mit Peppol BIS Billing):**

| Feld | Bezeichnung | Hinweis |
|---|---|---|
| **BT-23** | Business Process Type | Standard-PEPPOL-Wert: `urn:fdc:peppol.eu:2017:poacc:billing:01:1.0` |
| **BT-34** | Seller Electronic Address | E-Mail oder elektronische Serviceadresse des Verkäufers |
| **BT-49** | Buyer Electronic Address | E-Mail oder elektronische Adresse des Käufers |

**Wichtige bestehende Pflichtfelder:**

| Feld | Bezeichnung | Anmerkung |
|---|---|---|
| **BT-1** | Invoice Number | Rechnungsnummer |
| **BT-2** | Invoice Issue Date | Rechnungsdatum |
| **BT-5** | Invoice Currency Code | Währungscode (z.B. EUR) |
| **BT-6** | VAT Accounting Currency | Abrechnungswährung der USt |
| **BT-10** | Buyer Reference | **Leitweg-ID bei B2G**, Platzhalter bei B2B |
| **BT-20** | Payment Terms | Zahlungsbedingungen (XRechnung erlaubt Skonto-Syntax) |
| **BG-4** | Seller | Verkäuferdaten inkl. USt-IdNr./Steuernummer |
| **BG-7** | Buyer | Käuferdaten |
| **BG-22** | Document Totals | Summen und Steuerbeträge |
| **BG-25** | Invoice Line | Rechnungspositionen |

#### Syntaxen

XRechnung unterstützt **zwei Syntaxen**:
- **UBL** (Universal Business Language, ISO 19845) – OASIS-Standard
- **CII** (UN/CEFACT Cross Industry Invoice) – UN-Standard

Beide sind gleichwertig zugelassen. PEPPOL nutzt primär UBL.

#### Anwendungsbereich

- **Primär B2G** (Rechnungen an öffentliche Auftraggeber) – hier verbindlicher Standard
- Auch im **B2B-Bereich** zugelassen als Format für die E-Rechnungspflicht
- XRechnung ist die deutsche **CIUS** (Core Invoice User Specification) der EN 16931 mit 21 zusätzlichen nationalen Geschäftsregeln

#### Leitweg-ID

**Was ist sie?**
Die Leitweg-ID ist eine eindeutige Zeichenkette zur Adressierung öffentlicher Auftraggeber (Behörden, Kommunen, Ministerien) in Deutschland.

**Aufbau:**
```
[Grobadressierung]-[Feinadressierung (optional)]-[Prüfziffern]
```
- **Grobadressierung** (2–12 Stellen, numerisch): Kodiert Bundesland, Regierungsbezirk, Landkreis, Gemeinde
- **Feinadressierung** (bis 30 Stellen, alphanumerisch, optional): Frei vergeben durch Bund/Länder
- **Prüfziffern** (2 Stellen, Pflicht)

**Wann Pflicht?**
- **Nur im B2G-Bereich.** E-Rechnungen ohne Leitweg-ID werden von den Eingangsplattformen (OZG-RE) abgelehnt.
- **Nicht im B2B-Bereich.** Hier genügt ein Platzhalter (z.B. „-") im Feld BT-10.
- Die Leitweg-ID wird vom öffentlichen Auftraggeber vergeben und dem Rechnungssteller mitgeteilt.
- PEPPOL Participant ID: `0204:<Leitweg-ID>`

**Wichtige Änderung 2025:** Die ZRE (Zentraler Rechnungseingang) wurde zum 31.12.2025 eingestellt. Nur noch die **OZG-RE** ist die alleinige Eingangsplattform des Bundes.

---

### 1.3 ZUGFeRD

#### Aktuelle Version

- **ZUGFeRD 2.4 / Factur-X 1.08** – veröffentlicht am 04.12.2025 durch das FeRD (Forum elektronische Rechnung Deutschland) und die französische FNFE-MPE
- **In Kraft seit: 15.01.2026**
- Technisch identisch mit Factur-X 1.08
- Basiert auf **UN/CEFACT CII D22B**, rückwärtskompatibel mit D16B

**Vorherige Versionen:**
- ZUGFeRD 2.3 / Factur-X 1.0.07 (18.09.2024)
- ZUGFeRD 2.3.3 / Factur-X 1.07.3 (Patch, Mai 2025)

#### Neuerungen in ZUGFeRD 2.4

- **Sub-Line Management:** Unterpositionen im Profil EXTENDED (Kits, Bündel, zusammengesetzte Artikel)
- **Aktualisierte Validierungsartefakte:** Alle fünf Profile mit eigenen XSD- und Schematron-Validierungen
- **Steuerrechtliche Anpassungen:** Berücksichtigt BMF-Stellungnahme vom 15.10.2025

#### Profile

| Profil | UStG-konform | EN 16931-konform | Positionen | Einsatzgebiet |
|---|---|---|---|---|
| **MINIMUM** | ❌ | ❌ | Nein | Nur Buchungshilfe, **nicht als Rechnung nutzbar** |
| **BASIC WL** | ❌ | ❌ | Nein | Nur Buchungshilfe (Factur-X-Kompatibilität) |
| **BASIC** | ✅ | Untermenge | Optional | Einfachste UStG-konforme Rechnungen |
| **EN 16931 (COMFORT)** | ✅ | ✅ Fully Compliant | Ja | **Empfohlener Standard für B2B** |
| **EXTENDED** | ✅ | ✅ Conformant Extension | Ja (erweitert) | Komplexe Geschäftsprozesse |
| **XRECHNUNG** | ✅ | ✅ + nationale Regeln | Ja | **B2G** – reine XML ohne PDF, XRechnung-konform |

**Empfehlung für InvoiceForge:** Profil **EN 16931 (COMFORT)** für Standard-B2B, **XRECHNUNG** für B2G.

#### Technische Implementierung

ZUGFeRD (außer Profil XRECHNUNG) ist ein **Hybridformat**:
1. **PDF/A-3:** Menschenlesbares PDF-Dokument (visuelle Darstellung)
2. **Eingebettetes CII-XML:** Maschinenlesbarer strukturierter Datensatz als Anhang im PDF

**Syntax:** ZUGFeRD nutzt **ausschließlich CII** (kein UBL).

**Ab 01.01.2025:** Maßgeblich ist der Inhalt des XML. Das PDF hat keine umsatzsteuerliche Relevanz mehr.

#### Technischer Unterschied zu XRechnung

| Merkmal | ZUGFeRD | XRechnung |
|---|---|---|
| **Format** | Hybrid: PDF/A-3 + eingebettetes XML | Reine XML-Datei |
| **Syntaxen** | Nur CII | CII **und** UBL |
| **Menschenlesbarkeit** | Ja (PDF-Teil) | Nein (nur mit XSLT-Visualisierung) |
| **Primärer Einsatz** | B2B | B2G (auch B2B möglich) |
| **Nationale Geschäftsregeln** | Profilabhängig | 21 zusätzliche nationale Regeln |
| **Leitweg-ID** | Nur bei B2G (Profil XRECHNUNG) | Pflicht in BT-10 bei B2G |

**Konvergenz:** Seit ZUGFeRD 2.1 ist die XML-Komponente im Profil EN 16931 identisch mit XRechnung (CII-Variante). Das ZUGFeRD-Profil „XRECHNUNG" erzeugt eine reine XML-Datei und ist vollständig XRechnung-konform.

---

### 1.4 EN 16931 – Europäische Norm

#### Überblick

**EN 16931** ist die europäische Norm für die elektronische Rechnungsstellung, entwickelt vom CEN (Europäisches Komitee für Normung). Sie definiert:
- Ein **semantisches Datenmodell** (welche Datenfelder eine E-Rechnung enthalten muss)
- Kompatibilität mit verschiedenen IT-Systemen in der gesamten EU
- Basiert auf **EU-Richtlinie 2014/55/EU**

#### Zugelassene Syntaxen

| Syntax | Standard | Verwendung |
|---|---|---|
| **UBL** | OASIS ISO 19845 | XRechnung, PEPPOL BIS Billing |
| **CII** | UN/CEFACT | ZUGFeRD, XRechnung |

Die Syntaxen sind **nicht miteinander kompatibel** (unterschiedliche Benennung und Strukturierung).

#### Verhältnis zu XRechnung und ZUGFeRD

```
EN 16931 (Europäische Norm – semantisches Datenmodell)
├── UBL-Syntax (OASIS)
│   ├── XRechnung (deutsche CIUS – darf einschränken, nicht erweitern)
│   └── PEPPOL BIS Billing 3.0
└── CII-Syntax (UN/CEFACT)
    ├── XRechnung (deutsche CIUS)
    └── ZUGFeRD 2.x (Profile: BASIC, EN 16931, EXTENDED, XRECHNUNG)
```

- **XRechnung** = deutsche CIUS (Core Invoice User Specification): Schränkt EN 16931 ein, fügt nationale Regeln hinzu, darf keine neuen Felder definieren
- **ZUGFeRD Profil EN 16931** = Fully Compliant CIUS der EN 16931
- **ZUGFeRD Profil EXTENDED** = Conformant Extension (darf zusätzliche Felder nutzen)
- **ZUGFeRD Profile MINIMUM/BASIC WL** = Nicht EN 16931-konform

---

### 1.5 PEPPOL

#### Relevanz für Deutschland

**PEPPOL** (Pan-European Public Procurement Online) ist ein Netzwerk für den sicheren elektronischen Austausch von Geschäftsdokumenten. Relevanz:

- **B2G:** Bundes- und Landesbehörden müssen PEPPOL als Übertragungsweg unterstützen. Einziger Weg für automatisierte Maschine-zu-Maschine-Kommunikation (m2m) und Massenexport.
- **B2B:** Zunehmende Bedeutung. Keine gesetzliche Pflicht, aber zukunftssicherste Infrastruktur.
- **PEPPOL Authority Deutschland:** Betrieben von der KoSIT.
- Über 1,4 Millionen Organisationen in 98 Ländern sind als PEPPOL-Teilnehmer registriert.

#### PEPPOL BIS Billing 3.0 und XRechnung – Interchangeable

Seit dem OpenPeppol-Release vom November 2024 (live seit 17.02.2025) sind XRechnung-Geschäftsregeln als **German National Ruleset (DE-NRS)** in Peppol BIS Billing 3.0 integriert. Beide Formate sind nun **inhaltlich äquivalent und austauschbar**.

#### GEBA – German Electronic Business Address (neu ab 2026)

Die **GEBA** wurde im Dezember 2025 veröffentlicht und bietet ein standardisiertes Adressierungssystem für das PEPPOL-Netzwerk:

```
[W-IdNr]-[Unterscheidungsmerkmal]-[Unter-Adressierung]
Beispiel: DE123456789-00001-RECH0001
```

- Registriert unter **ICD 0246** (ISO/IEC 6523)
- Basiert auf der Wirtschafts-Identifikationsnummer (W-IdNr)
- Primär für B2B-Szenarien, freiwillig
- Leitweg-ID bleibt für B2G verpflichtend

#### Wann ist PEPPOL notwendig?

| Szenario | PEPPOL erforderlich? | Alternative |
|---|---|---|
| **Rechnungen an Bundesbehörden** | Empfohlen (einer von drei Wegen) | E-Mail an OZG-RE, De-Mail |
| **B2B national** | Nein (freiwillig) | E-Mail, Portal-Upload, EDI |
| **Massenrechnungen an Behörden** | De facto ja (m2m) | Kein gleichwertiger Weg |
| **Zukunftssicherheit** | Stark empfohlen | – |

**Relevanz für InvoiceForge:** PEPPOL-Versand ist für Phase 1 nicht kritisch, sollte aber in der Architektur als Erweiterungsmöglichkeit vorgesehen werden. Die XML-Formate (UBL/CII) müssen jedoch PEPPOL BIS Billing 3.0-kompatibel sein, da dieses Format ebenfalls als E-Rechnungsformat zugelassen ist.

---

## 2. Open-Source-Alternativen auf GitHub

### 2.1 mustangproject (Java)

| Eigenschaft | Details |
|---|---|
| **Repository** | [github.com/ZUGFeRD/mustangproject](https://github.com/ZUGFeRD/mustangproject) |
| **Lizenz** | Apache 2.0 |
| **Aktualität** | v2.22.0 (04.02.2026) – sehr aktiv |
| **Sterne** | ~350+ |
| **Sprache** | Java |
| **Formate** | ZUGFeRD 2.4, ZUGFeRD 1, Factur-X 1, XRechnung 3.0.2 (CII) |
| **Features** | Lesen, Schreiben, Validieren, Konvertieren; CLI + REST-API (Mustangserver); PDF/A-3-Erzeugung |

**Stärken:**
- Referenzimplementierung des FeRD – höchste Kompatibilitätsgarantie
- Unterstützt alle aktuellen Formatversionen
- Integrierter Validator (Schematron + XSD)
- Aktiv gepflegt durch Jochen Stärk

**Schwächen:**
- Java – nicht direkt als Python-Dependency nutzbar
- Große JAR-Dependencies (Apache PDFBox etc.)
- REST-API (Mustangserver) als Brücke zu Python möglich, aber zusätzliche Infrastruktur

**Fazit für InvoiceForge:** **Nicht als direkte Dependency, aber als Referenz und Validierungsbackend nutzbar.** Mustangserver kann als Docker-Container für Validierung und Konvertierung eingesetzt werden.

---

### 2.2 python-drafthorse (Python)

| Eigenschaft | Details |
|---|---|
| **Repository** | [github.com/pretix/python-drafthorse](https://github.com/pretix/python-drafthorse) |
| **Lizenz** | Apache 2.0 |
| **Aktualität** | v2025.2.0 (September 2025) – aktiv |
| **Sterne** | ~164 |
| **Sprache** | Python (pure) |
| **Formate** | ZUGFeRD 2.3 (CII), alle Profile: MINIMUM, BASIC WL, BASIC, EN 16931, EXTENDED, XRECHNUNG |

**Stärken:**
- **Pure Python** – keine Java-Abhängigkeit
- 1:1-Abbildung des ZUGFeRD-Datenmodells (low-level)
- XML-Generierung und -Parsing
- PDF/A-3-Einbettung via `attach_xml()`
- XSD-Validierung der Ausgabe
- Automatische Profil-Level-Erkennung
- Aktiv gepflegt durch pretix-Team (pretix-zugferd Modul)

**Schwächen:**
- Kein Parsing von PDFs (Extraktion aus bestehenden ZUGFeRD-PDFs nicht unterstützt)
- Keine Profil-Level-Validierung (nur XSD)
- Low-Level-API: Erfordert detailliertes Wissen über das ZUGFeRD-Datenmodell
- Maintainer weisen darauf hin, dass es nicht ihr Kerngeschäft ist – längere Reaktionszeiten

**Fazit für InvoiceForge:** **Primäre Dependency für ZUGFeRD-XML-Generierung.** Beste Python-native Lösung für die CII-XML-Erzeugung. Ergänzung durch factur-x für PDF/A-3-Handling sinnvoll.

---

### 2.3 factur-x (Python)

| Eigenschaft | Details |
|---|---|
| **Repository** | [github.com/akretion/factur-x](https://github.com/akretion/factur-x) |
| **Lizenz** | BSD |
| **Aktualität** | v3.15 (05.12.2025) – sehr aktiv |
| **Sterne** | ~200+ |
| **Sprache** | Python |
| **Formate** | Factur-X/ZUGFeRD (alle Profile), XRechnung-Extraktion (seit v3.13) |

**Stärken:**
- **Produktion-stabil** (Status: „5 – Production/Stable")
- PDF/A-3-Generierung: Kombiniert PDF + XML zu Factur-X/ZUGFeRD-Rechnung
- XML-Extraktion aus bestehenden ZUGFeRD-PDFs (`get_xml_from_pdf()`)
- XRechnung-Support seit v3.13 (Oktober 2025)
- XSD-Validierung der XML-Dateien (`facturx-xmlcheck`)
- CLI-Tools: `facturx-pdfgen`, `facturx-pdfextractxml`, `facturx-xmlcheck`
- Sehr aktive Weiterentwicklung (7 Releases in 2025)
- XSD-Dateien aktualisiert auf Factur-X 1.0.8

**Schwächen:**
- **Generiert kein XML von Grund auf** – erwartet fertiges XML als Input
- Primär PDF-zentriert (PDF + XML → ZUGFeRD-PDF)
- Kein Datenmodell für programmatische XML-Erstellung

**Fazit für InvoiceForge:** **Essenzielle Dependency für PDF/A-3-Handling.** Komplementär zu drafthorse: drafthorse erzeugt das XML, factur-x bettet es in PDF/A-3 ein und validiert.

---

### 2.4 invoice2data (Python)

| Eigenschaft | Details |
|---|---|
| **Repository** | [github.com/invoice-x/invoice2data](https://github.com/invoice-x/invoice2data) |
| **Lizenz** | MIT |
| **Aktualität** | Letzter Push Mai 2025 – aktiv |
| **Sterne** | ~1.965 |
| **Sprache** | Python |
| **Features** | PDF-Text-Extraktion, Template-basierte Datenextraktion, OCR-Support |

**Stärken:**
- Sehr populär und gut dokumentiert
- Multiple Input-Reader: pdftotext, pdfminer, pdfplumber, OCR (Tesseract), Google Cloud Vision
- Flexibles YAML/JSON-Template-System für verschiedene Rechnungslayouts
- Output: CSV, JSON, XML
- CLI + Python-Library-API

**Schwächen:**
- Template-basiert: Erfordert für jeden Rechnungslayout ein eigenes Template
- Keine KI/ML-basierte Feldextraktion
- YAML-Parsing langsam (10x schneller mit libyaml)
- Kein ZUGFeRD/XRechnung-Output

**Fazit für InvoiceForge:** **Nützliche Dependency für die Datenextraktion aus Eingangsrechnungen (PDFs).** Kann als Fallback neben LLM-basierter Extraktion eingesetzt werden. Template-Bibliothek für häufige Rechnungsformate aufbauen.

---

### 2.5 KoSIT Validator (Java)

| Eigenschaft | Details |
|---|---|
| **Repository (Validator)** | [github.com/itplr-kosit/validator](https://github.com/itplr-kosit/validator) |
| **Repository (Config)** | [github.com/itplr-kosit/validator-configuration-xrechnung](https://github.com/itplr-kosit/validator-configuration-xrechnung) |
| **Lizenz** | Apache 2.0 |
| **Aktualität** | Config: 19.02.2026, Validator: v1.6.0 (17.02.2026) – sehr aktiv |
| **Sterne** | ~141 (Validator) |
| **Sprache** | Java |
| **Features** | XML-Validierung mit XSD + Schematron, XRechnung 3.0.x, UBL + CII |

**Stärken:**
- **Offizielle Referenz-Validierung** der KoSIT
- Enthält alle notwendigen XSD- und Schematron-Regeln
- CEN Schematron Rules 1.3.15, XRechnung Schematron 2.4.0
- Unterstützt Validierung ganzer Verzeichnisbäume
- Testsuite mit Beispiel-Rechnungen verfügbar

**Schwächen:**
- Java-basiert (JRE erforderlich)
- Erfordert Download von Validator + Konfiguration

**Fazit für InvoiceForge:** **Essenzielle Komponente für Validierung.** Als Docker-Container oder über Subprocess-Aufruf in Python integrierbar. Alternativ: Schematron-Regeln direkt mit `lxml` in Python ausführen.

---

### 2.6 XFakturist (Python)

| Eigenschaft | Details |
|---|---|
| **Repository** | [github.com/drbrnn/XFakturist](https://github.com/drbrnn/XFakturist) |
| **Lizenz** | Open Source (Details auf GitHub) |
| **Sprache** | Python |
| **Features** | Minimalistischer Standalone-XRechnung-XML-Generator |

**Stärken:**
- Standalone, keine externen Dienste nötig
- Einfacher Workflow: JSON/XLSX → XRechnung-XML
- Integriert KoSIT-Validator-Aufruf
- Datenschutz: Kein Datenversand an Dritte

**Schwächen:**
- Minimalistisch – nur einfache Rechnungen mit wenigen Positionen
- CLI-only, kein API
- Keine ZUGFeRD-Unterstützung
- Kleines Projekt, begrenzte Community

**Fazit für InvoiceForge:** **Nicht als Dependency, aber als Referenz nützlich.** Zeigt einen minimalen Workflow für XRechnung-Generierung in Python.

---

### 2.7 pycheval (Python) – ZUGFeRD 2.4

| Eigenschaft | Details |
|---|---|
| **Repository** | [github.com/zfutura/pycheval](https://github.com/zfutura/pycheval) |
| **Lizenz** | Apache 2.0 |
| **Aktualität** | Letzter Commit: 13.02.2026 – aktiv |
| **Sterne** | ~22 |
| **Sprache** | Python |
| **Formate** | Factur-X 1.08 / ZUGFeRD 2.4 (MINIMUM, BASIC WL, BASIC, EN 16931) |

**Stärken:**
- **Einzige Python-Bibliothek mit ZUGFeRD 2.4 / Factur-X 1.08 Support**
- Lesen und Schreiben von PDF- und XML-Dateien
- Aktive Entwicklung (Februar 2026)
- Apache-2.0-Lizenz (permissiv)

**Schwächen:**
- **EXTENDED und XRECHNUNG Profile fehlen noch**
- Sehr junge Bibliothek, kleine Community (22 Sterne)
- API kann sich noch ändern
- Wenig Dokumentation

**Fazit für InvoiceForge:** **Beobachten für die Zukunft.** Aktuell zu unreif für Produktionseinsatz (fehlende Profile), aber einziger Python-Weg zu ZUGFeRD 2.4. Kann als Ergänzung relevant werden, sobald EXTENDED und XRECHNUNG unterstützt werden.

---

### 2.8 Weitere relevante Projekte

| Projekt | Sprache | Beschreibung | Relevanz |
|---|---|---|---|
| **[horstoeko/zugferd](https://github.com/horstoeko/zugferd)** | PHP | Vollständige ZUGFeRD/XRechnung-Bibliothek (Lesen + Schreiben, alle Profile), ~387 ★, MIT | Referenz für Datenmodell, nicht als Dependency |
| **[factur-x-ng](https://github.com/invoice-x/factur-x-ng)** | Python | Fork von factur-x mit höherer API-Abstraktion, Multi-Flavor-Support (CII+UBL) | Beobachten, evtl. als Alternative |
| **[python-en16931](https://github.com/invinet/python-en16931)** | Python | Einzige Python-Lib für UBL 2.1 nach EN 16931 (Proof of Concept) | Referenz für UBL-Generierung |
| **[xrechnung-visualization](https://github.com/itplr-kosit/xrechnung-visualization)** | XSLT | Offizielle XSL-Transformatoren für Web/PDF-Rendering, ~122 ★ | Nützlich für Vorschau-Funktion |
| **[xrechnung-testsuite](https://github.com/itplr-kosit/xrechnung-testsuite)** | XML | Offizielle Test-Rechnungen für XRechnung-Standard | Essenzielle Testdaten |
| **[ZUGFeRD/corpus](https://github.com/ZUGFeRD/corpus)** | XML/PDF | Sammlung realer und Test-ZUGFeRD-Rechnungen (korrekte + fehlerhafte) | Essenzielle Testdaten |
| **[OpenXRechnungToolbox](https://github.com/jcthiele/OpenXRechnungToolbox)** | Java | GUI für XRechnung-Visualisierung/Validierung, Leitweg-ID-Berechnung, ~160 ★ | Referenz-Tool zum Testen |
| **[e-invoice-eu](https://github.com/gflohr/e-invoice-eu)** | TypeScript | Vollständige EN 16931-Lösung (CLI+REST+Lib), ~130 ★ | Konzeptionelle Referenz |
| **[xrechnungs-generator](https://github.com/xSentry/xrechnungs-generator)** | Python | CSV → XRechnung-XML | Referenz für Batch-Verarbeitung |
| **[excel2zugferd](https://github.com/lka/excel2zugferd)** | Python | Excel → ZUGFeRD-PDF, Apache 2.0 | Endanwender-Tool, Referenz |

---

### 2.9 Zusammenfassende Bewertung der Python-Bibliotheken

| Bibliothek | XML erzeugen | XML parsen | PDF/A-3 | Validierung | ZUGFeRD-Version | Empfehlung |
|---|---|---|---|---|---|---|
| **drafthorse** | ✅ (CII) | ✅ | ✅ (attach_xml) | XSD nur | 2.3 | **Kern-Dependency** für XML-Erzeugung |
| **factur-x** | ❌ | ✅ (Extraktion) | ✅ (Einbettung) | XSD | 2.3 (XSD: 1.0.8) | **Kern-Dependency** für PDF/A-3 |
| **pycheval** | ✅ | ✅ | ✅ | ❌ | **2.4** | Beobachten (EXTENDED/XR fehlt) |
| **invoice2data** | ❌ | ❌ | ❌ | ❌ | – | **Optional** für PDF-Datenextraktion |

**Kombinationsstrategie:**
1. **drafthorse** → Programmatische Erzeugung der CII-XML-Daten
2. **factur-x** → Einbettung des XML in PDF/A-3 (ZUGFeRD) + Extraktion aus bestehenden E-Rechnungen
3. **KoSIT Validator** (Docker/Subprocess) → Offizielle Schematron-Validierung
4. **invoice2data** oder **LLM** → Extraktion strukturierter Daten aus Eingangsrechnungen

---

## 3. Technologieentscheidung

### 3.1 Entscheidungsmatrix

#### Backend-Framework

| Kriterium | FastAPI | Flask | Django |
|---|---|---|---|
| **Performance** | ✅ ~2.847 req/s, async-native | ⚠️ ~892 req/s, sync | ⚠️ ~743 req/s, sync |
| **API-Dokumentation** | ✅ Auto-generiert (OpenAPI/Swagger) | ❌ Manuell | ⚠️ DRF hat eigene Docs |
| **Docker-Image** | ✅ Schlank (~50 MB) | ✅ Schlank (~45 MB) | ❌ Größer (~120 MB) |
| **Async/Hintergrund-Jobs** | ✅ Nativ (async/await) | ❌ Bolt-on | ⚠️ Channels/Celery nötig |
| **Datenvalidierung** | ✅ Pydantic (nativ) | ❌ Extern | ⚠️ Serializers (DRF) |
| **Lernkurve** | ✅ Gering (modern Python) | ✅ Gering | ⚠️ Mittel |
| **Mehrmandanten** | ⚠️ Manuell implementierbar | ⚠️ Manuell | ✅ django-tenants |
| **Admin-UI** | ❌ Nicht enthalten | ❌ Nicht enthalten | ✅ Django Admin |

**Entscheidung: FastAPI** ✅

**Begründung:**
- InvoiceForge ist primär ein **API-/Processing-Service**, kein Full-Stack-Webportal
- Async-Support essenziell für parallele Dokumentenverarbeitung (OCR, PDF-Generierung, Validierung)
- Auto-generierte OpenAPI-Dokumentation erleichtert Integration in bestehende Systeme
- Pydantic-Datenmodelle passen perfekt zur strukturierten Rechnungsdatenvalidierung
- Schlankste Docker-Images
- Mehrmandanten-Fähigkeit wird über eigene Middleware/Dependency-Injection gelöst

---

#### ZUGFeRD-/XRechnung-Bibliotheken

| Kriterium | drafthorse | factur-x | Kombination |
|---|---|---|---|
| **CII-XML erzeugen** | ✅ Programmatisch | ❌ | ✅ drafthorse |
| **UBL-XML erzeugen** | ❌ | ❌ | ⚠️ Eigene Implementierung nötig |
| **PDF/A-3 erzeugen** | ✅ (attach_xml) | ✅ (generate_from_file) | ✅ Beide möglich |
| **XML aus PDF extrahieren** | ❌ | ✅ (get_xml_from_pdf) | ✅ factur-x |
| **XSD-Validierung** | ✅ | ✅ | ✅ |
| **Wartung** | ✅ Aktiv (pretix) | ✅ Sehr aktiv (Akretion) | ✅ |

**Entscheidung: drafthorse + factur-x** ✅

**Begründung:**
- **drafthorse** für die programmatische Erzeugung von CII-XML nach dem ZUGFeRD-Datenmodell
- **factur-x** für PDF/A-3-Einbettung und XML-Extraktion aus bestehenden E-Rechnungen
- Für **UBL-XRechnung** (benötigt für volle PEPPOL-Kompatibilität): Eigenes Mapping auf Basis der EN 16931-Datenstruktur, Template-basiert mit `lxml`
- KoSIT Validator für Schematron-Validierung als Docker-Sidecar

---

#### OCR/Datenextraktion

| Kriterium | pdfplumber + Tesseract | marker-pdf | LLM-basiert | invoice2data |
|---|---|---|---|---|
| **Digitale PDFs** | ✅ Sehr gut | ✅ Exzellent | ✅ Sehr gut | ✅ Gut (Template-basiert) |
| **Gescannte PDFs** | ⚠️ Tesseract nötig | ✅ Built-in ML-OCR | ✅ Vision-API | ⚠️ Tesseract nötig |
| **Tabellenextraktion** | ✅ Exzellent | ⚠️ Gut | ⚠️ Gut | ⚠️ Regex-basiert |
| **Geschwindigkeit** | ✅ ~0.1s | ❌ ~11s + 1GB Modell | ❌ API-Latenz | ✅ Schnell |
| **Feldextraktion** | ❌ Manuell | ❌ Manuell | ✅ Automatisch | ⚠️ Template nötig |
| **Docker-tauglich** | ✅ Klein | ❌ Groß (1GB+) | ✅ API-Call | ✅ Klein |
| **Kosten** | ✅ Kostenlos | ✅ Kostenlos | ❌ API-Kosten | ✅ Kostenlos |

**Entscheidung: Zweistufiges System** ✅

**Begründung:**
1. **Stufe 1 – Strukturierte Extraktion:** `pdfplumber` für digitale PDFs (Tabellen, Text, Koordinaten) + `Tesseract` für gescannte Dokumente (OCR)
2. **Stufe 2 – Intelligente Feldextraktion:** LLM-basiert (Claude API oder lokal mit Ollama) für die semantische Zuordnung der extrahierten Texte zu Rechnungsfeldern
3. **Fallback:** `invoice2data` mit YAML-Templates für bekannte Rechnungsformate

**Warum nicht marker-pdf?** 1GB Modell-Download und hoher Speicherverbrauch sind für schlanke Docker-Container ungeeignet. Für InvoiceForge ist die Kombination pdfplumber + Tesseract + LLM überlegen.

---

#### Datenbank

| Kriterium | SQLite (dev) + PostgreSQL (prod) | Nur PostgreSQL |
|---|---|---|
| **Entwicklungskomfort** | ✅ Kein DB-Server nötig | ❌ PostgreSQL-Setup nötig |
| **Mehrmandanten** | ⚠️ SQLite nicht geeignet | ✅ Schema-basierte Isolation |
| **Migrations-Kompatibilität** | ⚠️ Manche Features fehlen in SQLite | ✅ Konsistent |
| **Docker-Deployment** | ⚠️ Dualstrategie komplex | ✅ Einfach |
| **Testbarkeit** | ✅ Schnell (in-memory) | ⚠️ Langsamer |

**Entscheidung: PostgreSQL (einheitlich) mit SQLite nur für Unit-Tests** ✅

**Begründung:**
- Mehrmandanten-Fähigkeit erfordert robuste DB von Anfang an
- Schema-basierte Tenant-Isolation in PostgreSQL (ein Schema pro Mandant)
- `asyncpg` als async-nativer PostgreSQL-Driver für FastAPI
- **Alembic** für Migrations-Management
- SQLite nur als Option für lokale Unit-Tests und schnelles Prototyping
- PostgreSQL-Container via Docker Compose für Entwicklung – minimaler Overhead

---

#### UI-Framework

| Kriterium | FastAPI + HTMX | Streamlit | Separates React-Frontend |
|---|---|---|---|
| **Architektur** | ✅ Single Server | ⚠️ Eigener Tornado-Server | ❌ Zwei separate Services |
| **Performance** | ✅ Schnell | ⚠️ Mittel | ✅ Schnell |
| **Docker-Footprint** | ✅ Minimal (gleicher Container) | ⚠️ Eigener Container | ❌ Zwei Container + Build |
| **Headless-Betrieb** | ✅ API steht allein | ⚠️ UI-zentriert | ✅ API steht allein |
| **Anpassbarkeit** | ✅ Volle Kontrolle | ❌ Begrenzt | ✅ Volle Kontrolle |
| **Entwicklungsaufwand** | ⚠️ HTML-Templates nötig | ✅ Minimal | ❌ Hoch |

**Entscheidung: FastAPI + HTMX + Jinja2-Templates** ✅

**Begründung:**
- InvoiceForge ist primär ein **Headless-Processing-Service** (API-first)
- HTMX + Jinja2 liefert eine leichtgewichtige Admin-/Monitoring-UI **im selben Container**
- Kein JavaScript-Build-Prozess nötig
- Kein zusätzlicher Server nötig (vs. Streamlit)
- Progressive Enhancement: API funktioniert auch ohne UI
- Spätere Migration zu einem echten Frontend (React/Vue) jederzeit möglich – die API ändert sich nicht

---

#### Validierung

| Kriterium | KoSIT Validator (Docker/Subprocess) | Schematron offline (lxml) | Eigene Validierung |
|---|---|---|---|
| **Compliance-Garantie** | ✅ Offizielle Referenz | ⚠️ Abhängig von Regel-Updates | ❌ Fehleranfällig |
| **Aktualität** | ✅ Automatisch mit neuen Configs | ⚠️ Manuelles Update | ❌ Manuell |
| **Performance** | ⚠️ Java-Startup-Overhead | ✅ Schnell (in-process) | ✅ Schnell |
| **Docker-Integration** | ✅ Sidecar-Container | ✅ Im App-Container | ✅ Im App-Container |
| **Wartungsaufwand** | ✅ Gering | ⚠️ Mittel | ❌ Hoch |

**Entscheidung: Hybrid – lxml-Schematron für Schnellvalidierung + KoSIT Validator für Compliance-Check** ✅

**Begründung:**
- **Schnellvalidierung:** XSD-Validierung inline mit `lxml`/drafthorse für sofortiges Feedback während der Rechnungserstellung
- **Compliance-Validierung:** KoSIT Validator als Docker-Sidecar (Daemon-Modus, HTTP-API) für vollständige offizielle Validierung vor dem finalen Export
- Beide Schichten reduzieren Fehler und gewährleisten Gesetzeskonformität
- KoSIT-Validator-Config wird als Git-Submodule oder periodischer Download eingebunden

**Kritische Einschränkung – XSLT2-Problem:**
Die EN16931/XRechnung-Schematron-Regeln verwenden `queryBinding="xslt2"`. Pythons `lxml.isoschematron` unterstützt **nur XSLT 1.0**. Es gibt keine reine Python-Implementierung für XSLT2-basierte Schematron-Validierung. Daher ist der KoSIT Validator (Java) für die vollständige Schematron-Validierung **zwingend erforderlich** – die Python-seitige Validierung beschränkt sich auf XSD.

---

### 3.2 Gesamtarchitektur (Übersicht)

```
┌─────────────────────────────────────────────────────────┐
│                    InvoiceForge                          │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  FastAPI  │  │   HTMX UI    │  │  Background       │  │
│  │  REST API │  │  (optional)  │  │  Workers (ARQ)    │  │
│  └────┬─────┘  └──────┬───────┘  └────────┬─────────┘  │
│       │               │                    │            │
│  ┌────▼───────────────▼────────────────────▼─────────┐  │
│  │              Core Processing Pipeline              │  │
│  │                                                    │  │
│  │  Input    → Extraktion  → Mapping   → Validierung  │  │
│  │  (PDF,     (pdfplumber,  (→ CII/    (XSD +         │  │
│  │   Bild,     Tesseract,    UBL        Schematron)   │  │
│  │   CSV,      LLM)         Daten-                    │  │
│  │   JSON)                  modell)                    │  │
│  │                                                    │  │
│  │  → Generierung  → Export                           │  │
│  │    (drafthorse    (ZUGFeRD PDF/A-3,                │  │
│  │     + factur-x)    XRechnung XML,                  │  │
│  │                    PEPPOL-ready)                    │  │
│  └────────────────────────────────────────────────────┘  │
│                          │                               │
│  ┌───────────┐  ┌───────▼───────┐  ┌────────────────┐  │
│  │ PostgreSQL │  │ KoSIT Valid.  │  │ Datei-Storage   │  │
│  │ (Alembic)  │  │ (Sidecar)     │  │ (lokal/WebDAV/ │  │
│  │            │  │               │  │  Nextcloud)     │  │
│  └───────────┘  └───────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 3.3 Finaler Tech-Stack

| Komponente | Technologie | Begründung |
|---|---|---|
| **Backend-Framework** | FastAPI + Uvicorn | Async-Performance, OpenAPI, Pydantic |
| **ZUGFeRD-XML (CII)** | drafthorse | Pure Python, 1:1-Datenmodell |
| **PDF/A-3 Einbettung** | factur-x | XML→PDF/A-3-Einbettung, Extraktion |
| **PDF-Rendering (visuell)** | WeasyPrint + Jinja2 | HTML/CSS→PDF, flexible Templates |
| **XRechnung (UBL)** | lxml + eigene Templates | Kein Python-Lib für UBL-Generierung vorhanden |
| **Validierung (schnell)** | lxml + Schematron | In-Process, sofortiges Feedback |
| **Validierung (offiziell)** | KoSIT Validator (Docker) | Referenz-Compliance |
| **OCR/Textextraktion** | pdfplumber + Tesseract | Lightweight, Docker-tauglich |
| **Intelligente Extraktion** | LLM-API (Claude / Ollama) | Semantische Feldzuordnung |
| **Fallback-Extraktion** | invoice2data | Template-basiert für bekannte Layouts |
| **Datenbank** | PostgreSQL + asyncpg | Mehrmandanten, async |
| **Migrationen** | Alembic | SQLAlchemy-basiert |
| **ORM** | SQLAlchemy 2.0 (async) | Standard, gut dokumentiert |
| **Background Jobs** | ARQ (Redis-basiert) | Async-native, leichtgewichtig |
| **UI** | HTMX + Jinja2 | Im selben Container, progressiv |
| **Datei-Storage** | Lokal + WebDAV-Client | Nextcloud/ownCloud-Kompatibilität |
| **Containerisierung** | Docker + Docker Compose | Standard-Deployment |
| **Python-Version** | 3.12+ | Aktuelle LTS, Performance-Verbesserungen |

### 3.4 Docker-Compose-Dienste (geplant)

| Dienst | Image | Zweck |
|---|---|---|
| `invoiceforge-api` | Python 3.12-slim | FastAPI + HTMX UI |
| `invoiceforge-worker` | Python 3.12-slim | ARQ Background Worker |
| `postgres` | postgres:16-alpine | Datenbank |
| `redis` | redis:7-alpine | Job-Queue + Cache |
| `kosit-validator` | eclipse-temurin:21-jre-alpine + KoSIT | Validierung (optional) |

### 3.5 Mehrmandanten-Konzept

- **Schema-basierte Isolation** in PostgreSQL: Ein eigenes DB-Schema pro Tenant
- **Tenant-Erkennung:** API-Key oder JWT-Token mit Tenant-ID
- **Middleware:** FastAPI-Dependency setzt den DB-Schema-Pfad pro Request
- **Datei-Isolation:** Separate Upload-/Output-Verzeichnisse pro Tenant
- **Konfiguration:** Tenant-spezifische Einstellungen (Absenderdaten, Steuernummern, Templates)

### 3.6 Nextcloud/WebDAV-Kompatibilität

- **WebDAV-Client:** `webdavlib` oder `requests` mit WebDAV-Erweiterungen
- **Watch-Ordner:** Periodischer Poll eines WebDAV-Verzeichnisses auf neue Eingangsrechnungen
- **Output-Ordner:** Konvertierte E-Rechnungen werden in konfigurierbaren WebDAV-Ordner geschrieben
- **Integration:** Optional als Nextcloud-External-Storage oder Direct-Mount

---

### 3.7 Risiken und offene Punkte

| Risiko | Schwere | Mitigation |
|---|---|---|
| **ZUGFeRD 2.4 nicht in Python-Libs** | Hoch | Weder drafthorse noch factur-x unterstützen aktuell ZUGFeRD 2.4 / Factur-X 1.08. pycheval unterstützt es, aber ohne EXTENDED/XRECHNUNG. **Mitigation:** Mustangproject REST-API als Fallback; Beitrag zu drafthorse/factur-x für 2.4-Support; pycheval beobachten. |
| **XSLT2 Schematron in Python unmöglich** | Hoch | Die offiziellen XRechnung-Schematron-Regeln sind XSLT2-basiert – Python hat keinen XSLT2-Prozessor. **Mitigation:** KoSIT Validator als Docker-Sidecar (Java) ist zwingend nötig für vollständige Validierung. |
| **Datenschutz bei LLM-Extraktion** | Mittel | Rechnungsdaten sind sensibel (Finanzdaten, Kundendaten). Cloud-LLM-API erfordert Datenschutzprüfung. **Mitigation:** Opt-in-Konfiguration; Alternative: Lokale LLMs (Ollama/llama.cpp) mit Genauigkeitseinbußen; invoice2data als Offline-Fallback. |
| **UBL-Generierung fehlt** | Mittel | Keine Python-Bibliothek kann UBL-XRechnung erzeugen. CII reicht für ZUGFeRD, aber volle PEPPOL-Kompatibilität braucht UBL. **Mitigation:** Eigene UBL-Templates mit lxml; python-en16931 als PoC-Referenz; CII-XRechnung als MVP. |
| **WeasyPrint System-Dependencies** | Niedrig | Pango, GObject, Cairo müssen im Docker-Image installiert werden (~50 MB extra). **Mitigation:** Multi-Stage-Build; Alternative: fpdf2 für einfachere Layouts. |
| **Java-Abhängigkeit (KoSIT)** | Niedrig | KoSIT Validator erfordert JRE. **Mitigation:** Separater Alpine+JRE-Container (~100 MB), nur für Validierung. |

### 3.8 Marktlücke und USP von InvoiceForge

Im Python-Ökosystem gibt es **keine Feature-komplette All-in-One-Lösung** für die E-Rechnungs-Konvertierung:

- **drafthorse** generiert CII-XML, hat aber kein High-Level-API
- **factur-x** bettet XML in PDF/A-3 ein, generiert aber kein XML
- **invoice2data** extrahiert Daten aus PDFs, erzeugt aber keine E-Rechnungen
- **Mustangproject** kann alles, ist aber Java

**InvoiceForge füllt diese Lücke:** Eine integrierte Python-Lösung, die den gesamten Workflow abdeckt – von der Eingangsrechnung (PDF/Bild/CSV) über die intelligente Datenextraktion (LLM-basiert) bis zur Generierung gesetzeskonformer E-Rechnungen (ZUGFeRD + XRechnung) mit automatischer Validierung.

---

## 4. Quellen

### Rechtliche Grundlagen
- [Bundesfinanzministerium – FAQ E-Rechnung (Stand Oktober 2025)](https://www.bundesfinanzministerium.de/Content/DE/FAQ/e-rechnung.html)
- [IHK Frankfurt – E-Rechnungspflicht ab 2025](https://www.frankfurt-main.ihk.de/recht/uebersicht-alle-rechtsthemen/steuerrecht/umsatzsteuer-national/e-rechnungspflicht-ab-2025-6055774)
- [ETL – Zeitplan E-Rechnungspflicht](https://www.etl.de/e-rechnung/zeitplan/)
- [Haufe – Elektronische Rechnung wird Pflicht](https://www.haufe.de/steuern/gesetzgebung-politik/elektronische-rechnung-wird-pflicht-e-rechnung-im-ueberblick_168_605558.html)
- [IHK Region Stuttgart – E-Rechnungen B2B ab 2025](https://www.ihk.de/stuttgart/fuer-unternehmen/recht-und-steuern/steuerrecht/steuermeldungen/e-rechnungen-5864496)
- [Bayerisches Landesamt für Steuern – E-Rechnung](https://www.lfst.bayern.de/steuerinfos/weitere-themen/e-rechnung)
- [taxaro – Zeitplan E-Rechnung](https://taxaro.de/wissen/zeitplan-e-rechnung-stufenweise-einfuehrung-fristen)

### XRechnung
- [KoSIT / XStandards Einkauf – Versionen](https://xeinkauf.de/xrechnung/versionen-und-bundles/)
- [KoSIT – XRechnung Portal](https://xeinkauf.de/xrechnung/)
- [GitHub – KoSIT Validator Configuration Releases](https://github.com/itplr-kosit/validator-configuration-xrechnung/releases)
- [E-Rechnung-Bund – XRechnung 3.0.1](https://e-rechnung-bund.de/en/new-version-xrechnung-standard-3-0-1-available/)
- [Ad-Hoc-News – XRechnung 3.0.2](https://www.ad-hoc-news.de/boerse/news/ueberblick/xrechnung-3-0-2-der-finale-standard-fuer-die-e-rechnung-pflicht/68433524)
- [ecosio – Leitweg-ID](https://ecosio.com/de/blog/was-ist-eine-leitweg-id/)
- [E-Rechnung-Bund – FAQ Leitweg-ID](https://www.e-rechnung-bund.de/faq/leitweg-id/)

### ZUGFeRD
- [FeRD – ZUGFeRD 2.4 Download](https://www.ferd-net.de/en/downloads/publications/details/zugferd-24-english)
- [ZUGFeRD Community – ZUGFeRD 2.4 Release](https://www.zugferd-community.net/en/blog/2025-12-05-ferd_veroeffentlicht_zugferd_2_4_factur-x_1_08)
- [Seeburger – ZUGFeRD 2.3](https://blog.seeburger.com/france-and-germany-publish-their-new-version-of-the-joint-standard-for-electronic-invoicing-zugferd-2-3-and-factur-x-1-0-07-from-ferd-and-fnfe-mpe/)
- [Invoice-Converter – XRechnung & ZUGFeRD 2026](https://www.invoice-converter.com/en/blog/xrechnung-zugferd-2026)

### EN 16931 & Formvergleich
- [mind-forms.de – ZUGFeRD und XRechnung CII/UBL](https://mind-forms.de/e-rechnung/zugferd-und-xrechnung-cii-und-ubl-technisch-verschieden-aber-trotzdem-gleich/)
- [treuz.de – ZUGFeRD, XRechnung, UBL, CII Vergleich](https://www.treuz.de/2024/12/31/10-zugferd-oder-xrechnung-ubl-oder-cii/)
- [B.i.Team – Norm EN 16931](https://www.biteam.de/magazin/norm-en-16931)
- [N4 – Semantik und Syntax der E-Rechnung](https://n4.de/blog/die-struktur-der-e-rechnung/)

### PEPPOL
- [primeXchange – E-Rechnung und Peppol in Deutschland](https://primexchange.de/wissen/e-rechnung-in-die-welt/e-rechnung-und-peppol-in-deutschland)
- [E-Rechnung-Bund – PEPPOL Übertragungsweg](https://e-rechnung-bund.de/en/transmission-methods/peppol/)
- [Seeburger – Peppol BIS Billing 3.0 und XRechnung austauschbar](https://blog.seeburger.com/peppol-bis-billing-3-0-and-xrechnung-interchangeable-within-germany/)
- [Storecove – E-Invoicing in Germany 2025-2026](https://www.storecove.com/blog/en/e-invoicing-in-germany/)

### Open-Source-Projekte
- [Mustangproject – mustangproject.org](https://www.mustangproject.org/)
- [GitHub – ZUGFeRD/mustangproject](https://github.com/ZUGFeRD/mustangproject)
- [GitHub – pretix/python-drafthorse](https://github.com/pretix/python-drafthorse)
- [PyPI – drafthorse](https://pypi.org/project/drafthorse/)
- [GitHub – akretion/factur-x](https://github.com/akretion/factur-x)
- [PyPI – factur-x](https://pypi.org/project/factur-x/)
- [GitHub – invoice-x/invoice2data](https://github.com/invoice-x/invoice2data)
- [GitHub – itplr-kosit/validator](https://github.com/itplr-kosit/validator)
- [GitHub – drbrnn/XFakturist](https://github.com/drbrnn/XFakturist)
- [GitHub – itplr-kosit/xrechnung-visualization](https://github.com/itplr-kosit/xrechnung-visualization)
- [GitHub – itplr-kosit/xrechnung-testsuite](https://github.com/itplr-kosit/xrechnung-testsuite)
- [GitHub – zfutura/pycheval](https://github.com/zfutura/pycheval)
- [GitHub – ZUGFeRD/corpus](https://github.com/ZUGFeRD/corpus)
- [GitHub – jcthiele/OpenXRechnungToolbox](https://github.com/jcthiele/OpenXRechnungToolbox)
- [GitHub – gflohr/e-invoice-eu](https://github.com/gflohr/e-invoice-eu)
- [GitHub – invinet/python-en16931](https://github.com/invinet/python-en16931)
- [GitHub – lka/excel2zugferd](https://github.com/lka/excel2zugferd)

### Technologie-Vergleiche
- [JetBrains – Django vs Flask vs FastAPI](https://blog.jetbrains.com/pycharm/2025/02/django-flask-fastapi/)
- [BuildSmart – Django vs FastAPI vs Flask Decision Matrix 2025](https://buildsmartengineering.substack.com/p/django-vs-fastapi-vs-flask-the-2025)
- [Medium – 7 Python PDF Extractors Tested (2025)](https://onlyoneaman.medium.com/i-tested-7-python-pdf-extractors-so-you-dont-have-to-2025-edition-c88013922257)
- [GitHub – jsvine/pdfplumber](https://github.com/jsvine/pdfplumber)
- [binary-butterfly – Factur-X/ZUGFeRD mit Python](https://binary-butterfly.de/artikel/factur-x-zugferd-e-invoices-with-python/)
- [Koncile – Claude vs GPT vs Gemini: Invoice Extraction](https://www.koncile.ai/en/ressources/claude-gpt-or-gemini-which-is-the-best-llm-for-invoice-extraction)
- [Extend.ai – PyTesseract Guide: OCR Limits & Alternatives](https://www.extend.ai/resources/pytesseract-guide-ocr-limits-alternatives)
