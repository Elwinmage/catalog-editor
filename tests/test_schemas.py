"""Schemas downloaded from the releases and kept on disk."""

from __future__ import annotations

import json

from conftest import BASE, manifest_of, schema_zip, serve, setup_editor

from custom_components.reeftech_catalog_editor.schemas import SchemaStore


async def test_refresh_installs_and_reloads(hass, aioclient_mock):
    serve(aioclient_mock)
    store = SchemaStore(hass)
    assert not store.ready("equipment")
    assert await store.async_refresh("equipment") is True
    assert store.ready("equipment") and store.checksums["equipment"]
    assert set(store.schemas["equipment"]) == {"common", "task", "category", "item"}
    assert store.schemas_of("item") is store.schemas["equipment"]
    assert set(store.validators_of("item")) >= {"item"}
    calls = aioclient_mock.call_count
    # Same checksum: only the manifest is read
    assert await store.async_refresh("equipment") is True
    assert aioclient_mock.call_count == calls + 1

    fresh = SchemaStore(hass)
    await fresh.async_load()
    assert fresh.ready("equipment") and not fresh.ready("parameters")
    assert fresh.checksums == {"equipment": store.checksums["equipment"]}


async def test_refresh_replaces_changed_schemas(hass, aioclient_mock):
    serve(aioclient_mock, ("parameters",))
    store = SchemaStore(hass)
    await store.async_refresh("parameters")
    old = store.checksums["parameters"]
    blob = schema_zip("parameters", {"note.json": b"{}"})
    manifest = manifest_of("parameters", blob, "2026.12.0")
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{BASE}/parameters-latest/manifest.json", text=json.dumps(manifest)
    )
    aioclient_mock.get(f"{BASE}/{manifest['schema']['archive']}", content=blob)
    assert await store.async_refresh("parameters") is True
    assert store.checksums["parameters"] != old
    assert not store.folder("parameters").with_name("parameters.new").exists()


async def test_failures_keep_what_is_installed(hass, aioclient_mock):
    store = SchemaStore(hass)
    aioclient_mock.get(f"{BASE}/equipment-latest/manifest.json", status=404)
    assert await store.async_refresh("equipment") is False
    assert "equipment" in store.errors

    # A release without schemas
    manifest = manifest_of("equipment", b"")
    del manifest["schema"]
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{BASE}/equipment-latest/manifest.json", text=json.dumps(manifest)
    )
    assert await store.async_refresh("equipment") is False
    assert "no schemas" in store.errors["equipment"]

    serve(aioclient_mock, ("equipment",))
    assert await store.async_refresh("equipment") is True
    assert "equipment" not in store.errors
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/equipment-latest/manifest.json", status=500)
    assert await store.async_refresh("equipment") is True  # still usable
    assert "equipment" in store.errors


async def test_unreadable_folder_is_dropped(hass, aioclient_mock):
    serve(aioclient_mock, ("equipment",))
    store = SchemaStore(hass)
    await store.async_refresh("equipment")
    (store.folder("equipment") / "item.schema.json").write_text("{broken")
    await store._async_read("equipment")
    assert not store.ready("equipment") and "equipment" not in store.checksums
    # And a fresh start finds nothing usable, then downloads again
    other = SchemaStore(hass)
    await other.async_load()
    assert not other.ready("equipment")
    assert await other.async_refresh("equipment") is True


async def test_setup_and_unload(hass, aioclient_mock):
    entry = await setup_editor(hass, aioclient_mock)
    data = hass.data["reeftech_catalog_editor"]
    assert all(
        data.schemas.ready(s) for s in ("equipment", "supplements", "parameters")
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert "reeftech_catalog_editor" not in hass.data


async def test_missing_checksum_file_is_tolerated(hass, aioclient_mock):
    serve(aioclient_mock, ("equipment",))
    store = SchemaStore(hass)
    await store.async_refresh("equipment")
    (store.folder("equipment") / ".sha256").unlink()
    await store._async_read("equipment")
    assert store.ready("equipment") and store.checksums["equipment"] is None
    # Unknown checksum: the next refresh installs the release again
    assert await store.async_refresh("equipment") is True
    assert store.checksums["equipment"]
