"""The photo of a species: image models, photo checks, degraded atlas, save and PR."""

from __future__ import annotations

import base64
import io
import json
import time
from pathlib import Path

import numpy as np
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
from custom_components.catalog_editor import reeftank_catalog_plant as plant
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
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": "3:2"},
        },
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


ACCOUNT = "0123456789abcdef0123456789abcdef"


async def test_cloudflare_gives_the_picture(hass, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    url = image_providers.CLOUDFLARE_URL.format(
        account=ACCOUNT, model="@cf/black-forest-labs/flux-1-schnell"
    )
    # the REST API wraps the output in `result`...
    aioclient_mock.post(url, json={"result": {"image": b64(b"PIC")}, "success": True})
    key = f"{ACCOUNT}:tok"
    flux_1 = "@cf/black-forest-labs/flux-1-schnell"
    got = await generate_image(session, "cloudflare", key, flux_1, "prompt")
    assert got == b"PIC"
    request = aioclient_mock.mock_calls[0]
    assert (
        request[2] == {"prompt": "prompt"}
        and request[3]["Authorization"] == "Bearer tok"
    )
    # ...a binding does not
    aioclient_mock.clear_requests()
    aioclient_mock.post(url, json={"image": b64(b"PIC2")})
    assert await generate_image(session, "cloudflare", key, flux_1, "p") == b"PIC2"


async def test_cloudflare_flux_2_takes_a_form(hass, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    url = image_providers.CLOUDFLARE_URL.format(
        account=ACCOUNT, model="@cf/black-forest-labs/flux-2-dev"
    )
    aioclient_mock.post(url, json={"result": {"image": b64(b"PIC")}})
    # the default model, and one written without its `@`, are understood
    assert PROVIDERS["cloudflare"].default_model == "@cf/black-forest-labs/flux-2-dev"
    key = f"{ACCOUNT}:tok"
    assert await generate_image(session, "cloudflare", key, "", "p") == b"PIC"
    got = await generate_image(
        session, "cloudflare", key, "cf/black-forest-labs/flux-2-dev", "p"
    )
    assert got == b"PIC"
    form = aioclient_mock.mock_calls[0][2]
    assert isinstance(form, image_providers.FormData)
    names = [field[0]["name"] for field in form._fields]
    assert names == ["prompt", "width", "height"]


async def test_cloudflare_refuses_what_it_cannot_use(hass, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    for key, model in (
        ("tok", ""),  # no account id
        (f"{ACCOUNT}:", ""),  # no token
        ("../x:tok", ""),  # not an account id: nothing is sent
        (f"{ACCOUNT}:tok", "gpt-image-1"),  # not a Workers AI model
    ):
        with pytest.raises(ProviderError):
            await generate_image(session, "cloudflare", key, model, "p")
    assert aioclient_mock.call_count == 0
    url = image_providers.CLOUDFLARE_URL.format(
        account=ACCOUNT, model="@cf/black-forest-labs/flux-2-dev"
    )
    aioclient_mock.post(
        url,
        status=401,
        json={"success": False, "errors": [{"code": 10000, "message": "Bad token"}]},
    )
    with pytest.raises(ProviderError, match="Bad token") as refused:
        await generate_image(session, "cloudflare", f"{ACCOUNT}:tok", "", "p")
    assert refused.value.code == "provider_key_refused"
    aioclient_mock.clear_requests()
    aioclient_mock.post(url, json={"result": {}, "success": True})
    with pytest.raises(ProviderError) as empty:
        await generate_image(session, "cloudflare", f"{ACCOUNT}:tok", "", "p")
    assert empty.value.code == "provider_no_image"


async def test_gemini_asks_for_a_wide_picture(hass, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    aioclient_mock.post(GEMINI, json=gemini_reply(b"PIC"))
    await generate_image(async_get_clientsession(hass), "gemini", "k", "", "p")
    config = aioclient_mock.mock_calls[0][2]["generationConfig"]
    assert config["imageConfig"] == {"aspectRatio": "3:2"}


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
    assert [p["id"] for p in status["providers"]] == ["gemini", "openai", "cloudflare"]
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
    # fish and plants have an atlas to make, corals do not
    assert "result" in await call(
        editor, "image_status", section="plants", kind="plant"
    )
    assert "error" in await call(editor, "image_status", section="corals", kind="coral")


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
    assert "#00FF00" in green["prompt"] and PROMPT["version"] == 2
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


async def test_the_animation_of_a_built_atlas_can_be_played(
    editor, hass, aioclient_mock
):
    configure(hass)
    aioclient_mock.post(GEMINI, json=gemini_reply(photo_bytes()))
    photo = (
        await call(editor, "image_generate", section="fish", kind="fish", species="X y")
    )["result"]
    atlas = (await call(editor, "image_build", **NEW, photo=photo["token"]))["result"]
    view = (await call(editor, "atlas_view", atlas=atlas["token"], **NEW))["result"]
    # the sheet itself travels, with the layout of its frames and clips
    assert view["image"].startswith("data:image/webp;base64,")
    assert view["frame"] == atlas["frame"] and view["columns"] == 8
    assert view["clips"]["swim"] == {"from": 0, "to": 42, "fps": 24, "loop": True}
    assert view["clips"]["turn"]["loop"] is False and view["facing"] == "right"
    # an unknown token, another entry's atlas, and an entry without animation
    lost = await call(editor, "atlas_view", atlas="nope", **NEW)
    assert lost["error"]["code"] == "unknown_atlas"
    other = {"section": "fish", "kind": "fish", "entry_id": "other_species"}
    wrong = await call(editor, "atlas_view", atlas=atlas["token"], **other)
    assert wrong["error"]["code"] == "atlas_mismatch"
    none = await call(editor, "atlas_view", **other)
    assert none["error"]["code"] == "no_atlas"
    coral = await call(
        editor, "atlas_view", section="corals", kind="coral", entry_id="a"
    )
    assert coral["error"]["code"] == "no_atlas"


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
    # the animation is played from the user's own file, once saved
    reply = await call(editor, "atlas_view", **NEW)
    assert "result" in reply, reply
    view = reply["result"]
    assert view["url"].endswith(
        "/fish/amphiprion_percula/amphiprion_percula.webp?v=u1"
    ) or ("/fish/amphiprion_percula/amphiprion_percula.webp?v=" in view["url"])
    assert view["degraded"] is True and view["columns"] == 8
    assert set(view["clips"]) == {"swim", "idle", "turn"}
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


# -- plants: a specimen on a flat background, regenerated until it suits ----------------

PLANT = {"section": "plants", "kind": "plant", "species": "Egeria densa"}
STEM = {"zone": "background", "names": {"en": "Brazilian waterweed"}}


def plant_bytes(bg=(255, 0, 255), leaf=(30, 150, 40), size=(600, 800)) -> bytes:
    """A stem with leaves, well inside the picture."""
    image = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(image)
    w, h = size
    draw.rectangle((w * 0.47, h * 0.15, w * 0.53, h * 0.85), fill=leaf)
    for i in range(6):
        y = h * (0.2 + i * 0.1)
        draw.ellipse((w * 0.3, y, w * 0.5, y + 50), fill=leaf)
        draw.ellipse((w * 0.5, y + 20, w * 0.7, y + 70), fill=leaf)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


async def test_a_plant_prompt_follows_its_growth_form_and_background(editor):
    ask = {**PLANT, "descriptor": STEM}
    reply = (await call(editor, "image_prompt", **ask))["result"]
    assert reply["key"] == "magenta" and reply["advice"] is None
    assert "flat magenta" in reply["prompt"] and "Egeria densa" in reply["prompt"]
    # green is not advised for a plant that is not listed, but it can be forced
    green = (await call(editor, "image_prompt", **ask, key="green"))["result"]
    assert "flat green" in green["prompt"] and green["advice"]
    assert green["default_key"] == "magenta"
    # a listed plant is asked on green by default, without a warning
    listed = (
        await call(
            editor,
            "image_prompt",
            **{**ask, "species": "Ludwigia repens"},
            entry_id="ludwigia_repens",
        )
    )["result"]
    assert listed["key"] == "green" and listed["advice"] is None
    # no zone, no growth form
    lost = await call(editor, "image_prompt", **PLANT)
    assert lost["error"]["code"] == "no_growth_form"


async def test_a_plant_photo_is_asked_with_its_ratio_and_shown_keyed_out(
    editor, hass, aioclient_mock
):
    configure(hass)
    aioclient_mock.post(GEMINI, json=gemini_reply(plant_bytes()))
    reply = (await call(editor, "image_generate", **PLANT, descriptor=STEM))["result"]
    sent = aioclient_mock.mock_calls[-1][2]["generationConfig"]["imageConfig"]
    assert sent == {"aspectRatio": "3:4"}
    assert reply["problems"] == [] and reply["key"] == "magenta"
    assert reply["keyed"].startswith("data:image/webp") and reply["advice"] is None
    assert reply["default_key"] == "magenta"
    # trying again on another background is the same call with another key
    aioclient_mock.clear_requests()
    aioclient_mock.post(GEMINI, json=gemini_reply(plant_bytes((0, 255, 0))))
    again = (
        await call(editor, "image_generate", **PLANT, descriptor=STEM, key="green")
    )["result"]
    assert again["key"] == "green" and again["advice"]
    assert again["token"] != reply["token"]
    assert {reply["token"], again["token"]} <= set(hass.data[T].photos)
    sent = aioclient_mock.mock_calls[-1][2]["contents"][0]["parts"][0]["text"]
    assert "flat green" in sent


async def test_a_plant_atlas_is_built_and_only_from_a_plant_photo(
    editor, hass, aioclient_mock
):
    configure(hass)
    aioclient_mock.post(GEMINI, json=gemini_reply(plant_bytes()))
    plant = (await call(editor, "image_generate", **PLANT, descriptor=STEM))["result"]
    build = {**AT, "section": "plants", "kind": "plant", "entry_id": "egeria_densa"}
    done = (await call(editor, "image_build", **build, photo=plant["token"]))["result"]
    assert done["frame"] == [320, 320] and done["source"]["type"] == "ai-generated"
    pending = hass.data[T].atlases[done["token"]][0]
    assert pending.keys["kind"] == "plant" and pending.keys["columns"] == 1
    # a fish photo is not the photo of a plant
    aioclient_mock.clear_requests()
    aioclient_mock.post(GEMINI, json=gemini_reply(photo_bytes()))
    fish = (await call(editor, "image_generate", **ask_fish()))["result"]
    wrong = await call(editor, "image_build", **build, photo=fish["token"])
    assert wrong["error"]["code"] == "photo_kind"


def ask_fish() -> dict:
    return {"section": "fish", "kind": "fish", "species": "Amphiprion percula"}


async def test_a_plant_photo_can_be_uploaded(editor, hass, hass_client):
    http = await hass_client()
    form = FormData()
    form.add_field("file", plant_bytes(), filename="p.png", content_type="image/png")
    form.add_field("kind", "plant")
    body = await (await http.post("/api/catalog_editor/photo", data=form)).json()
    assert body["problems"] == [] and body["keyed"].startswith("data:image/webp")
    assert hass.data[T].photos[body["token"]][0].kind == "plant"


def test_a_green_plant_on_a_green_background_is_seen_eaten():
    """Why green is advised against: the key makes the plant grey and transparent."""
    photo = images.inspect_photo(
        plant_bytes((0, 255, 0), (40, 170, 40)), {"type": "photo"}, "green", "plant"
    )
    keyed = images.key_out(images._open(photo.blob), "green")
    share = int((np.asarray(keyed.getchannel("A")) > 128).sum())
    plain = images.inspect_photo(plant_bytes(), {"type": "photo"}, "magenta", "plant")
    kept = images.key_out(images._open(plain.blob), "magenta")
    assert share < int((np.asarray(kept.getchannel("A")) > 128).sum())


def blob_picture(blob: bytes) -> Image.Image:
    return Image.open(io.BytesIO(blob)).convert("RGB")


def box_bytes(box: tuple[float, float, float, float], size=(600, 800)) -> bytes:
    """A plant drawn as a filled box (fractions of the picture) on magenta."""
    image = Image.new("RGB", size, (255, 0, 255))
    w, h = size
    ImageDraw.Draw(image).rectangle(
        (w * box[0], h * box[1], w * box[2], h * box[3]), fill=(30, 150, 40)
    )
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def test_a_plant_is_measured_on_its_larger_side():
    # narrow and tall: too small for a fish (its width), fine for a plant
    tall = blob_picture(box_bytes((0.45, 0.1, 0.6, 0.9)))
    assert any("too small" in p for p in images.check_photo(tall))
    assert images.check_plant_photo(tall) == []
    # small both ways: too small for a plant as well
    tiny = blob_picture(box_bytes((0.45, 0.45, 0.6, 0.6)))
    problems = images.check_plant_photo(tiny)
    assert problems == ["the plant is too small in the picture (under 40%)"]


def test_a_plant_prompt_refuses_an_unknown_background():
    with pytest.raises(ValueError, match="key must be one of"):
        plant.render_plant_prompt("egeria_densa", STEM, "blue")
