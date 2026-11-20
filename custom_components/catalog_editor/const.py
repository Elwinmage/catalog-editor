"""Constants of the Catalog editor."""

from __future__ import annotations

from .catalogs import EXTERNAL_SECTIONS

DOMAIN = "catalog_editor"

#: Client id of the GitHub OAuth App (device flow enabled) used to sign in
CONF_CLIENT_ID = "client_id"

#: Image model the editor asks for the photo of a species (options; all optional):
#: the provider, the contributor's own API key and a model other than the default
CONF_IMAGE_PROVIDER = "image_provider"
CONF_IMAGE_KEY = "image_key"
CONF_IMAGE_MODEL = "image_model"

#: Sections of the catalog the editor subscribes to (option; all by default)
CONF_SECTIONS = "sections"

#: Sections of the catalog, and the kinds of entries each one holds. A kind is
#: the one of catalog_rules (`task`), which the pack calls `tasks`.
SECTION_KINDS: dict[str, tuple[str, ...]] = {
    "equipment": ("item", "category", "task"),
    "supplements": ("supplement",),
    "parameters": ("parameter",),
    "water_tests": ("water_test",),
    # the catalogs declared in catalogs.py (house-catalog: trees, objects)
    **{section: tuple(kinds) for section, kinds in EXTERNAL_SECTIONS.items()},
}

#: Group of the merged view (catalog_pack.build_view) holding each kind
VIEW_GROUPS = {
    "task": "tasks",
    "category": "categories",
    "item": "items",
    "supplement": "items",
    "parameter": "items",
    "water_test": "items",
    # a kind of a declared catalog is listed under the name of its folder
    **{
        kind: folder
        for kinds in EXTERNAL_SECTIONS.values()
        for kind, (folder, _) in kinds.items()
    },
}

#: Where the visuals of the user layer are served: <url>/<section>/...
USER_URL = f"/{DOMAIN}/user"

#: Keys the merged view adds to an entry; never part of its descriptor
VIEW_KEYS = ("image", "thumb", "source")

#: Uploaded visuals wait here (in memory) until the entry is saved
UPLOAD_TTL_S = 15 * 60
MAX_UPLOADS = 20
