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
    assert [c["section"] for c in result] == [
        "equipment",
        "supplements",
        "parameters",
        "water_tests",
    ]
    assert result[0] == {
        "section": "equipment",
        "kinds": ["item", "category", "task"],
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
        ("github_status", {}),
        ("github_login", {}),
        ("github_login_poll", {}),
        ("github_logout", {}),
        ("contributions", {}),
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


async def test_water_tests(editor, hass):
    from conftest import WATER_TEST

    base = {"section": "water_tests", "kind": "water_test", "entry_id": "rs-2"}
    ok = await call(editor, "validate", data={**WATER_TEST, "name": "Other"}, **base)
    assert ok.get("success") is True, ok
    assert ok["result"]["errors"] == [], ok
    # Checked against the parameters catalog: the unit must be the one of the parameter
    bad = {**WATER_TEST, "name": "Other"}
    bad["tests"] = [{**WATER_TEST["tests"][0], "unit": "ppm"}]
    found = (await call(editor, "validate", data=bad, **base))["result"]["errors"]
    assert any("differs from the one of the parameter" in e for e in found)
    # Same product as an existing one
    dup = (await call(editor, "validate", data=WATER_TEST, **base))["result"]["errors"]
    assert any("already 'rs'" in e for e in dup)
    saved = await call(editor, "save", data={**WATER_TEST, "name": "Other"}, **base)
    assert saved["result"]["saved"] is True, saved
    # Without a parameters catalog the test is not cross-checked
    hass.data["reeftech_catalog"].pop("fake_par")
    again = await call(editor, "validate", data=bad, **{**base, "entry_id": "rs-3"})
    assert not any("differs" in e for e in again["result"]["errors"])


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


# -- GitHub ---------------------------------------------------------------------------

from fake_github import FakeGithub  # noqa: E402
from homeassistant.helpers.dispatcher import async_dispatcher_connect  # noqa: E402

from custom_components.reeftech_catalog_editor import github  # noqa: E402

LOGIN = "https://github.com/login"
BASE = {"section": "equipment", "kind": "item", "entry_id": "acme-x1"}


@pytest.fixture
def gh(aioclient_mock, monkeypatch):
    monkeypatch.setattr(github, "FORK_DELAY_S", 0)
    return FakeGithub(aioclient_mock)


async def sign_in(hass):
    await hass.data[T].contributions.async_sign_in("tok", "elwin")


async def save_item(editor, hass_client, **extra):
    http = await hass_client()
    token = (await (await upload(http, png())).json())["token"]
    saved = (await call(editor, "save", data=ITEM, visual=token, **BASE, **extra))[
        "result"
    ]
    assert saved["saved"] is True, saved


async def test_login_flow(editor, hass, aioclient_mock):
    assert (await call(editor, "github_status"))["result"] == {
        "connected": False,
        "login": None,
        "login_pending": False,
    }
    assert (await call(editor, "github_login_poll"))["error"]["code"] == "no_login"
    aioclient_mock.post(
        f"{LOGIN}/device/code",
        json={
            "device_code": "dev",
            "user_code": "ABCD-1234",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        },
    )
    started = (await call(editor, "github_login"))["result"]
    assert started["user_code"] == "ABCD-1234" and started["interval"] == 5
    assert (await call(editor, "github_status"))["result"]["login_pending"] is True

    answers = [
        {"error": "authorization_pending"},
        {"error": "slow_down", "interval": 10},
    ]

    async def token(method, url, data):
        from pytest_homeassistant_custom_component.test_util.aiohttp import (
            AiohttpClientMockResponse,
        )

        return AiohttpClientMockResponse(method, url, json=answers.pop(0))

    aioclient_mock.post(f"{LOGIN}/oauth/access_token", side_effect=token)
    assert (await call(editor, "github_login_poll"))["result"] == {
        "status": "pending",
        "interval": 5,
    }
    assert (await call(editor, "github_login_poll"))["result"] == {
        "status": "pending",
        "interval": 10,
    }

    aioclient_mock.clear_requests()
    FakeGithub(aioclient_mock)
    aioclient_mock.post(f"{LOGIN}/oauth/access_token", json={"access_token": "tok"})
    ok = (await call(editor, "github_login_poll"))["result"]
    assert ok == {"status": "ok", "login": "elwin"}
    assert hass.data[T].login is None
    assert (await call(editor, "github_status"))["result"]["connected"] is True
    assert (await call(editor, "github_logout"))["result"] == {"connected": False}
    assert hass.data[T].contributions.token is None


async def test_login_ends(editor, hass, aioclient_mock, monkeypatch):
    aioclient_mock.post(
        f"{LOGIN}/device/code",
        json={
            "device_code": "d",
            "user_code": "U",
            "verification_uri": "v",
            "expires_in": 900,
        },
    )
    await call(editor, "github_login")
    aioclient_mock.post(f"{LOGIN}/oauth/access_token", json={"error": "access_denied"})
    assert (await call(editor, "github_login_poll"))["result"] == {"status": "denied"}
    assert hass.data[T].login is None
    await call(editor, "github_login")
    hass.data[T].login = ("d", 0.0, 5)  # long expired
    assert (await call(editor, "github_login_poll"))["result"] == {"status": "expired"}
    assert (await call(editor, "github_status"))["result"]["login_pending"] is False
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{LOGIN}/device/code", json={"error": "unauthorized_client"})
    assert (await call(editor, "github_login"))["error"]["code"] == "login_refused"


async def test_contribute_refusals(editor, hass, hass_client, gh):
    assert (await call(editor, "contribute", attest=False, **BASE))["error"][
        "code"
    ] == "attestation_required"
    assert (await call(editor, "contribute", attest=True, **BASE))["error"][
        "code"
    ] == "auth_required"
    await sign_in(hass)
    assert (await call(editor, "contribute", attest=True, **BASE))["error"][
        "code"
    ] == "no_user_copy"

    # An entry that was valid when saved but is not any more (its category went)
    await save_item(editor, hass_client)
    hass.data["reeftech_catalog"]["fake"].view["categories"].pop("heater")
    refused = (await call(editor, "contribute", attest=True, **BASE))["result"]
    assert refused["submitted"] is False and refused["errors"]
    assert gh.pulls == {}

    gh.valid = False  # the token was revoked
    hass.data["reeftech_catalog"]["fake"].view["categories"]["heater"] = {
        "name": {"en": "Heater"},
        "scopes": ["aquarium"],
    }
    revoked = await call(editor, "contribute", attest=True, **BASE)
    assert revoked["error"]["code"] == "auth_required"
    assert hass.data[T].contributions.token is None


async def test_contribute_and_follow(editor, hass, hass_client, gh, pack):
    await sign_in(hass)
    await save_item(editor, hass_client)
    signals = []
    async_dispatcher_connect(hass, SIGNAL_USER_CATALOG_CHANGED, signals.append)

    done = (await call(editor, "contribute", attest=True, **BASE))["result"]
    assert (
        done["submitted"] is True and done["appended"] is False and done["number"] == 1
    )
    assert done["url"].endswith("/pull/1")
    files = gh.files("elwin/reeftech-catalog", gh.pulls[1]["head"]["ref"])
    assert set(files) == {
        "equipment/items/acme-x1/item.json",
        "equipment/items/acme-x1/image.webp",
        "equipment/items/acme-x1/thumb.webp",
    }

    listed = (await call(editor, "contributions"))["result"]
    assert [(i["id"], i["state"], i["label"], i["released"]) for i in listed] == [
        ("acme-x1", "open", "Acme X1", False)
    ]

    # A change before the merge goes into the same pull request
    again = (await call(editor, "save", data={**ITEM, "power_w": 5}, **BASE))["result"]
    assert again["saved"] is True
    second = (await call(editor, "contribute", attest=True, **BASE))["result"]
    assert second["appended"] is True and second["number"] == 1 and len(gh.pulls) == 1

    # Merged, but the integrations do not have it yet: the local copy stays
    gh.pulls[1]["merged_at"] = "2026-11-16T10:00:00Z"
    merged = (await call(editor, "contributions"))["result"]
    assert merged[0]["state"] == "merged" and merged[0]["released"] is False
    assert hass.data[T].catalog.has("equipment", "item", "acme-x1")

    # Released with other content (the maintainer changed it): still kept
    folder = pack / "items/acme-x1"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "item.json").write_text("{}")
    assert (await call(editor, "contributions"))["result"][0]["released"] is False

    # Released as it was proposed: the copy of the user is redundant
    own = hass.data[T].catalog.path_of("equipment", "item", "acme-x1") / "item.json"
    (folder / "item.json").write_bytes(own.read_bytes())
    signals.clear()
    released = (await call(editor, "contributions"))["result"]
    assert released[0]["released"] is True
    await hass.async_block_till_done()
    assert signals == ["equipment"]
    assert not hass.data[T].catalog.has("equipment", "item", "acme-x1")
    # Nothing more to do once released
    assert (await call(editor, "contributions"))["result"][0]["released"] is True


