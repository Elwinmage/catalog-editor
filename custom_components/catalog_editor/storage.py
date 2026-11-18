"""The shared user layer: where the editor writes the entries of the user.

`<config>/reeftech_catalog/user/<section>/` has the layout of the section
(`items/<id>/item.json`, `image.webp`, `thumb.webp`; a task is the file
`tasks/<id>.json`). Every integration reading the section merges it with its
catalog (see doc/consumers.md of reeftech-catalog); a writer then sends
`SIGNAL_USER_CATALOG_CHANGED`. Blocking: call from an executor job.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .catalog_pack import KIND_LAYOUT, shared_user_parts
from .catalog_rules import DESCRIPTORS

_PACK_KINDS = {
    "task": "tasks",
    "category": "category",
    "item": "item",
    "supplement": "supplement",
    "parameter": "parameter",
    "water_test": "water_test",
}


def dump(data: dict[str, Any]) -> bytes:
    """A descriptor as it is written (readable, diff friendly)."""
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


class UserCatalog:
    """Reads and writes the entries of the shared user layer."""

    def __init__(self, config_path) -> None:
        """`config_path` is `hass.config.path`."""
        self._config_path = config_path

    def root(self, section: str) -> Path:
        """Folder of the user layer of a section."""
        return Path(self._config_path(*shared_user_parts(section)))

    def path_of(self, section: str, kind: str, entry_id: str) -> Path:
        """The file of a task, the folder of any other entry."""
        folder, _ = KIND_LAYOUT[_PACK_KINDS[kind]]
        base = self.root(section) / folder
        return base / f"{entry_id}.json" if kind == "task" else base / entry_id

    def has(self, section: str, kind: str, entry_id: str) -> bool:
        """The user has an entry of their own with this id."""
        path = self.path_of(section, kind, entry_id)
        return (
            path.is_file() if kind == "task" else (path / DESCRIPTORS[kind]).is_file()
        )

    def read(self, section: str, kind: str, entry_id: str) -> dict[str, Any]:
        """The descriptor of an entry of the user."""
        path = self.path_of(section, kind, entry_id)
        if kind != "task":
            path /= DESCRIPTORS[kind]
        return json.loads(path.read_text(encoding="utf-8"))

    def read_visuals(self, section: str, kind: str, entry_id: str) -> dict[str, bytes]:
        """The visuals (every file but the descriptor) of an entry of the user."""
        if kind == "task" or not self.has(section, kind, entry_id):
            return {}
        folder = self.path_of(section, kind, entry_id)
        return {
            path.name: path.read_bytes()
            for path in sorted(folder.iterdir())
            if path.is_file() and path.name != DESCRIPTORS[kind]
        }

    def write(
        self,
        section: str,
        kind: str,
        entry_id: str,
        data: dict[str, Any],
        visuals: dict[str, bytes] | None = None,
    ) -> None:
        """Write an entry, replacing the previous one in one move."""
        target = self.path_of(section, kind, entry_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        if kind == "task":
            temporary = target.with_name(f".{target.name}.tmp")
            temporary.write_bytes(dump(data))
            os.replace(temporary, target)
            return
        # Folders starting with a dot are ignored by the readers of the layer
        staging = target.with_name(f".{entry_id}.new")
        old = target.with_name(f".{entry_id}.old")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        (staging / DESCRIPTORS[kind]).write_bytes(dump(data))
        for name, blob in (visuals or {}).items():
            (staging / name).write_bytes(blob)
        shutil.rmtree(old, ignore_errors=True)
        if target.exists():
            target.rename(old)
        staging.rename(target)
        shutil.rmtree(old, ignore_errors=True)

    def delete(self, section: str, kind: str, entry_id: str) -> bool:
        """Remove an entry of the user; False when there was none."""
        if not self.has(section, kind, entry_id):
            return False
        path = self.path_of(section, kind, entry_id)
        if kind == "task":
            path.unlink()
        else:
            shutil.rmtree(path)
        return True
