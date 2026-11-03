# Timblee Pad
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Built-in and user-editable document templates."""

from __future__ import annotations

from dataclasses import dataclass

CURSOR_MARKER = "[[cursor]]"
MAX_CUSTOM_TEMPLATES = 64
MAX_TEMPLATE_NAME = 96
MAX_TEMPLATE_CHARACTERS = 100_000


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    template_id: str
    language: str
    name: str
    content: str
    builtin: bool = True


BUILTIN_TEMPLATES: tuple[TemplateSpec, ...] = (
    TemplateSpec("html:blank", "html", "Blank HTML", ""),
    TemplateSpec(
        "html:html5",
        "html",
        "HTML5 Document",
        """<!doctype html>\n<html lang=\"en\">\n<head>\n    <meta charset=\"utf-8\">\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n    <title>[[cursor]]</title>\n</head>\n<body>\n\n</body>\n</html>\n""",
    ),
    TemplateSpec("css:blank", "css", "Blank Stylesheet", ""),
    TemplateSpec(
        "css:basic",
        "css",
        "Basic Stylesheet",
        """:root {\n    [[cursor]]\n}\n\n* {\n    box-sizing: border-box;\n}\n\nbody {\n    margin: 0;\n}\n""",
    ),
    TemplateSpec("xml:blank", "xml", "Blank XML", ""),
    TemplateSpec(
        "xml:basic",
        "xml",
        "Basic XML Document",
        """<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<root>\n    [[cursor]]\n</root>\n""",
    ),

)

BUILTIN_TEMPLATE_BY_ID = {spec.template_id: spec for spec in BUILTIN_TEMPLATES}


def default_template_id(language: str) -> str:
    preferred = {
        "html": "html:html5",
        "css": "css:basic",
        "xml": "xml:basic",
    }
    return preferred.get(language, f"{language}:blank")


def normalise_custom_templates(raw: object) -> list[TemplateSpec]:
    """Validate config JSON and return bounded custom templates."""
    if not isinstance(raw, list):
        return []
    result: list[TemplateSpec] = []
    seen: set[str] = set()
    for item in raw[:MAX_CUSTOM_TEMPLATES]:
        if not isinstance(item, dict):
            continue
        template_id = item.get("id")
        language = item.get("language")
        name = item.get("name")
        content = item.get("content")
        if (
            not isinstance(template_id, str)
            or not template_id.startswith("user:")
            or len(template_id) > 160
            or template_id in seen
            or not isinstance(language, str)
            or language not in {"html", "css", "xml"}
            or not isinstance(name, str)
            or not name.strip()
            or len(name) > MAX_TEMPLATE_NAME
            or not isinstance(content, str)
            or len(content) > MAX_TEMPLATE_CHARACTERS
        ):
            continue
        seen.add(template_id)
        result.append(
            TemplateSpec(template_id, language, name.strip(), content, builtin=False)
        )
    return result


def serialise_custom_templates(templates: list[TemplateSpec]) -> list[dict[str, str]]:
    return [
        {
            "id": spec.template_id,
            "language": spec.language,
            "name": spec.name,
            "content": spec.content,
        }
        for spec in templates
        if not spec.builtin
    ]