async def test_contributions_edge_cases(editor, hass, hass_client, gh, pack):
    # Signed out: the list is returned as it is
    assert (await call(editor, "contributions"))["result"] == []
    await sign_in(hass)
    await save_item(editor, hass_client)
    await call(editor, "contribute", attest=True, **BASE)

    # Offline: the last known state stays
    gh.status = 500
    assert (await call(editor, "contributions"))["result"][0]["state"] == "open"
    assert hass.data[T].contributions.token == "tok"
    # Revoked token: signed out, the list stays
    gh.status = None
    gh.valid = False
    assert (await call(editor, "contributions"))["result"][0]["state"] == "open"
    assert hass.data[T].contributions.token is None

    # Merged while no integration reads the section, then once the copy is gone
    item = hass.data[T].contributions.items[0]
    item["state"] = "merged"
    saved_providers = hass.data["reeftech_catalog"].pop("fake")
    assert (await call(editor, "contributions"))["result"][0]["released"] is False
    hass.data["reeftech_catalog"]["fake"] = saved_providers
    await hass.async_add_executor_job(
        hass.data[T].catalog.delete, "equipment", "item", "acme-x1"
    )
    assert (await call(editor, "contributions"))["result"][0]["released"] is False


async def test_a_task_is_released_as_a_file(editor, hass, gh, pack):
    await sign_in(hass)
    task = {"name": {"en": "Rinse"}, "schedule": interval()}
    base = {"section": "equipment", "kind": "task", "entry_id": "rinse"}
    assert (await call(editor, "save", data=task, **base))["result"]["saved"] is True
    assert (await call(editor, "contribute", attest=True, **base))["result"][
        "submitted"
    ] is True
    assert set(gh.files("elwin/reeftech-catalog", gh.pulls[1]["head"]["ref"])) == {
        "equipment/tasks/rinse.json"
    }
    gh.pulls[1]["merged_at"] = "2026-11-16T10:00:00Z"
    (pack / "tasks").mkdir()
    own = hass.data[T].catalog.path_of("equipment", "task", "rinse")
    (pack / "tasks/rinse.json").write_bytes(own.read_bytes())
    assert (await call(editor, "contributions"))["result"][0]["released"] is True
    assert not own.exists()


