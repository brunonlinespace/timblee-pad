# Timblee Pad
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable import/export format for Timblee Pad user tag collections."""

from __future__ import annotations

import json
from typing import Any, Iterable

from timblee_pad.html_tags import TAG_BY_KEY, custom_tag

TAG_COLLECTION_FORMAT = "timblee-pad-tag-collection"
TAG_COLLECTION_VERSION = 1
MAX_CUSTOM_TAGS = 200
MAX_FAVOURITES = 500
MAX_TAG_NAME_LENGTH = 128


class TagCollectionError(ValueError):
    """Raised when an imported tag collection is malformed or unsupported."""


def _clean_custom_names(values: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        if not isinstance(value, str) or len(value) > MAX_TAG_NAME_LENGTH:
            raise TagCollectionError("Custom tag names must be short text values.")
        try:
            spec = custom_tag(value)
        except ValueError as error:
            raise TagCollectionError(f"Invalid custom tag {value!r}: {error}") from error
        if spec.key in TAG_BY_KEY:
            # Built-in HTML tags do not need to be duplicated as custom tags.
            continue
        if spec.key not in cleaned:
            cleaned.append(spec.key)
        if len(cleaned) > MAX_CUSTOM_TAGS:
            raise TagCollectionError(
                f"A tag collection may contain at most {MAX_CUSTOM_TAGS} custom tags."
            )
    cleaned.sort(key=str.casefold)
    return cleaned


def _clean_favourites(values: Iterable[str], custom_names: set[str]) -> set[str]:
    cleaned: set[str] = set()
    for value in values:
        if not isinstance(value, str) or len(value) > MAX_TAG_NAME_LENGTH:
            raise TagCollectionError("Favourite tag names must be short text values.")
        folded = value.strip().casefold()
        if not folded:
            continue
        # Unknown names are ignored for forward compatibility. A future built-in
        # tag can therefore travel through an older Timblee Pad without making the
        # whole collection unreadable.
        if folded not in TAG_BY_KEY and folded not in custom_names:
            continue
        cleaned.add(folded)
        if len(cleaned) > MAX_FAVOURITES:
            raise TagCollectionError(
                f"A tag collection may contain at most {MAX_FAVOURITES} favourites."
            )
    return cleaned


def build_tag_collection(
    custom_tag_names: Iterable[str], favourite_tags: Iterable[str]
) -> dict[str, Any]:
    """Return a normalized, versioned JSON-compatible tag collection."""
    custom_names = _clean_custom_names(custom_tag_names)
    favourites = _clean_favourites(favourite_tags, set(custom_names))
    return {
        "format": TAG_COLLECTION_FORMAT,
        "version": TAG_COLLECTION_VERSION,
        "application": "Timblee Pad",
        "custom_tags": custom_names,
        "favourites": sorted(favourites, key=str.casefold),
    }


def parse_tag_collection(payload: bytes | str) -> tuple[list[str], set[str]]:
    """Validate and normalize a serialized Timblee Pad tag collection."""
    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise TagCollectionError("Tag collections must be UTF-8 JSON files.") from error
    else:
        text = payload

    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise TagCollectionError(f"Invalid JSON: {error.msg}.") from error
    if not isinstance(data, dict):
        raise TagCollectionError("The tag collection root must be a JSON object.")
    if data.get("format") != TAG_COLLECTION_FORMAT:
        raise TagCollectionError("This is not a Timblee Pad tag collection.")
    if data.get("version") != TAG_COLLECTION_VERSION:
        raise TagCollectionError(
            f"Unsupported tag collection version: {data.get('version')!r}."
        )

    custom_values = data.get("custom_tags", [])
    favourite_values = data.get("favourites", [])
    if not isinstance(custom_values, list):
        raise TagCollectionError("'custom_tags' must be a JSON array.")
    if not isinstance(favourite_values, list):
        raise TagCollectionError("'favourites' must be a JSON array.")

    custom_names = _clean_custom_names(custom_values)
    favourites = _clean_favourites(favourite_values, set(custom_names))
    return custom_names, favourites
