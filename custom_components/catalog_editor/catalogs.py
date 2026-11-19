"""The catalogs the editor handles besides the one of the catalog client.

The client (`catalog_pack.py`, from reeftech-catalog) only knows the sections of
its own repository. Another catalog describes itself in a module its repository
copies here (`house_catalog_sections.py` for house-catalog: its repository, its
sections, the layout of their entries), and the editor declares those sections
to the client, once, when its package is imported. Everything else follows:
downloads, shared pack, user layer, and the repository a pull request goes to.
"""

from __future__ import annotations

from . import house_catalog_sections as house
from .catalog_pack import register_section

#: section -> {kind: (folder, descriptor)} of the catalogs declared here
EXTERNAL_SECTIONS: dict[str, dict[str, tuple[str, str]]] = dict(house.SECTIONS)
#: Their kinds of entries
EXTERNAL_KINDS: tuple[str, ...] = tuple(
    kind for kinds in EXTERNAL_SECTIONS.values() for kind in kinds
)

for _section, _kinds in house.SECTIONS.items():
    register_section(_section, _kinds, house.REPO)
