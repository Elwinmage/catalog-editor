"""Machine translation of the languages of a field."""

from __future__ import annotations

import pytest
from conftest import setup_editor
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.catalog_editor.translate import (
    GOOGLE_URL,
    MYMEMORY_URL,
    TranslateError,
    translate,
)

T = "catalog_editor"


def google(aioclient_mock, target: str, text: str | None) -> None:
    """Google answers `text` (nothing: an error) for a target language."""
    from yarl import URL

    url = URL(GOOGLE_URL).with_query(
        {"client": "gtx", "sl": "en", "tl": target, "dt": "t", "q": "Heater"}
    )
    if text is None:
        aioclient_mock.get(url, status=500)
    else:
        aioclient_mock.get(url, json=[[[text, "Heater", None, None, 10]], None, "en"])


def mymemory(aioclient_mock, target: str, text: str | None) -> None:
    from yarl import URL

    url = URL(MYMEMORY_URL).with_query({"q": "Heater", "langpair": f"en|{target}"})
    if text is None:
        aioclient_mock.get(url, json={"responseStatus": 403, "responseDetails": "no"})
    else:
        aioclient_mock.get(
            url, json={"responseStatus": 200, "responseData": {"translatedText": text}}
        )


async def test_translate(hass, aioclient_mock):
    session = async_get_clientsession(hass)
    google(aioclient_mock, "fr", "Chauffage")
    google(aioclient_mock, "de", None)  # Google fails: MyMemory takes over
    mymemory(aioclient_mock, "de", "Heizung")
    google(aioclient_mock, "es", None)
    mymemory(aioclient_mock, "es", None)  # nobody answers: left out
    found = await translate(session, "Heater", "en", ["fr", "de", "es", "en", "fr"])
    assert found == {"fr": "Chauffage", "de": "Heizung"}


async def test_translate_nobody_answers(hass, aioclient_mock):
    google(aioclient_mock, "fr", None)
    mymemory(aioclient_mock, "fr", None)
    with pytest.raises(TranslateError):
        await translate(async_get_clientsession(hass), "Heater", "en", ["fr"])
    # Nothing to translate into: nothing to do, not an error
    assert await translate(async_get_clientsession(hass), "Heater", "en", ["en"]) == {}


async def test_ws_translate(hass, aioclient_mock, hass_ws_client):
    await setup_editor(hass, aioclient_mock)
    client = await hass_ws_client(hass)
    google(aioclient_mock, "fr", "Chauffage")
    await client.send_json_auto_id(
        {"type": f"{T}/translate", "text": "Heater", "source": "en", "targets": ["fr"]}
    )
    reply = await client.receive_json()
    assert reply["result"] == {"translations": {"fr": "Chauffage"}}
    google(aioclient_mock, "pl", None)
    mymemory(aioclient_mock, "pl", None)
    await client.send_json_auto_id(
        {"type": f"{T}/translate", "text": "Heater", "source": "en", "targets": ["pl"]}
    )
    reply = await client.receive_json()
    assert reply["error"]["code"] == "translate_failed"
