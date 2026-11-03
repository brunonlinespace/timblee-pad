# Timblee Pad
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lightweight document-language profiles for Timblee Pad."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DocumentProfile:
    key: str
    label: str
    short_label: str
    extensions: tuple[str, ...]
    default_extension: str
    editor_language: str
    previewable: bool
    description: str


DOCUMENT_PROFILES: dict[str, DocumentProfile] = {
    "html": DocumentProfile(
        "html",
        "HTML Document",
        "HTML",
        (".html", ".htm"),
        ".html",
        "html",
        True,
        "HTML web document",
    ),
    "css": DocumentProfile(
        "css",
        "CSS Stylesheet",
        "CSS",
        (".css",),
        ".css",
        "css",
        False,
        "CSS stylesheet",
    ),
    "xml": DocumentProfile(
        "xml",
        "XML Document",
        "XML",
        (".xml", ".xsd", ".xsl", ".xslt"),
        ".xml",
        "xml",
        True,
        "XML structured document",
    ),
}

DOCUMENT_TYPE_ORDER = ("html", "css", "xml")
SUPPORTED_SOURCE_SUFFIXES = frozenset(
    suffix
    for key in DOCUMENT_TYPE_ORDER
    for suffix in DOCUMENT_PROFILES[key].extensions
)

SOURCE_FILE_FILTER = (
    "Timblee Source Files (*.html *.htm *.css *.xml *.xsd *.xsl *.xslt);;"
    "HTML Files (*.html *.htm);;CSS Files (*.css);;"
    "XML Files (*.xml *.xsd *.xsl *.xslt);;All Files (*)"
)


def profile_for_key(key: str) -> DocumentProfile:
    return DOCUMENT_PROFILES.get(key, DOCUMENT_PROFILES["html"])


def document_type_for_suffix(suffix: str) -> str | None:
    folded = (suffix or "").casefold()
    for key in DOCUMENT_TYPE_ORDER:
        if folded in DOCUMENT_PROFILES[key].extensions:
            return key
    return None


def document_type_for_path(path: str | Path) -> str | None:
    return document_type_for_suffix(Path(path).suffix)


def extension_matches_type(path: str | Path, document_type: str) -> bool:
    return Path(path).suffix.casefold() in profile_for_key(document_type).extensions
