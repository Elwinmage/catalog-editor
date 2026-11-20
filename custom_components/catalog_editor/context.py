"""The merged catalog, as the editor sees it.

The view of a section is the shared pack the editor keeps up to date, merged with
the user layer (see source.py). Drafts are checked against that view, and
entries that come from a release are edited as local overrides.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from .catalog_pack import KIND_LAYOUT, Layer
from .catalog_rules import Context, brand_key
from .catalogs import EXTERNAL_SECTIONS
from .const import VIEW_GROUPS, VIEW_KEYS
from .rules import rules_of


def strip_entry(
    kind: str, entry: dict[str, Any], view: dict[str, Any]
) -> dict[str, Any]:
    """The descriptor of an entry of the merged view, as it is on disk.

    The view adds visuals and the layer it comes from; an item also takes the
    scopes of its category when it has none, which are not written back.
    """
    data = {key: value for key, value in entry.items() if key not in VIEW_KEYS}
    if kind == "item":
        category = view.get("categories", {}).get(data.get("category"), {})
        if data.get("scopes") == category.get("scopes"):
            data.pop("scopes", None)
    return data


def read_descriptor(
    source: HasLayers, kind: str, entry_id: str
) -> dict[str, Any] | None:
    """The descriptor of an entry as written in the most specific layer having it.

    The merged view overwrites the `source` field of an entry with the name of its
    layer, so a descriptor with a `source` of its own (a reference of a verified
    value) must be read from the disk to be edited without losing it.
    """
    folder, descriptor = KIND_LAYOUT["tasks" if kind == "task" else kind]
    for layer in reversed(source.layers()):
        path = (
            layer.root
            / folder
            / (f"{entry_id}.json" if descriptor is None else f"{entry_id}/{descriptor}")
        )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return None


#: What the card needs of a descriptor to play the animation of an atlas
ATLAS_FIELDS = ("frame", "columns", "clips", "facing", "degraded")


def read_atlas(
    source: HasLayers, kind: str, entry_id: str
) -> tuple[dict[str, Any], str] | None:
    """The animation of an entry: its descriptor keys and the URL of its atlas.

    From the most specific layer having the entry (the descriptor the form
    edits); None when that entry has no atlas file to play.
    """
    folder, descriptor = KIND_LAYOUT[kind]
    for layer in reversed(source.layers()):
        where = layer.root / folder / entry_id
        try:
            data = json.loads((where / str(descriptor)).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        atlas = data.get("atlas") if isinstance(data, dict) else None
        name = atlas.get("1x") if isinstance(atlas, dict) else None
        if (
            not isinstance(name, str)
            or "/" in name
            or not (where / name).is_file()
            or not all(field in data for field in ("frame", "columns", "clips"))
        ):
            return None
        info = {field: data[field] for field in ATLAS_FIELDS if field in data}
        return info, f"{layer.url}/{folder}/{entry_id}/{name}?v={layer.stamp}"
    return None


def _group(
    view: dict[str, Any], kind: str, exclude: tuple[str, str] | None
) -> dict[str, dict[str, Any]]:
    entries = view.get(VIEW_GROUPS[kind], {})
    return {
        entry_id: strip_entry(kind, entry, view)
        for entry_id, entry in entries.items()
        if exclude != (kind, entry_id)
    }


def external_context(
    view: dict[str, Any], section: str, exclude: tuple[str, str] | None = None
) -> Any:
    """What a draft of a declared catalog (house, reeftank) is checked against.

    The others of its section: the context of those rules has one group per
    section, named after it.
    """
    entries: dict[str, dict[str, Any]] = {}
    for kind in EXTERNAL_SECTIONS[section]:
        entries |= _group(view, kind, exclude)
    kind = next(iter(EXTERNAL_SECTIONS[section]))
    return rules_of(kind).Context(**{section: entries})


house_context = external_context


def build_context(
    view: dict[str, Any],
    section: str,
    exclude: tuple[str, str] | None = None,
    parameters: dict[str, dict[str, Any]] | None = None,
    brands: dict[str, str] | None = None,
) -> Context:
    """What a draft is checked against; `exclude` leaves out the entry it replaces.

    `parameters` are the ones of the parameters catalog, which a water test is
    checked against (empty: the test is not cross-checked).
    """
    if section == "equipment":
        return Context(
            tasks=_group(view, "task", exclude),
            categories=_group(view, "category", exclude),
            brands=dict(brands or {}),
        )
    if section == "supplements":
        return Context(
            supplements=_group(view, "supplement", exclude), brands=dict(brands or {})
        )
    if section == "water_tests":
        return Context(
            water_tests=_group(view, "water_test", exclude),
            parameters=dict(parameters or {}),
            brands=dict(brands or {}),
        )
    return Context(parameters=_group(view, "parameter", exclude))


def count_brands(
    views: Mapping[str, dict[str, Any]],
    exclude: tuple[str, str, str] | None = None,
) -> dict[str, Counter[str]]:
    """How each brand is written in the catalogs: key -> spelling -> entries.

    `views`: merged view by section. `exclude`: (section, kind, id) of the entry a
    draft replaces, which must not impose its old spelling on itself.
    """
    brands: dict[str, Counter[str]] = {}
    for section, view in views.items():
        for entry_id, entry in view.get("items", {}).items():
            brand = entry.get("brand")
            if not isinstance(brand, str) or not brand:
                continue
            if exclude and exclude[0] == section and exclude[2] == entry_id:
                continue
            brands.setdefault(brand_key(brand), Counter())[brand] += 1
    return brands


def preferred_spellings(counts: Mapping[str, Counter[str]]) -> dict[str, str]:
    """The spelling to keep for each brand: the most used, then the first by name."""
    return {
        key: min(spellings, key=lambda text: (-spellings[text], text))
        for key, spellings in counts.items()
    }


def entry_label(kind: str, entry_id: str, data: dict[str, Any]) -> str:
    """A name to show for an entry."""
    if kind == "supplement":
        return str(data.get("fullname") or entry_id)
    if kind == "water_test":
        return f"{data.get('brand', '')} {data.get('name', '')}".strip() or entry_id
    name = data.get("name") or data.get("names")
    if isinstance(name, dict) and name.get("en"):
        return str(name["en"])
    if kind == "item":
        return f"{data.get('brand', '')} {data.get('model', '')}".strip() or entry_id
    return entry_id


def list_entries(view: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """Entries of a kind, to choose from."""
    return [
        {
            "id": entry_id,
            "label": entry_label(kind, entry_id, entry),
            "source": entry.get("source"),
            "brand": entry.get("brand"),
            "category": entry.get("category"),
            "water_types": entry.get("water_types"),
            "image": entry.get("image"),
            "thumb": entry.get("thumb"),
        }
        for entry_id, entry in sorted(view.get(VIEW_GROUPS[kind], {}).items())
    ]


class HasLayers(Protocol):
    """Anything telling which folders a view was read from."""

    def layers(self) -> list[Layer]:
        """The folders the view is read from, least specific first."""
        ...


def locate_visual(source: HasLayers, entry: dict[str, Any], key: str) -> Path | None:
    """The file behind the `image` or `thumb` URL of an entry of the view."""
    url = entry.get(key)
    if not url:
        return None
    path = str(url).split("?", 1)[0]
    for layer in source.layers():  # the folders the view was read from
        prefix = layer.url + "/"
        if path.startswith(prefix):
            root = layer.root.resolve()
            candidate = (root / path[len(prefix) :]).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return candidate
    return None
