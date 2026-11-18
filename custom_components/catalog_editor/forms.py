"""Form models, derived from the JSON Schemas of the catalog.

The card is a plain renderer: this module turns the schema of a kind of entry
into a description of the form (fields, widgets, constraints) so that a new
field of the catalog shows up without touching the card. Shared definitions of
`common.schema.json` map to widgets (`i18n`, `scopes`, `icon`, `schedule`...);
other fields follow their JSON type.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from .catalog_rules import ASSET_FILES, KNOWN_LANGS
from .const import SECTION_KINDS
from .hints import BRAND_FIELD, HAS_VISUAL, ID_FROM, REFS

_DEF_RE = re.compile(r"#/\$defs/([A-Za-z0-9_]+)$")
#: Shared definitions that are a widget of their own
_WIDGETS = {
    "i18n": "i18n",
    "icon": "icon",
    "schedule": "schedule",
    "bounded_int": "bounded_int",
}
_CONSTRAINTS = (
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minItems",
    "uniqueItems",
)


def _resolve(
    node: dict[str, Any], common: dict[str, Any]
) -> tuple[dict[str, Any], str | None]:
    """The node with its `$ref` replaced by the shared definition, and its name."""
    ref = node.get("$ref")
    if ref is None:
        return node, None
    match = _DEF_RE.search(ref)
    name = match.group(1) if match else None
    target = common.get("$defs", {}).get(name, {}) if name else {}
    # What the node says on its own (a description, say) wins over the definition
    return {**target, **{k: v for k, v in node.items() if k != "$ref"}}, name


def _field(
    name: str,
    node: dict[str, Any],
    required: bool,
    path: str,
    refs: dict[str, str],
    common: dict[str, Any],
) -> dict[str, Any]:
    node, shared = _resolve(node, common)
    field: dict[str, Any] = {"name": name, "required": required}
    if "description" in node:
        field["description"] = node["description"]
    if "default" in node:
        field["default"] = node["default"]
    field.update({k: node[k] for k in _CONSTRAINTS if k in node})

    if path in refs:
        field["type"] = "ref"
        field["ref"] = refs[path]
    elif shared in _WIDGETS:
        field["type"] = _WIDGETS[shared]
        if shared == "i18n":
            field["languages"] = list(KNOWN_LANGS)
            field["required_languages"] = ["en"]
    elif shared == "id":
        field["type"] = "id"
    elif shared == "scopes":
        field["type"] = "multi_enum"
        field["options"] = _enum_of(node["items"], common)
    elif "enum" in node:
        field["type"] = "enum"
        field["options"] = list(node["enum"])
    elif node.get("type") == "array":
        field.update(_array(node, path, refs, common))
    elif node.get("type") == "object" and "properties" in node:
        field["type"] = "object"
        field["fields"] = _fields(node, path, refs, common)
    elif node.get("type") in ("string", "number", "integer", "boolean"):
        field["type"] = node["type"]
    else:
        # Nothing the card knows how to draw: edited as raw JSON
        field["type"] = "json"
    return field


def _enum_of(node: dict[str, Any], common: dict[str, Any]) -> list[Any]:
    node, _ = _resolve(node, common)
    return list(node.get("enum", []))


def _array(
    node: dict[str, Any], path: str, refs: dict[str, str], common: dict[str, Any]
) -> dict[str, Any]:
    items, shared = _resolve(node.get("items", {}), common)
    if "enum" in items:
        return {"type": "multi_enum", "options": list(items["enum"])}
    item_path = f"{path}[]"
    if item_path in refs:
        return {"type": "list", "item": {"type": "ref", "ref": refs[item_path]}}
    if shared == "task_ref" or items.get("type") == "object":
        return {
            "type": "list",
            "item": {
                "type": "object",
                "fields": _fields(items, item_path, refs, common),
            },
        }
    inner = _field("item", items, True, item_path, refs, common)
    inner.pop("name")
    inner.pop("required")
    return {"type": "list", "item": inner}


def _fields(
    node: dict[str, Any], path: str, refs: dict[str, str], common: dict[str, Any]
) -> list[dict[str, Any]]:
    node, _ = _resolve(node, common)
    required = set(node.get("required", []))
    return [
        _field(
            name,
            sub,
            name in required,
            f"{path}.{name}" if path else name,
            refs,
            common,
        )
        for name, sub in node.get("properties", {}).items()
    ]


def build_form(kind: str, schemas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Description of the form of a kind of entry (a key of `SECTION_KINDS`)."""
    schema = schemas[kind]
    common = schemas.get("common", {})
    section = next(s for s, kinds in SECTION_KINDS.items() if kind in kinds)
    fields = _fields(schema, "", REFS.get(kind, {}), common)
    for field in fields:
        if field["name"] == BRAND_FIELD.get(kind) and field["type"] == "string":
            field["type"] = "brand"
    return {
        "kind": kind,
        "section": section,
        "title": schema.get("title", kind),
        "description": schema.get("description"),
        "fields": fields,
        "id_from": list(ID_FROM[kind]),
        "has_visual": HAS_VISUAL[kind],
        "visual_limits": {
            "image": ASSET_FILES["image.webp"],
            "thumb": ASSET_FILES["thumb.webp"],
        },
    }


def slugify(*parts: str) -> str:
    """An id (lower case, `-` between words, 64 characters at most) from texts."""
    text = "-".join(part for part in parts if part)
    slug = re.sub(r"[^a-z0-9]+", "-", _ascii(text).lower()).strip("-")
    return slug[:64].strip("-")


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def value_at(data: dict[str, Any], path: str) -> str:
    """The text at a dotted path of a draft ('' when missing or not a text)."""
    node: Any = data
    for key in path.split("."):
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, str) else ""


def suggest_id(kind: str, data: dict[str, Any], taken: set[str]) -> str:
    """An id for a new entry, unique among the `taken` ones ('' when nothing to go on)."""
    base = slugify(*(value_at(data, path) for path in ID_FROM[kind]))
    if not base:
        return ""
    candidate, number = base, 2
    while candidate in taken:
        suffix = f"-{number}"
        candidate = base[: 64 - len(suffix)].strip("-") + suffix
        number += 1
    return candidate
