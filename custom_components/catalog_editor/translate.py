"""Machine translation of the short texts of an entry (pre-fills its languages).

Google's public web endpoint is tried first, MyMemory when it fails. Neither
needs a key; both are best effort, so a failure only means the field stays empty.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
TIMEOUT = ClientTimeout(total=10)

#: Text longer than this is not sent (labels and short descriptions only)
MAX_TEXT = 500


class TranslateError(Exception):
    """No provider could translate."""


async def _google(session: ClientSession, text: str, source: str, target: str) -> str:
    params = {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}
    async with session.get(GOOGLE_URL, params=params, timeout=TIMEOUT) as response:
        response.raise_for_status()
        payload: Any = await response.json(content_type=None)
    return "".join(part[0] for part in payload[0] if part and part[0])


async def _mymemory(session: ClientSession, text: str, source: str, target: str) -> str:
    params = {"q": text, "langpair": f"{source}|{target}"}
    async with session.get(MYMEMORY_URL, params=params, timeout=TIMEOUT) as response:
        response.raise_for_status()
        payload: Any = await response.json(content_type=None)
    if payload.get("responseStatus") not in (200, "200"):
        raise TranslateError(str(payload.get("responseDetails")))
    return str(payload["responseData"]["translatedText"])


async def translate_one(
    session: ClientSession, text: str, source: str, target: str
) -> str:
    """The text in the target language; raises TranslateError."""
    for provider in (_google, _mymemory):
        try:
            result = (await provider(session, text, source, target)).strip()
        except (
            ClientError,
            TimeoutError,
            TranslateError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ):
            continue
        if result:
            return result
    raise TranslateError(f"cannot translate to {target}")


async def translate(
    session: ClientSession, text: str, source: str, targets: list[str]
) -> dict[str, str]:
    """Translations by language; the languages that failed are left out."""
    wanted = [lang for lang in dict.fromkeys(targets) if lang != source]
    results = await asyncio.gather(
        *(translate_one(session, text, source, lang) for lang in wanted),
        return_exceptions=True,
    )
    found = {
        lang: result
        for lang, result in zip(wanted, results, strict=True)
        if isinstance(result, str)
    }
    if wanted and not found:
        raise TranslateError("no translation service answered")
    return found
