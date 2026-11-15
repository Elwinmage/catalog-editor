"""Websocket commands and picture upload."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from aiohttp import FormData
from conftest import interval, setup_editor
from PIL import Image

from custom_components.reeftech_catalog_editor import api
from custom_components.reeftech_catalog_editor.catalog_runtime import (
    SIGNAL_USER_CATALOG_CHANGED,
)
from custom_components.reeftech_catalog_editor.images import Visual

T = "reeftech_catalog_editor"
ITEM = {"category": "heater", "brand": "Acme", "model": "X1", "name": {"en": "Acme X1"}}


def png(alpha: bool = True) -> bytes:
    buffer = io.BytesIO()
    Image.new(
        "RGBA" if alpha else "RGB", (200, 100), (10, 20, 30, 0 if alpha else 255)
    ).save(buffer, "PNG")
    return buffer.getvalue()


async def call(client, command: str, **fields):
    await client.send_json_auto_id({"type": f"{T}/{command}", **fields})
    return await client.receive_json()


async def upload(http, blob: bytes, field: str = "file"):
    form = FormData()
    form.add_field(field, blob, filename="p.png", content_type="image/png")
    return await http.post(f"/api/{T}/image", data=form)


@pytest.fixture
async def editor(hass, aioclient_mock, providers, hass_ws_client):
    await setup_editor(hass, aioclient_mock)
    return await hass_ws_client(hass)


async def test_catalogs(editor, hass):
    result = (await call(editor, "catalogs"))["result"]
    assert [c["section"] for c in result] == ["equipment", "supplements", "parameters"]
    assert result[0] == {
        "section": "equipment",
        "kinds": ["task", "category", "item"],
        "provider": "fake",
        "schemas": True,
        "schema_error": None,
    }
    hass.data["reeftech_catalog"].pop("fake_par")
    assert (await call(editor, "catalogs"))["result"][2]["provider"] is None


async def test_form_entries_entry(editor):
    form = (await call(editor, "form", section="equipment", kind="item"))["result"]
    assert form["kind"] == "item"
    entries = (await call(editor, "entries", section="equipment", kind="item"))[
        "result"
    ]
    assert [e["id"] for e in entries] == ["eheim-200"]
    assert entries[0]["label"] == "Eheim 200" and entries[0]["source"] == "pack"
    entry = (
        await call(
            editor, "entry", section="equipment", kind="item", entry_id="eheim-200"
        )
    )["result"]
    assert entry["data"] == {"category": "heater", "brand": "Eheim", "model": "200"}
    assert entry["source"] == "pack" and entry["user_copy"] is False
    missing = await call(
        editor, "entry", section="equipment", kind="item", entry_id="nope"
    )
    assert missing["error"]["code"] == "not_found"
    suggestion = await call(
        editor,
        "suggest_id",
        section="equipment",
        kind="item",
        data={"brand": "Eheim", "model": "200"},
    )
    assert suggestion["result"] == {"id": "eheim-200-2"}


async def test_refusals(editor, hass, aioclient_mock):
    wrong = await call(editor, "form", section="supplements", kind="item")
    assert wrong["error"]["code"] == "invalid_format"
    hass.data["reeftech_catalog"].pop("fake_sup")
    none = await call(editor, "form", section="supplements", kind="supplement")
    assert none["error"]["code"] == "no_provider"
    hass.data["reeftech_catalog"]["fake_sup"] = object()  # restored below
    hass.data["reeftech_catalog"].pop("fake_sup")

    # Schemas never downloaded and the release unreachable
    hass.data[T].schemas.validators.pop("parameters")
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        "https://github.com/Elwinmage/reeftech-catalog/releases/download/parameters-latest/manifest.json",
        status=404,
    )
    nothing = await call(editor, "form", section="parameters", kind="parameter")
    assert nothing["error"]["code"] == "schemas_unavailable"
    # ... but entries do not need them
    listed = await call(editor, "entries", section="parameters", kind="parameter")
    assert listed["success"] is True


async def test_not_loaded_and_non_admin(
    hass, aioclient_mock, providers, hass_ws_client, hass_read_only_access_token
):
    entry = await setup_editor(hass, aioclient_mock)
    admin = await hass_ws_client(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    for command, fields in (
        ("catalogs", {}),
        ("form", {"section": "equipment", "kind": "item"}),
    ):
        assert (await call(admin, command, **fields))["error"]["code"] == "not_loaded"
    await setup_editor(hass, aioclient_mock, release=False)
    reader = await hass_ws_client(hass, hass_read_only_access_token)
    assert (await call(reader, "catalogs"))["error"]["code"] == "unauthorized"


async def test_validate_reports(editor):
    base = {"section": "equipment", "kind": "item", "entry_id": "acme-x1"}
    ok = (await call(editor, "validate", data=ITEM, **base))["result"]
    assert ok["errors"] == []
    bad = (await call(editor, "validate", data={**ITEM, "category": "nope"}, **base))[
        "result"
    ]
    assert any("nope" in e for e in bad["errors"])
    bad_id = (
        await call(editor, "validate", data=ITEM, **{**base, "entry_id": "Bad Id"})
    )["result"]
    assert any("not a valid id" in e for e in bad_id["errors"])
    long_id = (
        await call(editor, "validate", data=ITEM, **{**base, "entry_id": "a" * 80})
    )["result"]
    assert any("not a valid id" in e for e in long_id["errors"])
    task = (
        await call(
            editor,
            "validate",
            section="equipment",
            kind="task",
            entry_id="rinse",
            data={"name": {"en": "Rinse"}, "schedule": interval()},
        )
    )["result"]
    assert task["errors"] == []


async def test_validate_with_picture(editor, hass_client, hass):
    http = await hass_client()
    opaque = (await (await upload(http, png(alpha=False))).json())["token"]
    base = {"section": "equipment", "kind": "item", "entry_id": "acme-x1", "data": ITEM}
    report = (await call(editor, "validate", visual=opaque, **base))["result"]
    assert any("transparent" in w for w in report["warnings"])
    clear = (
        await call(
            editor,
            "validate",
            visual=(await (await upload(http, png())).json())["token"],
            **base,
        )
    )["result"]
    assert not any("transparent" in w for w in clear["warnings"])
    gone = await call(editor, "validate", visual="expired", **base)
    assert gone["error"]["code"] == "unknown_upload"
    # A category has no picture: the token is ignored
    cat = await call(
        editor,
        "validate",
        section="equipment",
        kind="category",
        entry_id="pump",
        data={"name": {"en": "Pump"}},
        visual=opaque,
    )
    assert cat["success"] is True


async def test_save_and_delete_flow(editor, hass, hass_client):
    signals = []
    from homeassistant.helpers.dispatcher import async_dispatcher_connect

    async_dispatcher_connect(hass, SIGNAL_USER_CATALOG_CHANGED, signals.append)
    http = await hass_client()
    token = (await (await upload(http, png())).json())["token"]
    root = Path(hass.config.path("reeftech_catalog", "user", "equipment"))
    base = {"section": "equipment", "kind": "item", "entry_id": "acme-x1"}

    invalid = (await call(editor, "save", data={**ITEM, "category": "nope"}, **base))[
        "result"
    ]
    assert invalid["saved"] is False and invalid["errors"]
    assert not (root / "items").exists()

    saved = (await call(editor, "save", data=ITEM, visual=token, new=True, **base))[
        "result"
    ]
    assert saved["saved"] is True and saved["id"] == "acme-x1"
    await hass.async_block_till_done()
    assert signals == ["equipment"]
    folder = root / "items/acme-x1"
    assert json.loads((folder / "item.json").read_text()) == ITEM
    assert (folder / "image.webp").exists() and (folder / "thumb.webp").exists()
    assert token not in hass.data[T].uploads

    # Edit without a new picture: the own visual is kept
    again = (await call(editor, "save", data={**ITEM, "model": "X2"}, **base))["result"]
    assert again["saved"] is True and (folder / "image.webp").exists()
    # ... unless removed
    cleared = (await call(editor, "save", data=ITEM, remove_visual=True, **base))[
        "result"
    ]
    assert cleared["saved"] is True and not (folder / "image.webp").exists()

    taken = await call(
        editor,
        "save",
        data=ITEM,
        new=True,
        section="equipment",
        kind="item",
        entry_id="eheim-200",
    )
    assert taken["error"]["code"] == "id_taken"

    assert (await call(editor, "delete", **base))["result"] == {"deleted": True}
    assert not folder.exists()
    assert (await call(editor, "delete", **base))["error"]["code"] == "not_found"


async def test_override_keeps_the_visual_of_the_catalog(editor, hass):
    data = {"category": "heater", "brand": "Eheim", "model": "200"}
    base = {"section": "equipment", "kind": "item", "entry_id": "eheim-200"}
    saved = (await call(editor, "save", data={**data, "power_w": 100}, **base))[
        "result"
    ]
    assert saved["saved"] is True
    folder = Path(
        hass.config.path("reeftech_catalog", "user", "equipment", "items", "eheim-200")
    )
    assert (folder / "image.png").read_bytes() == b"PNGDATA"
    assert (folder / "thumb.webp").read_bytes() == b"THUMBDATA"
    entry = (await call(editor, "entry", **base))["result"]
    assert entry["user_copy"] is True


async def test_other_sections(editor, hass):
    sup = (
        await call(
            editor,
            "save",
            section="supplements",
            kind="supplement",
            entry_id="b-ca",
            data={
                "brand": "B",
                "name": "Ca",
                "fullname": "B - Ca",
                "kind": "ca",
                "verified": False,
            },
        )
    )["result"]
    assert sup["saved"] is True, sup
    par = (
        await call(
            editor,
            "save",
            section="parameters",
            kind="parameter",
            entry_id="ca",
            data={
                "name": {"en": "Ca"},
                "symbol": "Ca",
                "category": "major",
                "unit": "mg_l",
            },
        )
    )["result"]
    assert par["saved"] is True, par


async def test_upload_view(
    hass, aioclient_mock, providers, hass_client, hass_read_only_access_token
):
    await setup_editor(hass, aioclient_mock)
    http = await hass_client()
    data = hass.data.pop(T)
    assert (await upload(http, png())).status == 503  # editor not loaded
    hass.data[T] = data
    reply = await upload(http, png())
    body = await reply.json()
    assert reply.status == 200 and body["has_alpha"] is True
    assert (body["width"], body["height"]) == (200, 100)
    assert body["preview"].startswith("data:image/webp;base64,")
    assert body["token"] in hass.data[T].uploads

    assert (await upload(http, png(), field="other")).status == 400
    refused = await upload(http, b"not a picture")
    assert refused.status == 400 and "unreadable" in await refused.text()

    reader = await hass_client(hass_read_only_access_token)
    assert (await upload(reader, png())).status == 403


async def test_upload_bookkeeping(hass, aioclient_mock, monkeypatch):
    await setup_editor(hass, aioclient_mock)
    data = hass.data[T]
    visual = Visual(b"i", b"t", True, (1, 1))
    monkeypatch.setattr(api, "MAX_UPLOADS", 2)
    tokens = [data.store(visual) for _ in range(4)]
    assert set(data.uploads) == set(tokens[-2:])
    monkeypatch.setattr(api, "UPLOAD_TTL_S", -1)
    expired = data.store(visual)  # expires at once
    assert expired not in data.uploads and len(data.uploads) == 2


async def test_register_api_once(hass, aioclient_mock):
    await setup_editor(hass, aioclient_mock)
    api.async_register_api(hass)  # second call is a no-op
