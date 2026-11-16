"""What the JSON Schemas cannot say about the form of each kind of entry.

Widgets come from the schemas themselves (type, enum, bounds, shared
definitions). Only what a schema cannot express is listed here: which fields
point to another entry, how an id is suggested, which kinds have a visual.
"""

from __future__ import annotations

#: Field path -> group of the merged view its value is chosen from. A path uses
#: dots for objects and `[]` for the items of an array.
REFS: dict[str, dict[str, str]] = {
    "category": {"maintenance[].task": "tasks"},
    "item": {"category": "categories", "maintenance[].task": "tasks"},
    "supplement": {"bundle[].part": "items"},
}

#: Fields an id is suggested from (dotted paths, joined in a slug)
ID_FROM: dict[str, tuple[str, ...]] = {
    "task": ("name.en",),
    "category": ("name.en",),
    "item": ("brand", "model"),
    "supplement": ("brand", "name"),
    "parameter": ("symbol",),
    "water_test": ("brand", "name"),
}

#: Kinds that have a visual (image.webp and thumb.webp next to the descriptor)
HAS_VISUAL = {
    "task": False,
    "category": True,
    "item": True,
    "supplement": True,
    "parameter": True,
    "water_test": True,
}
