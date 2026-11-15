"""Constants of the ReefTech catalog editor."""

from __future__ import annotations

DOMAIN = "reeftech_catalog_editor"

#: Client id of the GitHub OAuth App (device flow enabled) used to sign in
CONF_CLIENT_ID = "client_id"

#: Sections of the catalog, and the kinds of entries each one holds. A kind is
#: the one of catalog_rules (`task`), which the pack calls `tasks`.
SECTION_KINDS: dict[str, tuple[str, ...]] = {
    "equipment": ("task", "category", "item"),
    "supplements": ("supplement",),
    "parameters": ("parameter",),
}

#: Group of the merged view (catalog_pack.build_view) holding each kind
VIEW_GROUPS = {
    "task": "tasks",
    "category": "categories",
    "item": "items",
    "supplement": "items",
    "parameter": "items",
}

#: Integrations reading each section; the first one loaded provides the merged
#: view the editor shows and checks drafts against (maintenance_hub keeps every
#: scope, reef_maintenance only the aquarium ones).
PROVIDERS: dict[str, tuple[str, ...]] = {
    "equipment": ("maintenance_hub", "reef_maintenance"),
    "supplements": ("redsea",),
    "parameters": ("reeftank", "redsea"),
}

#: Keys the merged view adds to an entry; never part of its descriptor
VIEW_KEYS = ("image", "thumb", "source")

#: Uploaded visuals wait here (in memory) until the entry is saved
UPLOAD_TTL_S = 15 * 60
MAX_UPLOADS = 20
