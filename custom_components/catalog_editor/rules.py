"""The rules of every catalog the editor handles, behind one interface.

Each catalog repository owns the rules of its entries and copies them here with
its `sync_client.py`: `catalog_rules.py` (reeftech-catalog),
`house_catalog_rules.py` (house-catalog) and `reeftank_catalog_rules.py`
(reeftank-catalog). They share an interface; a kind of entry belongs to one of
them, and the rest of the editor only imports this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

from . import catalog_rules as reef
from . import house_catalog_rules as house
from . import reeftank_catalog_rules as reeftank

#: Languages of the catalogs of reeftech and house-catalog, visuals and their limits
KNOWN_LANGS = reef.KNOWN_LANGS
ASSET_FILES = reef.ASSET_FILES
#: Every language any catalog is written in (reeftank adds Dutch)
ALL_LANGS = tuple(dict.fromkeys((*reef.KNOWN_LANGS, *reeftank.KNOWN_LANGS)))
Report = reef.Report

#: Descriptor file and folder, in its repository, of each kind of entry
DESCRIPTORS: dict[str, str] = {
    **reef.DESCRIPTORS,
    **house.DESCRIPTORS,
    **reeftank.DESCRIPTORS,
}
FOLDERS: dict[str, str] = {**reef.FOLDERS, **house.FOLDERS, **reeftank.FOLDERS}

#: Kinds of the house catalog (trees, objects, pond_fish)
HOUSE_KINDS = frozenset(house.DESCRIPTORS)
#: Kinds of the reeftank catalog (fish, coral, plant, invertebrate)
REEFTANK_KINDS = frozenset(reeftank.DESCRIPTORS)


def rules_of(kind: str) -> ModuleType:
    """The rules module a kind of entry belongs to."""
    if kind in HOUSE_KINDS:
        return house
    return reeftank if kind in REEFTANK_KINDS else reef


def asset_files(kind: str) -> dict[str, int]:
    """The visuals the entries of a kind may have next to their descriptor, with their limits."""
    return rules_of(kind).ASSET_FILES


def languages(kind: str) -> tuple[str, ...]:
    """The languages the texts of a kind of entry are written in."""
    return tuple(rules_of(kind).KNOWN_LANGS)


def hidden_keys(kind: str) -> tuple[str, ...]:
    """Descriptor keys the editor keeps as they are and does not show.

    Fixed values it writes itself, and what the pictures of an entry are made of.
    """
    module = rules_of(kind)
    return (*getattr(module, "FIXED_KEYS", ()), *getattr(module, "PICTURE_KEYS", ()))


def complete(kind: str, data: dict[str, Any]) -> dict[str, Any]:
    """A draft with the keys of fixed value the form does not ask for."""
    with_fixed = getattr(rules_of(kind), "with_fixed", None)
    return with_fixed(kind, data) if with_fixed else data


def load_validators(schema_dir: Path) -> dict[str, Any]:
    """One validator per kind, from the schemas of a release (same for every catalog)."""
    return reef.load_validators(schema_dir)


def validate_draft(
    kind: str,
    entry_id: str,
    data: dict[str, Any],
    files: Mapping[str, int],
    ctx: Any,
    validators: Mapping[str, Any],
) -> Any:
    """Everything the CI of its catalog checks about one entry (errors, warnings)."""
    return rules_of(kind).validate_draft(kind, entry_id, data, files, ctx, validators)
