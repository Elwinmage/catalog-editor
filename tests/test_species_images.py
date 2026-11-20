"""The photo of a species: image models, photo checks, degraded atlas, save and PR."""

from __future__ import annotations

import base64
import io
import json
import time
from pathlib import Path

import pytest
from aiohttp import ClientError, FormData
from fake_github import REEFTANK
from homeassistant.data_entry_flow import FlowResultType
from PIL import Image, ImageDraw
from test_api import T, call, sign_in
from test_reeftank_catalog import AT, DRAFT
from test_reeftank_catalog import editor as species_editor  # noqa: F401
from test_reeftank_catalog import gh as fake_github_fixture  # noqa: F401

from custom_components.catalog_editor import image_providers, images
from custom_components.catalog_editor.api import PendingAtlas
from custom_components.catalog_editor.const import (
    CONF_IMAGE_KEY,
    CONF_IMAGE_MODEL,
    CONF_IMAGE_PROVIDER,
)
from custom_components.catalog_editor.image_providers import (
    PROVIDERS,
    ProviderError,
    generate_image,
)
from custom_components.catalog_editor.reeftank_catalog_still import PROMPT

GEMINI = image_providers.GEMINI_URL.format(model="gemini-2.5-flash-image")
NEW = {**AT, "entry_id": "amphiprion_percula"}
FISH_DRAFT = {**DRAFT, "scientific": "Amphiprion percula"}


@pytest.fixture
def editor(species_editor):  # noqa: F811
    """The websocket client of an editor holding a few species."""
    return species_editor


@pytest.fixture
def gh(fake_github_fixture):  # noqa: F811
    """The fake GitHub."""
    return fake_github_fixture


def photo_bytes(key=(255, 0, 255), size=(640, 400), fmt="PNG") -> bytes:
    """A flat background with an ellipse and a tail."""
    image = Image.new("RGB", size, key)
    draw = ImageDraw.Draw(image)
    w, h = size
    draw.ellipse((160, h * 0.3, w - 100, h * 0.7), fill=(230, 120, 20))
    draw.polygon([(180, h / 2), (100, h * 0.3), (100, h * 0.7)], fill=(230, 120, 20))
    buffer = io.BytesIO()
    image.save(buffer, fmt)
    return buffer.getvalue()


def b64(blob: bytes) -> str:
    return base64.b64encode(blob).decode()


def gemini_reply(blob: bytes, name: str = "inlineData") -> dict:
    return {
        "candidates": [
            {"content": {"parts": [{"text": "ok"}, {name: {"data": b64(blob)}}]}}
        ]
    }


def configure(hass, provider="gemini", model="") -> None:
    hass.data[T].image = {
        CONF_IMAGE_PROVIDER: provider,
        CONF_IMAGE_KEY: "secret-key",
        **({CONF_IMAGE_MODEL: model} if model else {}),
    }


async def post_photo(http, blob: bytes, key: str | None = None, field: str = "file"):
    form = FormData()
    form.add_field(field, blob, filename="p.png", content_type="image/png")
    if key:
        form.add_field("key", key)
    return await http.post(f"/api/{T}/photo", data=form)


# -- the image models -------------------------------------------------------------


