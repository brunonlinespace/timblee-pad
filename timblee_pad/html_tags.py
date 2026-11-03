# Timblee Pad
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""HTML5 tag catalogue and insertion metadata for Timblee Pad."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class TagSpec:
    key: str
    label: str
    category: str
    opening: str
    closing: str
    description: str

    @property
    def is_void(self) -> bool:
        return not self.closing


HTML5_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Document</title>
</head>
<body>
    
</body>
</html>
"""


def _tag(
    key: str,
    category: str,
    description: str,
    *,
    opening: str | None = None,
    closing: str | None = None,
    label: str | None = None,
) -> TagSpec:
    opening = opening if opening is not None else f"<{key}>"
    closing = closing if closing is not None else f"</{key}>"
    return TagSpec(
        key=key,
        label=label or f"<{key}>",
        category=category,
        opening=opening,
        closing=closing,
        description=description,
    )


COMMON_HTML_TAGS: tuple[TagSpec, ...] = (
    _tag("html", "Document", "Root element for an HTML document."),
    _tag("head", "Document", "Container for document metadata."),
    _tag("title", "Document", "Document title shown by the browser."),
    _tag("body", "Document", "Container for visible page content."),
    _tag("meta", "Document", "Document metadata.", opening='<meta name="" content="">', closing=""),
    _tag("link", "Document", "External resource link, commonly a stylesheet.", opening='<link rel="stylesheet" href="">', closing=""),
    _tag("style", "Document", "Embedded CSS stylesheet."),
    _tag("script", "Document", "Embedded or linked script.", opening='<script src="">'),
    _tag("header", "Structure", "Introductory content for a page or section."),
    _tag("nav", "Structure", "Major navigation links."),
    _tag("main", "Structure", "Primary page content."),
    _tag("section", "Structure", "Thematic section of a document."),
    _tag("article", "Structure", "Self-contained article or composition."),
    _tag("aside", "Structure", "Tangential or supplementary content."),
    _tag("footer", "Structure", "Footer for a page or section."),
    _tag("div", "Structure", "Generic block-level container."),
    _tag("span", "Structure", "Generic inline container."),
    _tag("h1", "Text", "Top-level heading."),
    _tag("h2", "Text", "Second-level heading."),
    _tag("h3", "Text", "Third-level heading."),
    _tag("h4", "Text", "Fourth-level heading."),
    _tag("h5", "Text", "Fifth-level heading."),
    _tag("h6", "Text", "Sixth-level heading."),
    _tag("p", "Text", "Paragraph."),
    _tag("br", "Text", "Line break.", opening="<br>", closing=""),
    _tag("hr", "Text", "Thematic break / horizontal rule.", opening="<hr>", closing=""),
    _tag("strong", "Text", "Strong importance."),
    _tag("em", "Text", "Stress emphasis."),
    _tag("mark", "Text", "Highlighted or marked text."),
    _tag("small", "Text", "Side comments or small print."),
    _tag("sub", "Text", "Subscript text."),
    _tag("sup", "Text", "Superscript text."),
    _tag("code", "Text", "Inline code fragment."),
    _tag("pre", "Text", "Preformatted text."),
    _tag("blockquote", "Text", "Block quotation."),
    _tag("q", "Text", "Inline quotation."),
    _tag("a", "Links & Media", "Hyperlink.", opening='<a href="">'),
    _tag("img", "Links & Media", "Image.", opening='<img src="" alt="">', closing=""),
    _tag("picture", "Links & Media", "Responsive image container."),
    _tag("figure", "Links & Media", "Self-contained figure."),
    _tag("figcaption", "Links & Media", "Caption for a figure."),
    _tag("audio", "Links & Media", "Audio player.", opening='<audio controls>'),
    _tag("video", "Links & Media", "Video player.", opening='<video controls>'),
    _tag("source", "Links & Media", "Media or picture source.", opening='<source src="">', closing=""),
    _tag("ul", "Lists", "Unordered list."),
    _tag("ol", "Lists", "Ordered list."),
    _tag("li", "Lists", "List item."),
    _tag("dl", "Lists", "Description list."),
    _tag("dt", "Lists", "Description term."),
    _tag("dd", "Lists", "Description details."),
    _tag("table", "Tables", "Table."),
    _tag("caption", "Tables", "Table caption."),
    _tag("thead", "Tables", "Table header row group."),
    _tag("tbody", "Tables", "Table body row group."),
    _tag("tfoot", "Tables", "Table footer row group."),
    _tag("tr", "Tables", "Table row."),
    _tag("th", "Tables", "Table header cell."),
    _tag("td", "Tables", "Table data cell."),
    _tag("form", "Forms", "Form container.", opening='<form action="" method="post">'),
    _tag("label", "Forms", "Label for a form control.", opening='<label for="">'),
    _tag("input", "Forms", "Input control.", opening='<input type="text" name="">', closing=""),
    _tag("textarea", "Forms", "Multiline text input.", opening='<textarea name="">'),
    _tag("button", "Forms", "Clickable button.", opening='<button type="button">'),
    _tag("select", "Forms", "Selection list.", opening='<select name="">'),
    _tag("option", "Forms", "Option inside a select.", opening='<option value="">'),
    _tag("fieldset", "Forms", "Group of form controls."),
    _tag("legend", "Forms", "Caption for a fieldset."),
    _tag("details", "Interactive", "Expandable disclosure widget."),
    _tag("summary", "Interactive", "Visible summary for details."),
    _tag("dialog", "Interactive", "Dialog or modal container."),
    _tag("progress", "Interactive", "Progress indicator.", opening='<progress value="0" max="100">'),
    _tag("meter", "Interactive", "Scalar measurement.", opening='<meter value="0">'),
    _tag("canvas", "Graphics", "Scriptable bitmap canvas."),
    _tag("svg", "Graphics", "Inline SVG container.", opening='<svg viewBox="0 0 100 100">'),
    _tag("template", "Advanced", "Inert HTML fragment for later cloning."),
    # Extended current-HTML coverage. Existing built-ins above are intentionally
    # preserved verbatim; these entries fill out the modern non-obsolete set.
    _tag("base", "Document", "Base URL for relative URLs in the document.", opening='<base href="">', closing=""),
    _tag("noscript", "Document", "Fallback content when scripting is unavailable."),
    _tag("address", "Structure", "Contact information for a person, group or organisation."),
    _tag("hgroup", "Structure", "Heading grouped with secondary heading content."),
    _tag("search", "Structure", "Container for search or filtering controls."),
    _tag("abbr", "Text", "Abbreviation or acronym."),
    _tag("b", "Text", "Stylistically offset text without added importance."),
    _tag("bdi", "Text", "Isolate bidirectional text from surrounding directionality."),
    _tag("bdo", "Text", "Override bidirectional text direction.", opening='<bdo dir="rtl">'),
    _tag("cite", "Text", "Title of a creative work."),
    _tag("data", "Text", "Human-readable content paired with a machine-readable value.", opening='<data value="">'),
    _tag("del", "Text", "Text deleted from a document."),
    _tag("dfn", "Text", "Defining instance of a term."),
    _tag("i", "Text", "Text offset in an alternate voice or mood."),
    _tag("ins", "Text", "Text inserted into a document."),
    _tag("kbd", "Text", "User input such as a keyboard command."),
    _tag("rp", "Text", "Fallback parentheses for ruby annotations."),
    _tag("rt", "Text", "Ruby annotation text."),
    _tag("ruby", "Text", "Ruby annotation container."),
    _tag("s", "Text", "Text that is no longer accurate or relevant."),
    _tag("samp", "Text", "Sample output from a computer program."),
    _tag("time", "Text", "Machine-readable date or time.", opening='<time datetime="">'),
    _tag("u", "Text", "Unarticulated annotation such as a proper-name mark."),
    _tag("var", "Text", "Variable name in mathematical or programming context."),
    _tag("wbr", "Text", "Optional word-break opportunity.", opening="<wbr>", closing=""),
    _tag("area", "Links & Media", "Clickable area inside an image map.", opening='<area shape="rect" coords="" href="" alt="">', closing=""),
    _tag("embed", "Links & Media", "Embed external content.", opening='<embed src="" type="">', closing=""),
    _tag("iframe", "Links & Media", "Embed another browsing context.", opening='<iframe src="" title="">'),
    _tag("map", "Links & Media", "Image-map definition.", opening='<map name="">'),
    _tag("object", "Links & Media", "Embed an external resource.", opening='<object data="" type="">'),
    _tag("track", "Links & Media", "Timed text track for audio or video.", opening='<track kind="subtitles" src="" srclang="" label="">', closing=""),
    _tag("menu", "Lists", "Semantic list of commands or items."),
    _tag("col", "Tables", "Table column definition.", opening="<col>", closing=""),
    _tag("colgroup", "Tables", "Group of table columns."),
    _tag("datalist", "Forms", "Suggested values for an input control."),
    _tag("optgroup", "Forms", "Group of options inside a select.", opening='<optgroup label="">'),
    _tag("output", "Forms", "Result produced by a calculation or user action.", opening='<output name="">'),
    _tag("slot", "Advanced", "Placeholder inside a web component shadow tree.", opening='<slot name="">'),
    _tag("math", "Graphics", "Inline MathML container."),
)

TAG_BY_KEY = {spec.key: spec for spec in COMMON_HTML_TAGS}


TAG_CATEGORIES: tuple[str, ...] = tuple(
    dict.fromkeys(spec.category for spec in COMMON_HTML_TAGS)
) + ("Custom",)

ESSENTIAL_TAGS: tuple[tuple[str, str], ...] = (
    ("html", "Ctrl+1"),
    ("head", "Ctrl+2"),
    ("title", "Ctrl+3"),
    ("body", "Ctrl+4"),
    ("main", "Ctrl+5"),
    ("section", "Ctrl+6"),
    ("p", "Ctrl+7"),
    ("a", "Ctrl+8"),
    ("img", "Ctrl+9"),
    ("h1", "Ctrl+0"),
)

CUSTOM_TAG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9:._-]*$")


def custom_tag(name: str) -> TagSpec:
    """Build a paired custom-element specification after strict validation."""
    cleaned = name.strip().casefold()
    if not CUSTOM_TAG_RE.fullmatch(cleaned):
        raise ValueError("Tag names may contain letters, numbers, colon, dot, underscore and hyphen.")
    return _tag(cleaned, "Custom", "User-defined custom tag.")
