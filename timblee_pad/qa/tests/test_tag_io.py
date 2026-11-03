#!/usr/bin/env python3
"""Regression tests for Timblee Pad tag collection import/export."""

from __future__ import annotations

import json
import unittest

from timblee_pad.tag_io import (
    TAG_COLLECTION_FORMAT,
    TAG_COLLECTION_VERSION,
    TagCollectionError,
    build_tag_collection,
    parse_tag_collection,
)


class TagCollectionTests(unittest.TestCase):
    def test_round_trip_normalizes_custom_tags_and_favourites(self) -> None:
        collection = build_tag_collection(
            ["my-card", "MY-WIDGET", "my-card"],
            ["h1", "MY-WIDGET", "missing-tag"],
        )
        self.assertEqual(collection["format"], TAG_COLLECTION_FORMAT)
        self.assertEqual(collection["version"], TAG_COLLECTION_VERSION)
        self.assertEqual(collection["custom_tags"], ["my-card", "my-widget"])
        self.assertEqual(collection["favourites"], ["h1", "my-widget"])

        custom, favourites = parse_tag_collection(json.dumps(collection))
        self.assertEqual(custom, ["my-card", "my-widget"])
        self.assertEqual(favourites, {"h1", "my-widget"})

    def test_builtin_tags_are_not_duplicated_as_custom(self) -> None:
        collection = build_tag_collection(["section", "site-card"], ["section"])
        self.assertEqual(collection["custom_tags"], ["site-card"])
        self.assertEqual(collection["favourites"], ["section"])

    def test_invalid_or_unrelated_json_is_rejected(self) -> None:
        with self.assertRaises(TagCollectionError):
            parse_tag_collection("[]")
        with self.assertRaises(TagCollectionError):
            parse_tag_collection('{"format":"something-else","version":1}')
        with self.assertRaises(TagCollectionError):
            parse_tag_collection(
                json.dumps(
                    {
                        "format": TAG_COLLECTION_FORMAT,
                        "version": TAG_COLLECTION_VERSION,
                        "custom_tags": ["bad tag"],
                        "favourites": [],
                    }
                )
            )

    def test_unknown_favourite_is_ignored_for_forward_compatibility(self) -> None:
        custom, favourites = parse_tag_collection(
            json.dumps(
                {
                    "format": TAG_COLLECTION_FORMAT,
                    "version": TAG_COLLECTION_VERSION,
                    "custom_tags": [],
                    "favourites": ["future-html-tag", "p"],
                }
            )
        )
        self.assertEqual(custom, [])
        self.assertEqual(favourites, {"p"})


if __name__ == "__main__":
    unittest.main()