# -- the card ---------------------------------------------------------------------------


async def test_card_is_served_and_loaded(
    hass, aioclient_mock, hass_client, monkeypatch
):
    import sys
    from unittest.mock import MagicMock

    loaded = []
    fake = MagicMock()
    fake.add_extra_js_url = lambda hass, url: loaded.append(url)
    monkeypatch.setitem(sys.modules, "homeassistant.components.frontend", fake)
    hass.config.components.add("frontend")
    await setup_editor(hass, aioclient_mock)
    assert len(loaded) == 1 and loaded[0].startswith(
        "/reeftech_catalog_editor/reeftech-catalog-editor-card.js?v="
    )
    http = await hass_client()
    reply = await http.get("/reeftech_catalog_editor/reeftech-catalog-editor-card.js")
    assert reply.status == 200 and "reeftech-catalog-editor-card" in await reply.text()
    # Set up once, even if the entry is loaded again
    await hass.config_entries.async_reload(
        hass.config_entries.async_entries(T)[0].entry_id
    )
    assert len(loaded) == 1


async def test_card_without_http_or_frontend(hass, aioclient_mock):
    from custom_components.reeftech_catalog_editor.frontend import async_register_card

    # No frontend: the file is served but not loaded by the interface
    await setup_editor(hass, aioclient_mock)
    assert "frontend" not in hass.config.components
    hass.http = None
    await async_register_card(hass)  # nothing to serve it with: no error
