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
import re
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Protocol

from aiohttp import ClientError, ClientSession, ClientTimeout, FormData

TIMEOUT = ClientTimeout(total=180)
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
OPENAI_URL = "https://api.openai.com/v1/images/generations"
CLOUDFLARE_URL = (
    "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
)
#: A Cloudflare account id, and the name of one of its models (`@cf/<author>/<name>`)
_ACCOUNT_RE = re.compile(r"^[0-9a-f]{32}$")
_CF_MODEL_RE = re.compile(r"^@cf/[a-z0-9._-]+/[a-z0-9._-]+$")


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
    session: ClientSession,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any] | FormData,
) -> dict[str, Any]:
    """The JSON reply of a POST (JSON, or a form for `FormData`); errors become ProviderError."""
    try:
        # Explicit arguments (not **kwargs) so that the call is type-checked.
        if isinstance(body, FormData):
            request = session.post(url, headers=headers, timeout=TIMEOUT, data=body)
        else:
            request = session.post(url, headers=headers, timeout=TIMEOUT, json=body)
        async with request as response:
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
    if error is None and isinstance(payload, dict):
        errors = payload.get("errors")  # Cloudflare: a list of {code, message}
        error = errors[0] if isinstance(errors, list) and errors else None
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


#: Picture ratios asked for (a fish is wider than high, a stem plant the other way)
DEFAULT_ASPECT = "3:2"
#: Size asked of OpenAI and of the Cloudflare FLUX.2 models for each ratio
_OPENAI_SIZES = {"3:2": "1536x1024", "3:4": "1024x1536", "1:1": "1024x1024"}
_FLUX_SIZES = {"3:2": (1536, 1024), "3:4": (1024, 1536), "1:1": (1024, 1024)}


async def gemini(
    session: ClientSession,
    key: str,
    model: str,
    prompt: str,
    aspect: str = DEFAULT_ASPECT,
) -> bytes:
    """Google Gemini (`generateContent`, an image model)."""
    payload = await _post(
        session,
        GEMINI_URL.format(model=model),
        {"x-goog-api-key": key},
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": aspect},
            },
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


async def openai(
    session: ClientSession,
    key: str,
    model: str,
    prompt: str,
    aspect: str = DEFAULT_ASPECT,
) -> bytes:
    """OpenAI (`images/generations`)."""
    payload = await _post(
        session,
        OPENAI_URL,
        {"Authorization": f"Bearer {key}"},
        {
            "model": model,
            "prompt": prompt,
            "size": _OPENAI_SIZES.get(aspect, "1536x1024"),
            "n": 1,
        },
    )
    items = payload.get("data") or []
    if not items or not isinstance(items[0], dict) or not items[0].get("b64_json"):
        raise ProviderError("provider_no_image", "The image service sent no picture")
    return _decode(items[0]["b64_json"])


async def cloudflare(
    session: ClientSession,
    key: str,
    model: str,
    prompt: str,
    aspect: str = DEFAULT_ASPECT,
) -> bytes:
    """Cloudflare Workers AI (FLUX): the key is `<account id>:<API token>`."""
    account, _, token = key.partition(":")
    if not _ACCOUNT_RE.match(account.strip()) or not token.strip():
        raise ProviderError(
            "provider_key_refused",
            "The Cloudflare key is written <account id>:<API token>",
        )
    model = model.strip()
    if model.startswith("cf/"):  # the `@` is easily lost when typing
        model = f"@{model}"
    if not _CF_MODEL_RE.match(model):
        raise ProviderError("provider_refused", f"Not a Workers AI model: {model}")
    body: dict[str, Any] | FormData = {"prompt": prompt}
    if "/flux-2" in model:  # these take a form, not JSON, with the size of the picture
        width, height = _FLUX_SIZES.get(aspect, (1536, 1024))
        body = FormData()
        body.add_field("prompt", prompt)
        body.add_field("width", str(width))
        body.add_field("height", str(height))
    payload = await _post(
        session,
        CLOUDFLARE_URL.format(account=account.strip(), model=model),
        {"Authorization": f"Bearer {token.strip()}"},
        body,
    )
    # The REST API wraps the output in `result`; the Workers binding does not
    result = payload.get("result")
    output = result if isinstance(result, dict) else payload
    if not output.get("image"):
        raise ProviderError("provider_no_image", "The image service sent no picture")
    return _decode(output["image"])


class Generator(Protocol):
    """What a provider does: a picture from a prompt (`aspect` is optional)."""

    def __call__(
        self,
        session: ClientSession,
        key: str,
        model: str,
        prompt: str,
        aspect: str = DEFAULT_ASPECT,
    ) -> Awaitable[bytes]: ...


@dataclass(frozen=True)
class Provider:
    """An image model service."""

    id: str
    name: str
    default_model: str
    generate: Generator


PROVIDERS: dict[str, Provider] = {
    "gemini": Provider("gemini", "Google Gemini", "gemini-2.5-flash-image", gemini),
    "openai": Provider("openai", "OpenAI", "gpt-image-1", openai),
    "cloudflare": Provider(
        "cloudflare",
        "Cloudflare Workers AI",
        "@cf/black-forest-labs/flux-2-dev",
        cloudflare,
    ),
}


async def generate_image(
    session: ClientSession,
    provider: str,
    key: str,
    model: str,
    prompt: str,
    aspect: str = DEFAULT_ASPECT,
) -> bytes:
    """The picture a provider makes of a prompt (`aspect`: its ratio)."""
    return await PROVIDERS[provider].generate(
        session, key, model or PROVIDERS[provider].default_model, prompt, aspect
    )
