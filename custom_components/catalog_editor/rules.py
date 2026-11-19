"""The rules of every catalog the editor handles, behind one interface.

Each catalog repository owns the rules of its entries and copies them here with
its `sync_client.py`: `catalog_rules.py` (reeftech-catalog) and
`house_catalog_rules.py` (house-catalog). They share an interface; a kind of
entry belongs to one of them, and the rest of the editor only imports this
module.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

from . import catalog_rules as reef
from . import house_catalog_rules as house

#: Common to the catalogs: languages, visuals and their size limits
KNOWN_LANGS = reef.KNOWN_LANGS
ASSET_FILES = reef.ASSET_FILES
Report = reef.Report

#: Descriptor file and folder, in its repository, of each kind of entry
DESCRIPTORS: dict[str, str] = {**reef.DESCRIPTORS, **house.DESCRIPTORS}
FOLDERS: dict[str, str] = {**reef.FOLDERS, **house.FOLDERS}

#: Kinds of the house catalog (trees, objects)
HOUSE_KINDS = frozenset(house.DESCRIPTORS)


def rules_of(kind: str) -> ModuleType:
    """The rules module a kind of entry belongs to."""
    return house if kind in HOUSE_KINDS else reef


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
