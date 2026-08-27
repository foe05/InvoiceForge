"""Tests for CII-XML generation (drafthorse).

The note path is covered explicitly: `sample_invoice` carries no note, so
every other test in the suite skips that branch entirely.
"""

from __future__ import annotations

from lxml import etree

from app.core.generation.cii_generator import CIIGenerator

NS_RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"


def test_generate_without_note(sample_invoice):
    xml = CIIGenerator(sample_invoice).generate()
    assert xml.startswith(b"<?xml")
    assert b"CrossIndustryInvoice" in xml


def test_generate_with_note_emits_included_note(sample_invoice):
    """Regression: IncludedNote.content is a StringField, not a Container.

    Calling `.add()` on it raised
    "'StringElement' object has no attribute 'add'" for every invoice that
    carried a note — which is any invoice whose extractor fills BT-22.
    """
    sample_invoice.note = "Lieferung erfolgte am 10.08.2026. Zahlbar ohne Abzug."

    xml = CIIGenerator(sample_invoice).generate()

    root = etree.fromstring(xml)
    notes = root.findall(f".//{{{NS_RAM}}}IncludedNote")
    assert len(notes) == 1

    content = notes[0].find(f"{{{NS_RAM}}}Content")
    assert content is not None
    assert content.text == sample_invoice.note


def test_note_with_special_characters_is_escaped(sample_invoice):
    sample_invoice.note = 'Rabatt < 5% & "Sonderpreis" für Käufer'

    xml = CIIGenerator(sample_invoice).generate()

    root = etree.fromstring(xml)
    content = root.find(f".//{{{NS_RAM}}}IncludedNote/{{{NS_RAM}}}Content")
    assert content is not None
    assert content.text == sample_invoice.note
