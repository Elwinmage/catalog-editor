"""The catalogs the editor handles besides the one of the catalog client.

The client (`catalog_pack.py`, from reeftech-catalog) only knows the sections of
its own repository. Another catalog describes itself in a module its repository
copies here (`house_catalog_sections.py` for house-catalog, `reeftank_catalog_
sections.py` for reeftank-catalog: its repository, its sections, the layout of
their entries), and the editor declares those sections to the client, once, when
its package is imported. Everything else follows: downloads, shared pack, user
layer, and the repository a pull request goes to.

The releases of reeftank-catalog are not published per section (see
reeftank_pack.py): the client that downloads them is replaced here.
"""

from __future__ import annotations

from . import catalog_runtime
from . import house_catalog_sections as house
from . import reeftank_catalog_sections as reeftank
from .catalog_pack import register_section
from .reeftank_pack import pack_client

#: section -> {kind: (folder, descriptor)} of the catalogs declared here
EXTERNAL_SECTIONS: dict[str, dict[str, tuple[str, str]]] = {
    **house.SECTIONS,
    **reeftank.SECTIONS,
}
#: Their kinds of entries
EXTERNAL_KINDS: tuple[str, ...] = tuple(
    kind for kinds in EXTERNAL_SECTIONS.values() for kind in kinds
)

for _section, _kinds in house.SECTIONS.items():
    register_section(_section, _kinds, house.REPO)
for _section, _kinds in reeftank.SECTIONS.items():
    register_section(_section, _kinds, reeftank.REPO)

# The shared pack of a section builds its client with this name (this copy of the
# module is the editor's own): it gets the reader of reeftank-catalog for its sections
catalog_runtime.PackClient = pack_client  # type: ignore[misc,assignment]
