"""The merged catalog of the integrations, as the editor sees it.

The editor never reads the catalog from the network: the integrations that
consume a section (maintenance_hub, redsea...) keep it up to date and merged
with the user layers, and the editor asks them. Drafts are checked against that
view, and entries that come from a release are edited as local overrides.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .catalog_rules import Context
from .catalog_runtime import CatalogUpdater, get_updater
from .const import PROVIDERS, VIEW_GROUPS, VIEW_KEYS


def provider(hass: HomeAssistant, section: str) -> CatalogUpdater | None:
    """The first loaded integration reading a section, or None.

    An integration keeps one catalog: it counts for the section it reads only
    (redsea reads the supplements, not the parameters).
    """
    for domain in PROVIDERS[section]:
        updater = get_updater(hass, domain)
        if updater is not None and updater.spec.section == section:
            return updater
    return None


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


def _group(
    view: dict[str, Any], kind: str, exclude: tuple[str, str] | None
) -> dict[str, dict[str, Any]]:
    entries = view.get(VIEW_GROUPS[kind], {})
    return {
        entry_id: strip_entry(kind, entry, view)
        for entry_id, entry in entries.items()
        if exclude != (kind, entry_id)
    }


def build_context(
    view: dict[str, Any],
    section: str,
    exclude: tuple[str, str] | None = None,
    parameters: dict[str, dict[str, Any]] | None = None,
) -> Context:
    """What a draft is checked against; `exclude` leaves out the entry it replaces.

    `parameters` are the ones of the parameters catalog, which a water test is
    checked against (empty: the test is not cross-checked).
    """
    if section == "equipment":
        return Context(
            tasks=_group(view, "task", exclude),
            categories=_group(view, "category", exclude),
        )
    if section == "supplements":
        return Context(supplements=_group(view, "supplement", exclude))
    if section == "water_tests":
        return Context(
            water_tests=_group(view, "water_test", exclude),
            parameters=dict(parameters or {}),
        )
    return Context(parameters=_group(view, "parameter", exclude))


def entry_label(kind: str, entry_id: str, data: dict[str, Any]) -> str:
    """A name to show for an entry."""
    if kind == "supplement":
        return str(data.get("fullname") or entry_id)
    if kind == "water_test":
        return f"{data.get('brand', '')} {data.get('name', '')}".strip() or entry_id
    name = data.get("name")
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
            "image": entry.get("image"),
            "thumb": entry.get("thumb"),
        }
        for entry_id, entry in sorted(view.get(VIEW_GROUPS[kind], {}).items())
    ]


def locate_visual(
    updater: CatalogUpdater, entry: dict[str, Any], key: str
) -> Path | None:
    """The file behind the `image` or `thumb` URL of an entry of the view."""
    url = entry.get(key)
    if not url:
        return None
    path = str(url).split("?", 1)[0]
    for layer in updater._layers():  # the folders the view was read from
        prefix = layer.url + "/"
        if path.startswith(prefix):
            root = layer.root.resolve()
            candidate = (root / path[len(prefix) :]).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return candidate
    return None
