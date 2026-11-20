"""Image models the editor can ask for the photo of a species.

A provider turns a prompt into the bytes of a picture with the API key of the
contributor (the editor has none of its own, and the cost is the contributor's).
Providers are interchangeable: they share one signature and `PROVIDERS` lists
them, so another one is a function and a line. The key only goes in a request
header and never appears in a message.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

TIMEOUT = ClientTimeout(total=180)
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
OPENAI_URL = "https://api.openai.com/v1/images/generations"


class ProviderError(Exception):
    """The image model gave no picture: an error code and its message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _code(status: int) -> str:
    if status in (401, 403):
        return "provider_key_refused"
    if status == 429:
        return "provider_quota"
    return "provider_refused" if status == 400 else "provider_error"


async def _post(
    session: ClientSession, url: str, headers: dict[str, str], body: dict[str, Any]
) -> dict[str, Any]:
    """The JSON reply of a POST; errors become ProviderError."""
    try:
        async with session.post(
            url, headers=headers, json=body, timeout=TIMEOUT
        ) as response:
            status = response.status
            try:
                payload: Any = await response.json(content_type=None)
            except ValueError:
                payload = None
    except (ClientError, TimeoutError) as err:
        raise ProviderError(
            "provider_unreachable", "The image service cannot be reached"
        ) from err
    error = payload.get("error") if isinstance(payload, dict) else None
    if status >= 400:
        detail = error.get("message") if isinstance(error, dict) else None
        raise ProviderError(_code(status), str(detail or f"HTTP {status}"))
    if not isinstance(payload, dict):
        raise ProviderError("provider_no_image", "The image service sent no JSON")
    return payload


def _decode(data: Any) -> bytes:
    try:
        blob = base64.b64decode(str(data), validate=True)
    except (binascii.Error, ValueError) as err:
        raise ProviderError(
            "provider_no_image", "The picture of the service is not readable"
        ) from err
    return blob


async def gemini(session: ClientSession, key: str, model: str, prompt: str) -> bytes:
    """Google Gemini (`generateContent`, an image model)."""
    payload = await _post(
        session,
        GEMINI_URL.format(model=model),
        {"x-goog-api-key": key},
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        },
    )
    for candidate in payload.get("candidates") or []:
        parts = (candidate.get("content") or {}).get("parts") or []
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                return _decode(inline["data"])
    block = (payload.get("promptFeedback") or {}).get("blockReason")
    if block:
        raise ProviderError("provider_refused", f"The prompt was blocked: {block}")
    raise ProviderError("provider_no_image", "The image service sent no picture")


async def openai(session: ClientSession, key: str, model: str, prompt: str) -> bytes:
    """OpenAI (`images/generations`)."""
    payload = await _post(
        session,
        OPENAI_URL,
        {"Authorization": f"Bearer {key}"},
        {"model": model, "prompt": prompt, "size": "1536x1024", "n": 1},
    )
    items = payload.get("data") or []
    if not items or not isinstance(items[0], dict) or not items[0].get("b64_json"):
        raise ProviderError("provider_no_image", "The image service sent no picture")
    return _decode(items[0]["b64_json"])


@dataclass(frozen=True)
class Provider:
    """An image model service."""

    id: str
    name: str
    default_model: str
    generate: Callable[[ClientSession, str, str, str], Awaitable[bytes]]


PROVIDERS: dict[str, Provider] = {
    "gemini": Provider("gemini", "Google Gemini", "gemini-2.5-flash-image", gemini),
    "openai": Provider("openai", "OpenAI", "gpt-image-1", openai),
}


async def generate_image(
    session: ClientSession, provider: str, key: str, model: str, prompt: str
) -> bytes:
    """The picture a provider makes of a prompt."""
    return await PROVIDERS[provider].generate(
        session, key, model or PROVIDERS[provider].default_model, prompt
    )