async def test_gemini_gives_the_picture(hass, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    aioclient_mock.post(GEMINI, json=gemini_reply(b"PIC"))
    assert await generate_image(session, "gemini", "k", "", "prompt") == b"PIC"
    request = aioclient_mock.mock_calls[0]
    assert request[2] == {
        "contents": [{"parts": [{"text": "prompt"}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    assert request[3]["x-goog-api-key"] == "k"
    aioclient_mock.clear_requests()
    aioclient_mock.post(GEMINI, json=gemini_reply(b"PIC2", "inline_data"))
    assert (
        await PROVIDERS["gemini"].generate(
            session, "k", PROVIDERS["gemini"].default_model, "p"
        )
        == b"PIC2"
    )


@pytest.mark.parametrize(
    ("status", "payload", "code", "text"),
    [
        (401, {"error": {"message": "bad key"}}, "provider_key_refused", "bad key"),
        (403, None, "provider_key_refused", "HTTP 403"),
        (429, {"error": {"message": "quota"}}, "provider_quota", "quota"),
        (400, {"error": "x"}, "provider_refused", "HTTP 400"),
        (500, {}, "provider_error", "HTTP 500"),
        (200, ["not", "a", "dict"], "provider_no_image", "no JSON"),
        (200, {}, "provider_no_image", "no picture"),
        (
            200,
            {"promptFeedback": {"blockReason": "SAFETY"}},
            "provider_refused",
            "SAFETY",
        ),
        (
            200,
            {"candidates": [{"content": {"parts": [{"inlineData": {"data": "!!"}}]}}]},
            "provider_no_image",
            "readable",
        ),
    ],
)
async def test_gemini_errors(hass, aioclient_mock, status, payload, code, text):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    aioclient_mock.post(GEMINI, status=status, json=payload)
    with pytest.raises(ProviderError, match=text) as err:
        await generate_image(async_get_clientsession(hass), "gemini", "k", "", "p")
    assert err.value.code == code
    assert "secret" not in str(err.value)


async def test_a_service_that_does_not_answer(hass, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    aioclient_mock.post(GEMINI, exc=ClientError())
    with pytest.raises(ProviderError) as err:
        await generate_image(async_get_clientsession(hass), "gemini", "k", "", "p")
    assert err.value.code == "provider_unreachable"
    aioclient_mock.clear_requests()
    aioclient_mock.post(GEMINI, text="<html>", status=502)  # not JSON
    with pytest.raises(ProviderError, match="HTTP 502"):
        await generate_image(async_get_clientsession(hass), "gemini", "k", "", "p")
    aioclient_mock.clear_requests()
    aioclient_mock.post(
        GEMINI,
        json={"candidates": [{"content": {"parts": [{"inlineData": {"data": ""}}]}}]},
    )
    with pytest.raises(ProviderError, match="no picture"):
        await generate_image(async_get_clientsession(hass), "gemini", "k", "", "p")
    aioclient_mock.clear_requests()
    aioclient_mock.post(
        GEMINI,
        json={
            "candidates": [{"content": {"parts": [{"inlineData": {"data": b64(b"")}}]}}]
        },
    )
    with pytest.raises(ProviderError, match="no picture"):
        await generate_image(async_get_clientsession(hass), "gemini", "k", "", "p")
    aioclient_mock.clear_requests()
    aioclient_mock.post(GEMINI, text="<html>")
    with pytest.raises(ProviderError, match="no JSON"):
        await generate_image(async_get_clientsession(hass), "gemini", "k", "", "p")


async def test_openai_gives_the_picture(hass, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    aioclient_mock.post(
        image_providers.OPENAI_URL, json={"data": [{"b64_json": b64(b"PIC")}]}
    )
    assert (
        await generate_image(session, "openai", "k", "gpt-image-2", "prompt") == b"PIC"
    )
    request = aioclient_mock.mock_calls[0]
    assert (
        request[2]["model"] == "gpt-image-2"
        and request[3]["Authorization"] == "Bearer k"
    )
    for payload in (
        {},
        {"data": []},
        {"data": ["x"]},
        {"data": [{}]},
        {"data": [{"b64_json": ""}]},
    ):
        aioclient_mock.clear_requests()
        aioclient_mock.post(image_providers.OPENAI_URL, json=payload)
        with pytest.raises(ProviderError):
            await generate_image(session, "openai", "k", "", "p")


# -- photos -----------------------------------------------------------------------


def test_a_photo_is_checked():
    good = images.inspect_photo(photo_bytes(), {"type": "photo"})
    assert good.problems == () and good.key == "magenta" and good.size == (640, 400)
    assert (
        images.inspect_photo(photo_bytes((0, 255, 0)), {"type": "photo"}).key == "green"
    )
    small = images.inspect_photo(photo_bytes(size=(300, 200)), {"type": "photo"})
    assert any("too small" in p for p in small.problems)
    asked = images.inspect_photo(photo_bytes(), {"type": "photo"}, "green")
    assert asked.key == "green" and asked.problems
    assert images.photo_preview(photo_bytes()).startswith("data:image/webp;base64,")


def test_a_photo_can_be_refused():
    with pytest.raises(images.ImageError, match="unreadable"):
        images.inspect_photo(b"not a picture", {"type": "photo"})
    with pytest.raises(images.ImageError, match="too_big"):
        images.inspect_photo(b"0" * (images.MAX_PHOTO_BYTES + 1), {"type": "photo"})
    old = images.MAX_PIXELS
    images.MAX_PIXELS = 100
    try:
        with pytest.raises(images.ImageError, match="too_many_pixels"):
            images.inspect_photo(photo_bytes(), {"type": "photo"})
    finally:
        images.MAX_PIXELS = old


def test_the_atlas_of_a_photo():
    photo = images.inspect_photo(photo_bytes(), {"type": "ai-generated", "model": "m"})
    still = images.build_degraded(photo, "amphiprion_percula", photo.source, None)
    assert set(still.files) == {"amphiprion_percula.webp", "thumb.webp"}
    assert still.keys["degraded"] is True and still.keys["source"] == photo.source
    assert images.atlas_preview(still).startswith("data:image/webp;base64,")


# -- the commands ---------------------------------------------------------------------


async def test_the_status_never_shows_the_key(editor, hass):
    status = (await call(editor, "image_status", section="fish", kind="fish"))["result"]
    assert status["configured"] is False and status["provider"] is None
    assert [p["id"] for p in status["providers"]] == ["gemini", "openai"]
    assert status["keys"] == ["magenta", "green"]
    assert status["licenses"] == ["CC BY 4.0", "CC0", "public domain"]
    configure(hass)
    status = (await call(editor, "image_status", section="fish", kind="fish"))["result"]
    assert status["configured"] is True and status["model"] == "gemini-2.5-flash-image"
    assert "secret" not in json.dumps(status)
    configure(hass, "openai", "gpt-image-2")
    status = (await call(editor, "image_status", section="fish", kind="fish"))["result"]
    assert (status["provider"], status["model"]) == ("openai", "gpt-image-2")
    hass.data[T].image = {CONF_IMAGE_PROVIDER: "unknown", CONF_IMAGE_KEY: "k"}
    status = (await call(editor, "image_status", section="fish", kind="fish"))["result"]
    assert status["configured"] is False
    # only fish have an atlas to make
    assert "error" in await call(editor, "image_status", section="plants", kind="plant")


async def test_the_prompt_is_the_fixed_one(editor):
    reply = (
        await call(
            editor,
            "image_prompt",
            section="fish",
            kind="fish",
            species="Amphiprion percula",
        )
    )["result"]
    assert reply["prompt"].startswith(
        "Realistic side view of Amphiprion percula, head to the RIGHT"
    )
    assert "#FF00FF" in reply["prompt"]
    green = (
        await call(
            editor,
            "image_prompt",
            section="fish",
            kind="fish",
            species="Paracanthurus hepatus",
            key="green",
        )
    )["result"]
    assert "#00FF00" in green["prompt"] and PROMPT["version"] == 1
    bad = await call(editor, "image_prompt", section="fish", kind="fish", species="x")
    assert "error" in bad


async def test_a_photo_is_generated(editor, hass, aioclient_mock):
    ask = {"section": "fish", "kind": "fish", "species": "Amphiprion percula"}
    refused = await call(editor, "image_generate", **ask)
    assert refused["error"]["code"] == "image_not_configured"
    configure(hass)
    aioclient_mock.post(GEMINI, json=gemini_reply(photo_bytes()))
    reply = (await call(editor, "image_generate", **ask))["result"]
    assert reply["problems"] == [] and reply["key"] == "magenta"
    assert reply["source"] == {
        "type": "ai-generated",
        "model": "gemini-2.5-flash-image",
    }
    assert (reply["width"], reply["height"]) == (640, 400)
    assert reply["token"] in hass.data[T].photos
    assert reply["preview"].startswith("data:image/webp")
    sent = aioclient_mock.mock_calls[-1][2]["contents"][0]["parts"][0]["text"]
    assert sent.startswith("Realistic side view of Amphiprion percula")
    # a service that refuses, then a picture nobody can read
    aioclient_mock.clear_requests()
    aioclient_mock.post(GEMINI, status=429, json={"error": {"message": "slow down"}})
    quota = await call(editor, "image_generate", **ask)
    assert quota["error"]["code"] == "provider_quota"
    aioclient_mock.clear_requests()
    aioclient_mock.post(GEMINI, json=gemini_reply(b"not a picture"))
    junk = await call(editor, "image_generate", **ask)
    assert junk["error"]["code"] == "unreadable"


async def test_a_photo_is_uploaded(
    editor, hass, hass_client, hass_read_only_access_token
):
    http = await hass_client()
    data = hass.data.pop(T)
    assert (await post_photo(http, photo_bytes())).status == 503
    hass.data[T] = data
    reply = await post_photo(http, photo_bytes((0, 255, 0)), key="green")
    body = await reply.json()
    assert reply.status == 200 and body["source"] == {"type": "photo"}
    assert body["key"] == "green" and body["problems"] == []
    assert body["token"] in hass.data[T].photos
    ignored = await (await post_photo(http, photo_bytes(), key="blue")).json()
    assert ignored["key"] == "magenta"
    reader = await hass_client(hass_read_only_access_token)
    assert (await post_photo(reader, photo_bytes())).status == 403
    assert (await post_photo(http, photo_bytes(), field="other")).status == 400
    refused = await post_photo(http, b"not a picture")
    assert refused.status == 400 and "unreadable" in await refused.text()


async def photo_token(hass, http, **kw) -> str:
    return (await (await post_photo(http, photo_bytes(**kw))).json())["token"]


async def test_an_atlas_is_built(editor, hass, hass_client):
    http = await hass_client()
    token = await photo_token(hass, http)
    build = {**NEW, "photo": token, "author": "Jane", "license": "CC BY 4.0"}
    unknown = await call(editor, "image_build", **{**build, "photo": "nope"})
    assert unknown["error"]["code"] == "unknown_photo"
    invalid = await call(editor, "image_build", **{**build, "entry_id": "Not Valid"})
    assert invalid["error"]["code"] == "invalid_id"
    no_author = await call(editor, "image_build", **{**NEW, "photo": token})
    assert no_author["error"]["code"] == "source_incomplete"
    no_license = await call(
        editor, "image_build", **{**NEW, "photo": token, "author": "Jane"}
    )
    assert no_license["error"]["code"] == "source_incomplete"
    done = (await call(editor, "image_build", **build))["result"]
    assert done["source"]["type"] == "photo" and done["source"]["author"] == "Jane"
    assert (
        done["source"]["license"] == "CC BY 4.0" and len(done["source"]["date"]) == 10
    )
    assert done["frame"][0] == 208 and done["preview"].startswith("data:image/webp")
    pending = hass.data[T].atlases[done["token"]][0]
    assert (
        isinstance(pending, PendingAtlas) and pending.entry_id == "amphiprion_percula"
    )
    assert set(pending.files) == {"amphiprion_percula.webp", "thumb.webp"}


async def test_an_unfit_photo_and_a_real_animation_are_refused(
    editor, hass, hass_client
):
    http = await hass_client()
    small = await photo_token(hass, http, size=(300, 200))
    build = {**NEW, "photo": small, "author": "Jane", "license": "CC0"}
    unfit = await call(editor, "image_build", **build)
    assert (
        unfit["error"]["code"] == "photo_unfit"
        and "too small" in unfit["error"]["message"]
    )
    forced = await call(editor, "image_build", **build, force=True)
    assert "result" in forced
    # the clown of the catalog has an atlas made from videos
    good = await photo_token(hass, http)
    real = {**AT, "photo": good, "author": "Jane", "license": "CC0"}
    refused = await call(editor, "image_build", **real)
    assert refused["error"]["code"] == "real_animation"
    assert "result" in await call(editor, "image_build", **real, force=True)
    # a photo whose background was asked for another colour: the picture is refused
    hass.data[T].photos[good] = (
        hass.data[T]
        .photos[good][0]
        .__class__(b"junk", (1, 1), (), None, {"type": "photo"}),
        time.monotonic() + 60,
    )
    junk = await call(
        editor, "image_build", **{**NEW, "photo": good, "author": "J", "license": "CC0"}
    )
    assert junk["error"]["code"] == "unreadable"


async def test_a_generated_atlas_is_saved_and_proposed(
    editor, hass, aioclient_mock, gh
):
    await sign_in(hass)
    configure(hass)
    aioclient_mock.post(GEMINI, json=gemini_reply(photo_bytes()))
    photo = (
        await call(
            editor,
            "image_generate",
            section="fish",
            kind="fish",
            species="Amphiprion percula",
        )
    )["result"]
    atlas = (await call(editor, "image_build", **NEW, photo=photo["token"]))["result"]
    assert atlas["source"]["model"] == "gemini-2.5-flash-image"
    draft = {**FISH_DRAFT}
    checked = (await call(editor, "validate", data=draft, atlas=atlas["token"], **NEW))[
        "result"
    ]
    assert checked["errors"] == [], checked
    saved = (
        await call(editor, "save", data=draft, new=True, atlas=atlas["token"], **NEW)
    )["result"]
    assert saved["saved"] is True, saved
    folder = Path(
        hass.config.path("reeftech_catalog/user/fish/fish/amphiprion_percula")
    )
    assert {p.name for p in folder.iterdir()} == {
        "species.json",
        "amphiprion_percula.webp",
        "thumb.webp",
    }
    written = json.loads((folder / "species.json").read_text())
    assert written["degraded"] is True and written["atlas"] == {
        "1x": "amphiprion_percula.webp"
    }
    assert written["source"]["type"] == "ai-generated" and written["kind"] == "fish"
    assert atlas["token"] not in hass.data[T].atlases
    # saved again without the atlas: the pictures of the user stay
    again = (
        await call(editor, "save", data={**FISH_DRAFT, "feeding_response": 0.4}, **NEW)
    )["result"]
    assert again["saved"] is True
    assert (folder / "amphiprion_percula.webp").is_file()
    done = (await call(editor, "contribute", attest=True, **NEW))["result"]
    assert done["submitted"] is True, done
    branch = gh.pulls_of[REEFTANK][1]["head"]["ref"]
    files = gh.files("elwin/reeftank-catalog", branch)
    assert set(files) == {
        "fish/amphiprion_percula/species.json",
        "fish/amphiprion_percula/amphiprion_percula.webp",
        "fish/amphiprion_percula/thumb.webp",
    }
    assert files["fish/amphiprion_percula/amphiprion_percula.webp"][:4] == b"RIFF"
    assert not any("photo" in path for path in files)


async def test_an_atlas_belongs_to_its_entry(editor, hass, hass_client):
    http = await hass_client()
    token = await photo_token(hass, http)
    atlas = (
        await call(editor, "image_build", **NEW, photo=token, author="J", license="CC0")
    )["result"]
    other = {**AT, "entry_id": "amphiprion_clarkii"}
    wrong = await call(
        editor, "save", data=FISH_DRAFT, new=True, atlas=atlas["token"], **other
    )
    assert wrong["error"]["code"] == "atlas_mismatch"
    gone = await call(editor, "save", data=FISH_DRAFT, new=True, atlas="nope", **NEW)
    assert gone["error"]["code"] == "unknown_atlas"


async def test_what_waits_is_forgotten(editor, hass, hass_client):
    http = await hass_client()
    token = await photo_token(hass, http)
    data = hass.data[T]
    photo, _ = data.photos[token]
    data.photos[token] = (photo, time.monotonic() - 1)
    data.prune()
    assert token not in data.photos
    for _ in range(25):
        data.keep(data.photos, photo)
    assert len(data.photos) == 20


# -- the options ---------------------------------------------------------------------


async def test_the_image_model_is_an_option(hass, aioclient_mock):
    from conftest import setup_editor

    entry = await setup_editor(hass, aioclient_mock)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert form["description_placeholders"] == {"key_state": "not set"}
    done = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            "sections": ["fish"],
            "image_provider": "gemini",
            "image_key": " abc ",
            "image_model": " gemini-x ",
        },
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert done["data"] == {
        "sections": ["fish"],
        "image_provider": "gemini",
        "image_key": "abc",
        "image_model": "gemini-x",
    }
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.data[T].image == {
        "image_provider": "gemini",
        "image_key": "abc",
        "image_model": "gemini-x",
    }
    # the key is kept when the field stays empty, and removed on demand
    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert form["description_placeholders"] == {"key_state": "set"}
    kept = await hass.config_entries.options.async_configure(
        form["flow_id"], {"sections": ["fish"], "image_provider": "openai"}
    )
    assert kept["data"] == {
        "sections": ["fish"],
        "image_provider": "openai",
        "image_key": "abc",
    }
    await hass.async_block_till_done(wait_background_tasks=True)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    cleared = await hass.config_entries.options.async_configure(
        form["flow_id"], {"sections": ["fish"], "clear_image_key": True}
    )
    assert cleared["data"] == {"sections": ["fish"]}
    # the reload the last change starts is over before the test ends
    await hass.async_block_till_done(wait_background_tasks=True)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
