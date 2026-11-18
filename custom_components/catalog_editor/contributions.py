"""What is kept between runs: the GitHub login and the pull requests proposed."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORAGE_VERSION = 1
#: Contributions kept (the oldest finished ones go first)
MAX_ITEMS = 100


class Contributions:
    """The token of the user and the pull requests made with the editor."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind to the storage of the integration."""
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, DOMAIN)
        self.token: str | None = None
        self.login: str | None = None
        self.items: list[dict[str, Any]] = []

    async def async_load(self) -> None:
        """Read what a previous run saved."""
        data = await self._store.async_load() or {}
        self.token = data.get("token")
        self.login = data.get("login")
        self.items = list(data.get("items", []))

    async def _async_save(self) -> None:
        await self._store.async_save(
            {"token": self.token, "login": self.login, "items": self.items}
        )

    async def async_sign_in(self, token: str, login: str) -> None:
        """Keep the token of a successful login."""
        self.token, self.login = token, login
        await self._async_save()

    async def async_sign_out(self) -> None:
        """Forget the token (the pull requests stay listed)."""
        self.token = self.login = None
        await self._async_save()

    def find(self, section: str, kind: str, entry_id: str) -> dict[str, Any] | None:
        """The pull request still open for an entry, if any."""
        for item in self.items:
            if (item["section"], item["kind"], item["id"]) == (
                section,
                kind,
                entry_id,
            ) and item["state"] == "open":
                return item
        return None

    async def async_record(self, *items: dict[str, Any]) -> None:
        """Add entries of a pull request, or replace the ones already listed.

        An entry is identified by its pull request and its place in the catalog: a
        batch pull request is listed once per entry it holds.
        """

        def identity(item: dict[str, Any]) -> tuple[Any, ...]:
            return (item["number"], item["section"], item["kind"], item["id"])

        news = {identity(item) for item in items}
        self.items = [i for i in self.items if identity(i) not in news]
        self.items[0:0] = items
        del self.items[MAX_ITEMS:]
        await self._async_save()

    async def async_save(self) -> None:
        """Write the changes made to the items in place."""
        await self._async_save()
