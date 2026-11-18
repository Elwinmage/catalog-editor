"""The editor's own view of the catalog: shared packs, refresh, user layer."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from conftest import BASE, manifest_of, schema_zip, serve, setup_editor
from homeassistant.setup import async_setup_component

from custom_components.catalog_editor.catalog_runtime import (
    async_acquire_pack,
    async_release_pack,
    get_shared_pack,
)
from custom_components.catalog_editor.const import USER_URL

T = "catalog_editor"
CATEGORY = {"name": {"en": "Heater"}, "scopes": ["aquarium"], "icon": "mdi:thermometer"}
ITEM = {"category": "heater", "brand": "Acme", "model": "X1"}


async def call(client, command: str, **fields):
    await client.send_json_auto_id({"type": f"{T}/{command}", **fields})
    return await client.receive_json()


def pack_dir(hass, section: str = "equipment") -> Path:
    return Path(hass.config.path("reeftech_catalog", "pack", section))


def install_pack(hass, section: str = "equipment", version: str = "2026.11.0") -> Path:
    """A pack already on disk, the one `serve` announces (nothing to download)."""
    root = pack_dir(hass, section)
    root.mkdir(parents=True)
    manifest = manifest_of(section, schema_zip(section), version)
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def put(root: Path, relative: str, data: dict | bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode())


def equipment_pack(hass) -> Path:
    root = install_pack(hass)
    put(root, "categories/heater/category.json", CATEGORY)
    put(root, "items/acme/item.json", ITEM)
    put(root, "items/acme/image.webp", b"RIFFacme")
    return root


SECTIONS = ("equipment", "supplements", "parameters", "water_tests")


def offline(aioclient_mock) -> None:
    """GitHub answers 404 for every release."""
    aioclient_mock.clear_requests()
    for section in SECTIONS:
        aioclient_mock.get(f"{BASE}/{section}-latest/manifest.json", status=404)


def release(aioclient_mock, section: str, version: str, items: dict[str, dict]):
    """Serve a release of a section holding `items`; the other sections stay as they are."""
    serve(aioclient_mock, sections=[s for s in SECTIONS if s != section])
    entries, files = {}, {}
    # The items need their category, which a release lists as an entry too
    records = [("category", "heater", "category.json", CATEGORY)]
    records += [
        ("item", entry_id, "item.json", data) for entry_id, data in items.items()
    ]
    for kind, entry_id, descriptor, data in records:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(descriptor, json.dumps(data))
        blob = buffer.getvalue()
        name = f"{section}-{version}/{kind}.{entry_id}.zip"
        entries[f"{kind}.{entry_id}"] = {
            "kind": kind,
            "scopes": ["aquarium"],
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size": len(blob),
            "archive": name,
            "since": version,
        }
        files[name] = blob
    schema = schema_zip(section)
    manifest = manifest_of(section, schema, version)
    manifest["entries"] = entries
    aioclient_mock.get(
        f"{BASE}/{section}-latest/manifest.json", text=json.dumps(manifest)
    )
    aioclient_mock.get(f"{BASE}/{manifest['schema']['archive']}", content=schema)
    for name, blob in files.items():
        aioclient_mock.get(f"{BASE}/{name}", content=blob)


async def test_view_of_the_shared_pack_and_the_user_layer(
    hass, aioclient_mock, hass_ws_client, hass_client
):
    root = equipment_pack(hass)
    await setup_editor(hass, aioclient_mock)
    client = await hass_ws_client(hass)

    entries = (await call(client, "entries", section="equipment", kind="item"))[
        "result"
    ]
    assert [(e["id"], e["source"]) for e in entries] == [("acme", "pack")]
    assert (
        entries[0]["image"]
        == "/reeftech_catalog_pack/equipment/items/acme/image.webp?v=2026.11.0"
    )

    # An entry of the user shows at once, with its picture served by the editor
    mine = {**ITEM, "model": "Mine"}
    base = {"section": "equipment", "kind": "item", "entry_id": "acme-mine"}
    saved = await call(client, "save", data=mine, **base)
    assert saved["result"]["saved"] is True, saved
    source = hass.data[T].sources["equipment"]
    assert source.user_revision == 1
    entries = (await call(client, "entries", section="equipment", kind="item"))[
        "result"
    ]
    assert {e["id"]: e["source"] for e in entries} == {
        "acme": "pack",
        "acme-mine": "user",
    }
    assert (await call(client, "delete", **base))["result"] == {"deleted": True}
    assert source.user_revision == 2

    http = await hass_client()
    response = await http.get("/reeftech_catalog_pack/equipment/items/acme/image.webp")
    assert response.status == 200 and await response.read() == b"RIFFacme"
    user = Path(hass.config.path("reeftech_catalog", "user", "equipment"))
    (user / "items/pic").mkdir(parents=True)
    (user / "items/pic/image.webp").write_bytes(b"RIFFpic")
    response = await http.get(f"{USER_URL}/equipment/items/pic/image.webp")
    assert response.status == 200 and await response.read() == b"RIFFpic"
    assert root.is_dir()


async def test_section_not_downloaded_then_refresh(
    hass, aioclient_mock, hass_ws_client
):
    """Offline at first: the section is not editable; Refresh downloads it."""
    offline(aioclient_mock)
    await setup_editor(hass, aioclient_mock, release=False)
    client = await hass_ws_client(hass)
    info = (await call(client, "catalogs"))["result"][0]
    assert info["installed"] is None and info["error"]
    refused = await call(client, "entries", section="equipment", kind="item")
    assert refused["error"]["code"] == "not_installed"
    assert refused["error"]["message"] == info["error"]

    release(aioclient_mock, "equipment", "2026.11.0", {"acme": ITEM})  # back online
    assert not (pack_dir(hass) / "items").exists()
    refreshed = (await call(client, "refresh", section="equipment"))["result"]
    assert refreshed[0]["installed"] == "2026.11.0" and refreshed[0]["error"] is None
    # The other sections were not asked
    assert refreshed[1]["installed"] is None and refreshed[1]["error"]
    ids = (await call(client, "entries", section="equipment", kind="item"))["result"]
    assert [e["id"] for e in ids] == ["acme"]
    assert (pack_dir(hass) / "items/acme/item.json").is_file()


async def test_refresh_installs_a_new_release_for_everyone(
    hass, aioclient_mock, hass_ws_client
):
    equipment_pack(hass)
    await setup_editor(hass, aioclient_mock)
    client = await hass_ws_client(hass)
    assert (await call(client, "catalogs"))["result"][0]["update_available"] is False

    release(
        aioclient_mock,
        "equipment",
        "2026.11.1",
        {"acme": ITEM, "acme-2": {**ITEM, "model": "X2"}},
    )
    result = (await call(client, "refresh"))["result"]  # all the sections
    assert result[0]["installed"] == "2026.11.1" and not result[0]["update_available"]
    pack = get_shared_pack(hass, "equipment")
    assert pack is not None and pack.installed is not None
    assert pack.installed.version == "2026.11.1"
    ids = [
        e["id"]
        for e in (await call(client, "entries", section="equipment", kind="item"))[
            "result"
        ]
    ]
    assert ids == ["acme", "acme-2"]

    # A section that cannot be reached reports its error and keeps what it has
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/equipment-latest/manifest.json", status=500)
    failed = (await call(client, "refresh", section="equipment"))["result"][0]
    assert failed["installed"] == "2026.11.1" and "HTTP 500" in failed["error"]
    assert failed["schema_error"] and "HTTP 500" in failed["schema_error"]


async def test_a_release_installed_by_someone_else_is_followed(
    hass, aioclient_mock, hass_ws_client
):
    """Another holder of the pack (an integration) installs: the view follows."""
    equipment_pack(hass)
    await setup_editor(hass, aioclient_mock)
    client = await hass_ws_client(hass)
    other = await async_acquire_pack(hass, "equipment", "redsea", auto=True)
    release(aioclient_mock, "equipment", "2026.11.1", {"acme": ITEM, "late": ITEM})
    await other.async_check(force=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    ids = [
        e["id"]
        for e in (await call(client, "entries", section="equipment", kind="item"))[
            "result"
        ]
    ]
    assert ids == ["acme", "late"]
    async_release_pack(hass, "equipment", "redsea")


async def test_unload_gives_the_packs_back(hass, aioclient_mock):
    entry = await setup_editor(hass, aioclient_mock)
    assert get_shared_pack(hass, "equipment") is not None
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert all(
        get_shared_pack(hass, s) is None
        for s in ("equipment", "supplements", "parameters", "water_tests")
    )


async def test_user_paths_need_http(hass, tmp_path):
    from custom_components.catalog_editor.frontend import (
        async_register_user_paths,
    )

    assert getattr(hass, "http", None) is None
    await async_register_user_paths(hass, {"equipment": tmp_path})  # no effect
    await async_setup_component(hass, "http", {})
    await async_register_user_paths(hass, {"equipment": tmp_path})
