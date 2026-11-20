"""What the JSON Schemas cannot say about the form of each kind of entry.

Widgets come from the schemas themselves (type, enum, bounds, shared
definitions). Only what a schema cannot express is listed here: which fields
point to another entry, how an id is suggested, which kinds have a visual.
"""

from __future__ import annotations

from .catalogs import EXTERNAL_KINDS
from .reeftank_catalog_rules import DESCRIPTORS as SPECIES

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
    # an entry of a declared catalog (catalogs.py) is named after its English name
    **{kind: ("name.en",) for kind in EXTERNAL_KINDS},
    # a species is named after its scientific name (see forms.species_id)
    **dict.fromkeys(SPECIES, ("scientific",)),
}

#: Kinds whose id is the scientific name, written `genus_species`
SPECIES_KINDS = frozenset(SPECIES)

#: Field holding the brand of the kinds that have one: chosen among the brands
#: of the catalogs (a brand keeps its spelling), or a new one
BRAND_FIELD = {"item": "brand", "supplement": "brand", "water_test": "brand"}

#: Kinds whose degraded atlas the editor makes from a photo (a fish seen from the side)
ATLAS_KINDS = ("fish",)

#: Kinds that have a visual (image.webp and thumb.webp next to the descriptor)
HAS_VISUAL = {
    "task": False,
    "category": True,
    "item": True,
    "supplement": True,
    "parameter": True,
    "water_test": True,
    **dict.fromkeys(EXTERNAL_KINDS, True),
    # the pictures of a species are an atlas built by the tools of its catalog
    **dict.fromkeys(SPECIES, False),
}
