"""One import for the schema library of Home Assistant."""

from __future__ import annotations

from typing import TYPE_CHECKING

# Home Assistant validates with probatio since 2026.9: schemas must come from it
if TYPE_CHECKING:
    import probatio as vol  # pyright: ignore[reportMissingImports]
else:
    try:
        import probatio as vol
    except ImportError:  # pragma: no cover - depends on the installed HA version
        import voluptuous as vol


__all__ = ["vol"]
