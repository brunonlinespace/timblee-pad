#!/usr/bin/env python3
"""Dependency-free regressions for Timblee Pad document profiles and templates."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from timblee_pad.document_profiles import (
    DOCUMENT_TYPE_ORDER,
    document_type_for_path,
    document_type_for_suffix,
    extension_matches_type,
    profile_for_key,
)
from timblee_pad.library_catalog import NON_HTML_LIBRARY
from timblee_pad.templates import (
    BUILTIN_TEMPLATES,
    CURSOR_MARKER,
    MAX_CUSTOM_TEMPLATES,
    default_template_id,
    normalise_custom_templates,
)


class DocumentProfileTests(unittest.TestCase):
    def test_profile_order_and_suffix_detection(self) -> None:
        self.assertEqual(DOCUMENT_TYPE_ORDER, ("html", "css", "xml"))
        expected = {
            ".html": "html", ".htm": "html", ".css": "css",
            ".xml": "xml", ".xsd": "xml", ".xsl": "xml", ".xslt": "xml",
        }
        for suffix, key in expected.items():
            with self.subTest(suffix=suffix):
                self.assertEqual(document_type_for_suffix(suffix), key)
                self.assertTrue(extension_matches_type(f"example{suffix}", key))
        self.assertEqual(document_type_for_path("UPPER.XML"), "xml")
        self.assertIsNone(document_type_for_suffix(".js"))
        self.assertIsNone(document_type_for_suffix(".svg"))

    def test_profiles_are_lightweight_and_preview_policy_is_explicit(self) -> None:
        self.assertTrue(profile_for_key("html").previewable)
        self.assertFalse(profile_for_key("css").previewable)
        self.assertTrue(profile_for_key("xml").previewable)

    def test_builtin_templates_cover_each_language_and_xml_is_well_formed(self) -> None:
        by_id = {item.template_id: item for item in BUILTIN_TEMPLATES}
        for required in (
            "html:blank", "html:html5", "css:blank", "css:basic",
            "xml:blank", "xml:basic",
        ):
            self.assertIn(required, by_id)
        self.assertEqual(default_template_id("html"), "html:html5")
        self.assertEqual(default_template_id("css"), "css:basic")
        self.assertEqual(default_template_id("xml"), "xml:basic")
        for required in ("xml:basic",):
            text = by_id[required].content.replace(CURSOR_MARKER, "")
            ET.fromstring(text)

    def test_custom_template_normalisation_is_bounded(self) -> None:
        items = normalise_custom_templates([
            {"id": "user:1", "name": "Lab Batch", "language": "xml", "content": "<batch>[[cursor]]</batch>"},
            {"id": "bad-language", "name": "Nope", "language": "javascript", "content": "x"},
        ])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].language, "xml")
        excessive = [
            {"id": f"user:{i}", "name": f"T{i}", "language": "xml", "content": "<r/>"}
            for i in range(MAX_CUSTOM_TEMPLATES + 10)
        ]
        self.assertEqual(len(normalise_custom_templates(excessive)), MAX_CUSTOM_TEMPLATES)

    def test_non_html_library_catalogues_are_namespaced(self) -> None:
        self.assertEqual(set(NON_HTML_LIBRARY), {"css", "xml"})
        for language, specs in NON_HTML_LIBRARY.items():
            self.assertTrue(specs)
            self.assertTrue(all(spec.key.startswith(f"{language}:") for spec in specs))


if __name__ == "__main__":
    unittest.main()
