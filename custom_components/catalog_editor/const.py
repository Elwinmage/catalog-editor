"""Constants of the Catalog editor."""

from __future__ import annotations

DOMAIN = "catalog_editor"

#: Client id of the GitHub OAuth App (device flow enabled) used to sign in
CONF_CLIENT_ID = "client_id"

#: Sections of the catalog the editor subscribes to (option; all by default)
CONF_SECTIONS = "sections"

#: Sections of the catalog, and the kinds of entries each one holds. A kind is
#: the one of catalog_rules (`task`), which the pack calls `tasks`.
SECTION_KINDS: dict[str, tuple[str, ...]] = {
    "equipment": ("item", "category", "task"),
    "supplements": ("supplement",),
    "parameters": ("parameter",),
    "water_tests": ("water_test",),
}

#: Group of the merged view (catalog_pack.build_view) holding each kind
VIEW_GROUPS = {
    "task": "tasks",
    "category": "categories",
    "item": "items",
    "supplement": "items",
    "parameter": "items",
    "water_test": "items",
}

#: Where the visuals of the user layer are served: <url>/<section>/...
USER_URL = f"/{DOMAIN}/user"

#: Keys the merged view adds to an entry; never part of its descriptor
VIEW_KEYS = ("image", "thumb", "source")

#: Uploaded visuals wait here (in memory) until the entry is saved
UPLOAD_TTL_S = 15 * 60
MAX_UPLOADS = 20
