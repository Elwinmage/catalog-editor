"""Websocket commands and image upload of the editor (administrators only)."""

from __future__ import annotations

import base64
import re
import secrets
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.websocket_api import async_register_command
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import (
    async_response,
    require_admin,
    websocket_command,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.http import HomeAssistantView

from .catalog_pack import repo_of
from .catalog_runtime import SIGNAL_USER_CATALOG_CHANGED
from .catalogs import EXTERNAL_KINDS
from .compat import vol
from .const import (
    CONF_IMAGE_KEY,
    CONF_IMAGE_MODEL,
    CONF_IMAGE_PROVIDER,
    DOMAIN,
    MAX_UPLOADS,
    SECTION_KINDS,
    UPLOAD_TTL_S,
    VIEW_GROUPS,
)
from .context import (
    ATLAS_FIELDS,
    build_context,
    count_brands,
    entry_label,
    external_context,
    list_entries,
    locate_visual,
    preferred_spellings,
    read_atlas,
    read_descriptor,
    strip_entry,
)
from .contribute import KIND_ORDER, BatchEntry, contribute, contribute_batch
from .contributions import Contributions
from .forms import build_form, suggest_id
from .github import (
    GithubClient,
    GithubError,
    poll_login,
    start_login,
)
from .hints import ATLAS_KINDS, HAS_VISUAL, SPECIES_KINDS
from .image_providers import PROVIDERS, ProviderError, generate_image
from .images import (
    MAX_PHOTO_BYTES,
    MAX_UPLOAD_BYTES,
    ImageError,
    Photo,
    Visual,
    atlas_preview,
    build_degraded,
    inspect_photo,
    photo_preview,
    process_image,
)
from .reeftank_catalog_still import KEYS as BACKGROUND_KEYS
from .reeftank_catalog_still import is_real_animation, render_prompt
from .rules import ALL_LANGS, DESCRIPTORS, Report, complete, validate_draft
from .schemas import SchemaStore
from .source import SectionSource
from .storage import UserCatalog, dump
from .translate import MAX_TEXT, TranslateError, translate

ALL_KINDS = sorted({kind for kinds in SECTION_KINDS.values() for kind in kinds})
_TARGET = {
    vol.Required("section"): vol.In(list(SECTION_KINDS)),
    vol.Required("kind"): vol.In(ALL_KINDS),
}
_ENTRY = {**_TARGET, vol.Required("entry_id"): str}
_DRAFT = {
    **_ENTRY,
    vol.Required("data"): dict,
    vol.Optional("visual"): str,  # token of an uploaded picture
    vol.Optional("remove_visual", default=False): bool,
    vol.Optional("atlas"): str,  # token of a degraded atlas built from a photo
}


@dataclass
class EditorData:
    """Run-time state of the integration."""

    schemas: SchemaStore
    catalog: UserCatalog
    contributions: Contributions
    #: OAuth App of the editor (its client id is public)
    client_id: str
    #: Login in progress: device code, expiry (monotonic clock), poll interval
    login: tuple[str, float, int] | None = None
    #: token -> (processed picture, expiry on the monotonic clock)
    uploads: dict[str, tuple[Visual, float]] = field(default_factory=dict)
    #: The merged catalog of each section (shared pack + user layer)
    sources: dict[str, SectionSource] = field(default_factory=dict)
    #: Image model of the contributor: provider, API key, model (options of the entry)
    image: dict[str, str] = field(default_factory=dict)
    #: token -> (photo, expiry): the photos waiting to become an atlas
    photos: dict[str, tuple[Photo, float]] = field(default_factory=dict)
    #: token -> (atlas, expiry): the atlases built, until the entry is saved
    atlases: dict[str, tuple[PendingAtlas, float]] = field(default_factory=dict)

    def prune(self) -> None:
        """Forget expired uploads, then the oldest ones above the limit."""
        for store in (self.uploads, self.photos, self.atlases):
            now = time.monotonic()
            for token in [k for k, v in store.items() if v[1] <= now]:
                del store[token]
            while len(store) > MAX_UPLOADS:
                del store[min(store, key=lambda k: store[k][1])]

    def store(self, visual: Visual) -> str:
        """Keep an uploaded picture until the entry is saved."""
        self.prune()
        token = secrets.token_urlsafe(16)
        self.uploads[token] = (visual, time.monotonic() + UPLOAD_TTL_S)
        self.prune()
        return token

    def keep(self, store: dict[str, Any], item: Any) -> str:
        """Keep a photo or an atlas (`photos`, `atlases`) until it is used."""
        self.prune()
        token = secrets.token_urlsafe(16)
        store[token] = (item, time.monotonic() + UPLOAD_TTL_S)
        self.prune()
        return token


@dataclass(frozen=True)
class PendingAtlas:
    """A degraded atlas built for an entry, to attach when it is saved."""

    section: str
    kind: str
    entry_id: str
    files: dict[str, bytes]
    keys: dict[str, Any]


def _data(hass: HomeAssistant) -> EditorData | None:
    return hass.data.get(DOMAIN)


class _Refused(Exception):
    """A command that cannot go on: an error code and its message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class _Target:
    data: EditorData
    source: SectionSource
    section: str
    kind: str
    view: dict[str, Any]


async def _target(
    hass: HomeAssistant, msg: dict[str, Any], need_schemas: bool = True
) -> _Target:
    data = _data(hass)
    if data is None:
        raise _Refused("not_loaded", "The editor is not loaded")
    section, kind = msg["section"], msg["kind"]
    if kind not in SECTION_KINDS[section]:
        raise _Refused("invalid_format", f"{section} has no {kind}")
    source = data.sources.get(section)
    if source is None:
        raise _Refused("not_subscribed", f"The {section} catalog is not subscribed to")
    if source.installed is None:
        raise _Refused(
            "not_installed",
            source.pack.last_error or f"The {section} catalog is not downloaded yet",
        )
    if need_schemas and not data.schemas.ready(section):
        await data.schemas.async_refresh(section)
        if not data.schemas.ready(section):
            raise _Refused(
                "schemas_unavailable",
                data.schemas.errors.get(section, "Schemas not downloaded yet"),
            )
    return _Target(data, source, section, kind, await source.async_view())


def _command(schema: dict[Any, Any], name: str):
    """Register-able administrator command whose `_Refused` become errors."""

    def decorator(func):
        @websocket_command({vol.Required("type"): f"{DOMAIN}/{name}", **schema})
        @require_admin
        @async_response
        async def handler(
            hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
        ) -> None:
            try:
                result = await func(hass, msg)
            except (_Refused, GithubError) as err:
                connection.send_error(msg["id"], err.code, str(err))
                return
            connection.send_result(msg["id"], result)

        handler.__name__ = f"ws_{name}"
        return handler

    return decorator


# -- drafts -----------------------------------------------------------------------


def _atlas(target: _Target, msg: dict[str, Any]) -> PendingAtlas | None:
    """The atlas built for this entry (None when the draft has none)."""
    token = msg.get("atlas")
    if token is None:
        return None
    target.data.prune()
    if token not in target.data.atlases:
        raise _Refused("unknown_atlas", "The atlas expired: build it again")
    atlas = target.data.atlases[token][0]
    if (atlas.section, atlas.kind, atlas.entry_id) != (
        target.section,
        target.kind,
        msg["entry_id"],
    ):
        raise _Refused("atlas_mismatch", "This atlas was built for another entry")
    return atlas


def _with_atlas(target: _Target, msg: dict[str, Any]) -> dict[str, Any]:
    """The draft with the descriptor keys of its atlas (the pictures it comes with)."""
    atlas = _atlas(target, msg)
    if atlas is None:
        return msg
    return {**msg, "data": {**msg["data"], **atlas.keys}}


async def _visuals(
    hass: HomeAssistant, target: _Target, msg: dict[str, Any]
) -> dict[str, bytes]:
    """The visuals the entry will have once saved, by file name.

    A new upload; else the ones of the user's own entry; else the ones of the
    entry of the catalog being overridden (so that overriding keeps its visual).
    """
    if target.kind in SPECIES_KINDS:
        atlas = _atlas(target, msg)
        if atlas is not None:
            return dict(atlas.files)
        # a species only ships the pictures the user made (never the catalog's)
        return await hass.async_add_executor_job(
            target.data.catalog.read_visuals,
            target.section,
            target.kind,
            msg["entry_id"],
        )
    if not HAS_VISUAL[target.kind] or msg["remove_visual"]:
        return {}
    token = msg.get("visual")
    if token is not None:
        target.data.prune()
        if token not in target.data.uploads:
            raise _Refused("unknown_upload", "The uploaded picture expired")
        visual = target.data.uploads[token][0]
        return {"image.webp": visual.image, "thumb.webp": visual.thumb}

    def read() -> dict[str, bytes]:
        own = target.data.catalog.read_visuals(
            target.section, target.kind, msg["entry_id"]
        )
        if own:
            return own
        entry = target.view.get(VIEW_GROUPS[target.kind], {}).get(msg["entry_id"])
        found: dict[str, bytes] = {}
        for key, default in (("image", "image.webp"), ("thumb", "thumb.webp")):
            path = locate_visual(target.source, entry, key) if entry else None
            if path is not None:
                name = default if key == "thumb" else path.name
                found[name] = path.read_bytes()
        return found

    return await hass.async_add_executor_job(read)


def _check_id(target: _Target, entry_id: str, report: Report) -> None:
    pattern = target.data.schemas.schemas[target.section]["common"]["$defs"]["id"]
    if (
        not re.fullmatch(pattern["pattern"], entry_id)
        or len(entry_id) > pattern["maxLength"]
    ):
        report.error(
            "id", f"{entry_id!r} is not a valid id (lower case, digits, - and _)"
        )


async def _parameters(data: EditorData, section: str) -> dict[str, dict[str, Any]]:
    """The parameters a water test refers to, from the parameters catalog.

    Empty when that catalog is not downloaded (the test is then not cross-checked).
    """
    if section != "water_tests":
        return {}
    source = data.sources.get("parameters")
    if source is None or source.installed is None:
        return {}
    view = await source.async_view()
    return {
        entry_id: strip_entry("parameter", entry, view)
        for entry_id, entry in view.get("items", {}).items()
    }


async def _brand_counts(
    data: EditorData, exclude: tuple[str, str, str] | None = None
) -> dict[str, Counter[str]]:
    """How the brands are written in every catalog the editor is subscribed to."""
    views = {
        section: await source.async_view()
        for section, source in data.sources.items()
        if source.installed is not None
    }
    return count_brands(views, exclude)


async def _check(
    hass: HomeAssistant, target: _Target, msg: dict[str, Any]
) -> tuple[Report, dict[str, bytes]]:
    """Everything the catalog CI checks about a draft."""
    msg = _with_atlas(target, msg)
    entry_id, kind = msg["entry_id"], target.kind
    visuals = await _visuals(hass, target, msg)
    draft = complete(kind, msg["data"])
    files = {name: len(blob) for name, blob in visuals.items()}
    if kind != "task":
        files[DESCRIPTORS[kind]] = len(dump(draft))
    context: Any
    if kind in EXTERNAL_KINDS:
        context = external_context(target.view, target.section, (kind, entry_id))
    else:
        context = build_context(
            target.view,
            target.section,
            exclude=(kind, entry_id),
            parameters=await _parameters(target.data, target.section),
            brands=preferred_spellings(
                await _brand_counts(target.data, (target.section, kind, entry_id))
            ),
        )
    report = validate_draft(
        kind,
        entry_id,
        draft,
        files,
        context,
        target.data.schemas.validators_of(kind),
    )
    _check_id(target, entry_id, report)
    token = msg.get("visual")
    if token in target.data.uploads and not target.data.uploads[token][0].has_alpha:
        report.warn(
            f"{kind}/{entry_id}",
            "the picture has no transparent background, it will be shown on a box",
        )
    return report, visuals


async def _user_changed(hass: HomeAssistant, source: SectionSource) -> None:
    """The user layer changed: reload the editor's view, tell the integrations."""
    source.user_revision += 1
    await source.async_reload()
    async_dispatcher_send(hass, SIGNAL_USER_CATALOG_CHANGED, source.section)


def _report(report: Report) -> dict[str, list[str]]:
    return {"errors": report.errors, "warnings": report.warnings}


# -- commands ---------------------------------------------------------------------


def _catalogs(data: EditorData) -> list[dict[str, Any]]:
    """The state of each section: the pack downloaded, the release, the schemas."""
    result = []
    for section, source in data.sources.items():
        kinds = SECTION_KINDS[section]
        pack = source.pack
        result.append(
            {
                "section": section,
                "kinds": list(kinds),
                "installed": pack.installed.version if pack.installed else None,
                "latest": pack.latest.version if pack.latest else None,
                "update_available": pack.update_available,
                "in_progress": pack.in_progress,
                "progress": pack.progress,
                "error": pack.last_error,
                "schemas": data.schemas.ready(section),
                "schema_error": data.schemas.errors.get(section),
            }
        )
    return result


@_command({}, "catalogs")
async def ws_catalogs(hass: HomeAssistant, msg: dict[str, Any]) -> list[dict[str, Any]]:
    """The sections: which release of each is downloaded, and whether it is editable."""
    return _catalogs(_editor(hass))


@_command({vol.Optional("section"): vol.In(list(SECTION_KINDS))}, "refresh")
async def ws_refresh(hass: HomeAssistant, msg: dict[str, Any]) -> list[dict[str, Any]]:
    """Check the releases now, install the new ones (and download a missing one).

    A section, or all of them. Every integration reading the catalog gets the new
    pack too (it is shared). A failure is reported in the `error` of the section.
    """
    data = _editor(hass)
    sections = [msg["section"]] if "section" in msg else list(data.sources)
    if any(section not in data.sources for section in sections):
        raise _Refused("not_subscribed", "That catalog is not subscribed to")
    for section in sections:
        source = data.sources[section]
        await source.pack.async_check(force=True)
        await data.schemas.async_refresh(section)
        await source.async_reload()
    # What reached the catalog no longer needs its local copy
    await _retire_merged(hass, data)
    return _catalogs(data)


@_command({}, "brands")
async def ws_brands(hass: HomeAssistant, msg: dict[str, Any]) -> list[dict[str, Any]]:
    """The brands of the catalogs, to choose one instead of typing it again.

    `name` is the spelling to use; `key` is what the spellings have in common (a new
    brand whose key is one of these is the same brand written another way).
    """
    counts = await _brand_counts(_editor(hass))
    names = preferred_spellings(counts)
    return sorted(
        (
            {"key": key, "name": names[key], "count": sum(spellings.values())}
            for key, spellings in counts.items()
        ),
        key=lambda brand: brand["name"].lower(),
    )


@_command(_TARGET, "form")
async def ws_form(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    """The fields of a kind of entry, from the schema of the current release."""
    target = await _target(hass, msg)
    return build_form(target.kind, target.data.schemas.schemas_of(target.kind))


@_command(_TARGET, "entries")
async def ws_entries(hass: HomeAssistant, msg: dict[str, Any]) -> list[dict[str, Any]]:
    """The entries of a kind, to pick one to edit or to refer to."""
    target = await _target(hass, msg, need_schemas=False)
    return list_entries(target.view, target.kind)


@_command(_ENTRY, "entry")
async def ws_entry(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    """An entry as it is written, for the form."""
    target = await _target(hass, msg, need_schemas=False)
    entry = target.view.get(VIEW_GROUPS[target.kind], {}).get(msg["entry_id"])
    if entry is None:
        raise _Refused("not_found", f"No {target.kind} {msg['id']!r}")
    own = await hass.async_add_executor_job(
        target.data.catalog.has, target.section, target.kind, msg["entry_id"]
    )
    raw = await hass.async_add_executor_job(
        read_descriptor, target.source, target.kind, msg["entry_id"]
    )
    return {
        "data": raw
        if raw is not None
        else strip_entry(target.kind, entry, target.view),
        "source": entry.get("source"),
        "image": entry.get("image"),
        "thumb": entry.get("thumb"),
        "user_copy": own,
    }


@_command({**_TARGET, vol.Required("data"): dict}, "suggest_id")
async def ws_suggest_id(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, str]:
    """An id for a new entry, free in the catalog."""
    target = await _target(hass, msg, need_schemas=False)
    taken = set(target.view.get(VIEW_GROUPS[target.kind], {}))
    return {"id": suggest_id(target.kind, msg["data"], taken)}


@_command(_DRAFT, "validate")
async def ws_validate(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, list[str]]:
    """Errors and warnings of a draft, as the catalog CI would report them."""
    target = await _target(hass, msg)
    report, _ = await _check(hass, target, msg)
    return _report(report)


@_command({**_DRAFT, vol.Optional("new", default=False): bool}, "save")
async def ws_save(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    """Write a valid draft in the user layer; every integration then reloads it."""
    target = await _target(hass, msg)
    entry_id = msg["entry_id"]
    if msg["new"] and entry_id in target.view.get(VIEW_GROUPS[target.kind], {}):
        raise _Refused("id_taken", f"{target.kind} {entry_id!r} already exists")
    msg = _with_atlas(target, msg)
    report, visuals = await _check(hass, target, msg)
    if report.errors:
        return {"saved": False, **_report(report)}
    await hass.async_add_executor_job(
        target.data.catalog.write,
        target.section,
        target.kind,
        entry_id,
        complete(target.kind, msg["data"]),
        visuals,
    )
    target.data.uploads.pop(msg.get("visual", ""), None)
    target.data.atlases.pop(msg.get("atlas", ""), None)
    await _user_changed(hass, target.source)
    return {"saved": True, "id": entry_id, **_report(report)}


@_command(_ENTRY, "delete")
async def ws_delete(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, bool]:
    """Remove an entry of the user (an entry of the catalog itself stays)."""
    target = await _target(hass, msg, need_schemas=False)
    removed = await hass.async_add_executor_job(
        target.data.catalog.delete, target.section, target.kind, msg["entry_id"]
    )
    if not removed:
        raise _Refused("not_found", f"No entry of yours: {target.kind} {msg['id']!r}")
    await _user_changed(hass, target.source)
    return {"deleted": True}


# -- photos and atlases of the species -------------------------------------------------

MAX_SPECIES = 200
_IMAGE_TARGET = {
    vol.Required("section"): vol.In(list(SECTION_KINDS)),
    vol.Required("kind"): vol.In(list(ATLAS_KINDS)),
}
_KEY = vol.In(list(BACKGROUND_KEYS))


def _settings(data: EditorData) -> tuple[str, str, str] | None:
    """Provider, API key and model of the contributor; None until set."""
    provider = data.image.get(CONF_IMAGE_PROVIDER)
    key = data.image.get(CONF_IMAGE_KEY)
    if provider not in PROVIDERS or not key:
        return None
    return provider, key, data.image.get(CONF_IMAGE_MODEL) or ""


async def _photo_reply(
    hass: HomeAssistant, data: EditorData, photo: Photo
) -> dict[str, Any]:
    """What the card needs to show a photo and to ask for its atlas."""
    preview = await hass.async_add_executor_job(photo_preview, photo.blob)
    return {
        "token": data.keep(data.photos, photo),
        "width": photo.size[0],
        "height": photo.size[1],
        "problems": list(photo.problems),
        "key": photo.key,
        "source": photo.source,
        "preview": preview,
    }


@_command(_IMAGE_TARGET, "image_status")
async def ws_image_status(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    """What the card needs to offer the generation of a photo (never the key)."""
    target = await _target(hass, msg)
    settings = _settings(target.data)
    source = target.data.schemas.schemas[target.section]["common"]["$defs"]["source"]
    return {
        "configured": settings is not None,
        "provider": settings[0] if settings else None,
        "model": (
            settings[2] or PROVIDERS[settings[0]].default_model if settings else None
        ),
        "providers": [{"id": p.id, "name": p.name} for p in PROVIDERS.values()],
        "keys": list(BACKGROUND_KEYS),
        "licenses": source["properties"]["license"]["enum"],
    }


@_command(
    {
        **_IMAGE_TARGET,
        vol.Required("species"): vol.All(str, vol.Length(min=2, max=MAX_SPECIES)),
        vol.Optional("key", default="magenta"): _KEY,
    },
    "image_prompt",
)
async def ws_image_prompt(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, str]:
    """The fixed prompt for a species, to use with any image tool by hand."""
    return {"prompt": render_prompt(msg["species"].strip(), msg["key"])}


@_command(
    {
        **_IMAGE_TARGET,
        vol.Required("species"): vol.All(str, vol.Length(min=2, max=MAX_SPECIES)),
        vol.Optional("key", default="magenta"): _KEY,
    },
    "image_generate",
)
async def ws_image_generate(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    """Ask the contributor's image model for the photo of a species."""
    data = _editor(hass)
    settings = _settings(data)
    if settings is None:
        raise _Refused(
            "image_not_configured", "Set an image provider and its API key first"
        )
    provider, api_key, model = settings
    name = model or PROVIDERS[provider].default_model
    try:
        blob = await generate_image(
            async_get_clientsession(hass),
            provider,
            api_key,
            model,
            render_prompt(msg["species"].strip(), msg["key"]),
        )
        photo = await hass.async_add_executor_job(
            inspect_photo, blob, {"type": "ai-generated", "model": name}, msg["key"]
        )
    except ProviderError as err:
        raise _Refused(err.code, str(err)) from err
    except ImageError as err:
        raise _Refused(str(err), f"The generated picture is refused: {err}") from err
    return await _photo_reply(hass, data, photo)


def _entry_id_ok(target: _Target, entry_id: str) -> bool:
    pattern = target.data.schemas.schemas[target.section]["common"]["$defs"]["id"]
    return (
        re.fullmatch(pattern["pattern"], entry_id) is not None
        and len(entry_id) <= pattern["maxLength"]
    )


@_command(
    {
        **_IMAGE_TARGET,
        vol.Required("entry_id"): str,
        vol.Required("photo"): str,
        vol.Optional("key"): _KEY,
        vol.Optional("author"): str,
        vol.Optional("license"): str,
        vol.Optional("force", default=False): bool,
    },
    "image_build",
)
async def ws_image_build(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    """Build the degraded atlas of an entry from a photo (kept until it is saved)."""
    target = await _target(hass, msg)
    data, entry_id = target.data, msg["entry_id"]
    data.prune()
    if msg["photo"] not in data.photos:
        raise _Refused("unknown_photo", "The photo expired: send it again")
    photo = data.photos[msg["photo"]][0]
    if not _entry_id_ok(target, entry_id):
        raise _Refused("invalid_id", f"{entry_id!r} is not a valid id for the files")
    if photo.problems and not msg["force"]:
        raise _Refused("photo_unfit", "; ".join(photo.problems))
    current = await hass.async_add_executor_job(
        read_descriptor, target.source, target.kind, entry_id
    )
    if is_real_animation(current) and not msg["force"]:
        raise _Refused(
            "real_animation", "This species already has an animation made from videos"
        )
    source = {"type": photo.source["type"]}
    if "model" in photo.source:
        source["model"] = photo.source["model"]
    else:
        for field_name in ("author", "license"):
            if not msg.get(field_name):
                raise _Refused(
                    "source_incomplete", f"A photo needs its {field_name} (source)"
                )
            source[field_name] = msg[field_name]
    source["date"] = datetime.now(UTC).date().isoformat()
    try:
        still = await hass.async_add_executor_job(
            build_degraded, photo, entry_id, source, msg.get("key")
        )
    except ImageError as err:
        raise _Refused(str(err), f"The photo is refused: {err}") from err
    pending = PendingAtlas(
        target.section, target.kind, entry_id, still.files, still.keys
    )
    return {
        "token": data.keep(data.atlases, pending),
        "preview": atlas_preview(still),
        "frame": still.keys["frame"],
        "source": source,
    }


@_command({**_ENTRY, vol.Optional("atlas"): str}, "atlas_view")
async def ws_atlas_view(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    """What the card plays to show the animation of a species.

    The atlas just built (its token), else the one the entry has: the sheet (a
    `data:` URL for a built one, the URL it is served at otherwise) and the
    layout of its frames and clips.
    """
    target = await _target(hass, msg, need_schemas=False)
    if target.kind not in ATLAS_KINDS:
        raise _Refused("no_atlas", f"A {target.kind} has no animation")
    pending = _atlas(target, msg)
    if pending is not None:
        name = pending.keys["atlas"]["1x"]
        blob = pending.files[name]
        info = {k: pending.keys[k] for k in ATLAS_FIELDS if k in pending.keys}
        return {
            **info,
            "image": f"data:image/webp;base64,{base64.b64encode(blob).decode()}",
        }
    found = await hass.async_add_executor_job(
        read_atlas, target.source, target.kind, msg["entry_id"]
    )
    if found is None:
        raise _Refused("no_atlas", "This entry has no animation to play")
    return {**found[0], "url": found[1]}


# -- GitHub -----------------------------------------------------------------------


def _editor(hass: HomeAssistant) -> EditorData:
    data = _data(hass)
    if data is None:
        raise _Refused("not_loaded", "The editor is not loaded")
    return data


def _client(hass: HomeAssistant, data: EditorData, section: str) -> GithubClient:
    """A GitHub client on the repository publishing a section."""
    if data.contributions.token is None:
        raise _Refused("auth_required", "Sign in to GitHub first")
    return GithubClient(
        async_get_clientsession(hass), data.contributions.token, repo_of(section)
    )


@_command(
    {
        vol.Required("text"): vol.All(str, vol.Length(min=1, max=MAX_TEXT)),
        vol.Required("source"): vol.In(ALL_LANGS),
        vol.Required("targets"): [vol.In(ALL_LANGS)],
    },
    "translate",
)
async def ws_translate(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    """Machine translation of a text, to pre-fill the languages of a field."""
    try:
        found = await translate(
            async_get_clientsession(hass), msg["text"], msg["source"], msg["targets"]
        )
    except TranslateError as err:
        raise _Refused("translate_failed", str(err)) from err
    return {"translations": found}


async def _signed_out(data: EditorData, err: GithubError) -> None:
    """A refused token is of no use any more."""
    if err.code == "auth_required":
        await data.contributions.async_sign_out()


@_command({}, "github_status")
async def ws_github_status(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    """Whether the user is signed in to GitHub."""
    data = _editor(hass)
    return {
        "connected": data.contributions.token is not None,
        "login": data.contributions.login,
        "login_pending": data.login is not None and data.login[1] > time.monotonic(),
    }


@_command({}, "github_login")
async def ws_github_login(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    """Start the device flow: a code to type on github.com/login/device."""
    data = _editor(hass)
    code = await start_login(async_get_clientsession(hass), data.client_id)
    data.login = (code.device_code, time.monotonic() + code.expires_in, code.interval)
    return {
        "user_code": code.user_code,
        "verification_uri": code.verification_uri,
        "expires_in": code.expires_in,
        "interval": code.interval,
    }


@_command({}, "github_login_poll")
async def ws_github_login_poll(
    hass: HomeAssistant, msg: dict[str, Any]
) -> dict[str, Any]:
    """One check of the login in progress: pending, ok, expired or denied."""
    data = _editor(hass)
    if data.login is None:
        raise _Refused("no_login", "No login in progress")
    device_code, expiry, interval = data.login
    if expiry <= time.monotonic():
        data.login = None
        return {"status": "expired"}
    session = async_get_clientsession(hass)
    status, value = await poll_login(session, data.client_id, device_code)
    if status == "pending":
        interval = max(interval, int(value))
        data.login = (device_code, expiry, interval)
        return {"status": "pending", "interval": interval}
    data.login = None
    if status != "ok":
        return {"status": status}
    login = await GithubClient(session, str(value)).login()
    await data.contributions.async_sign_in(str(value), login)
    return {"status": "ok", "login": login}


@_command({}, "github_logout")
async def ws_github_logout(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, bool]:
    """Forget the GitHub token."""
    await _editor(hass).contributions.async_sign_out()
    return {"connected": False}


@_command({**_ENTRY, vol.Required("attest"): bool}, "contribute")
async def ws_contribute(hass: HomeAssistant, msg: dict[str, Any]) -> dict[str, Any]:
    """Propose an entry of the user to the catalog as a pull request."""
    target = await _target(hass, msg)
    if not msg["attest"]:
        raise _Refused(
            "attestation_required", "Certify the picture is yours (CC BY 4.0)"
        )
    data = target.data
    section, kind, entry_id = target.section, target.kind, msg["entry_id"]
    client = _client(hass, data, section)
    if not await hass.async_add_executor_job(data.catalog.has, section, kind, entry_id):
        raise _Refused("no_user_copy", "Save the entry first")
    entry = await hass.async_add_executor_job(
        data.catalog.read, section, kind, entry_id
    )
    report, visuals = await _check(
        hass, target, {**msg, "data": entry, "remove_visual": False}
    )
    if report.errors:
        return {"submitted": False, **_report(report)}
    previous = data.contributions.find(section, kind, entry_id)
    try:
        pull, update, appended = await contribute(
            client,
            str(data.contributions.login),
            previous=previous,
            kind=kind,
            entry_id=entry_id,
            label=entry_label(kind, entry_id, entry),
            data=entry,
            visuals=visuals,
        )
    except GithubError as err:
        await _signed_out(data, err)
        raise
    now = datetime.now(UTC).isoformat(timespec="seconds")
    await data.contributions.async_record(
        {
            "section": section,
            "kind": kind,
            "id": entry_id,
            "label": entry_label(kind, entry_id, entry),
            "number": pull.number,
            "url": pull.url,
            "branch": pull.branch,
            "state": pull.state,
            "update": update,
            "created": previous["created"] if appended and previous else now,
            "released": False,
        }
    )
    return {
        "submitted": True,
        "number": pull.number,
        "url": pull.url,
        "appended": appended,
        **_report(report),
    }


#: Entries a single pull request may hold
MAX_BATCH = 50


@_command({}, "pending")
async def ws_pending(hass: HomeAssistant, msg: dict[str, Any]) -> list[dict[str, Any]]:
    """The entries of the user, to propose together (dependency order).

    `open_pr` is the pull request an entry is already in, if any: it is proposed on
    its own (a commit added to that pull request), not in a batch.
    """
    data = _editor(hass)

    def read() -> list[dict[str, Any]]:
        found = []
        for section in data.sources:
            for kind, entry_id in data.catalog.entries(section, SECTION_KINDS[section]):
                try:
                    entry = data.catalog.read(section, kind, entry_id)
                except (OSError, ValueError):
                    continue
                found.append(
                    {
                        "section": section,
                        "kind": kind,
                        "id": entry_id,
                        "label": entry_label(kind, entry_id, entry),
                    }
                )
        return found

    result = await hass.async_add_executor_job(read)
    for item in result:
        open_pr = data.contributions.find(item["section"], item["kind"], item["id"])
        item["open_pr"] = open_pr["number"] if open_pr else None
    result.sort(key=lambda i: (KIND_ORDER.index(i["kind"]), i["section"], i["id"]))
    return result


@_command(
    {
        vol.Required("entries"): vol.All([_ENTRY], vol.Length(min=1, max=MAX_BATCH)),
        vol.Required("attest"): bool,
    },
    "contribute_batch",
)
async def ws_contribute_batch(
    hass: HomeAssistant, msg: dict[str, Any]
) -> dict[str, Any]:
    """Propose several entries of the user as ONE pull request, a commit each.

    One pull request per catalog repository: entries of the house catalog do not
    travel with the ones of the reef catalog.
    """
    data = _editor(hass)
    if not msg["attest"]:
        raise _Refused(
            "attestation_required", "Certify the pictures are yours (CC BY 4.0)"
        )
    if data.contributions.token is None:
        raise _Refused("auth_required", "Sign in to GitHub first")
    batch: list[BatchEntry] = []
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for item in msg["entries"]:
        key = (item["section"], item["kind"], item["entry_id"])
        if key in seen:
            continue
        seen.add(key)
        section, kind, entry_id = key
        target = await _target(hass, item)
        if not await hass.async_add_executor_job(
            data.catalog.has, section, kind, entry_id
        ):
            raise _Refused("no_user_copy", f"{kind} {entry_id}: save the entry first")
        open_pr = data.contributions.find(section, kind, entry_id)
        if open_pr is not None:
            raise _Refused(
                "already_proposed",
                f"{kind} {entry_id} is already in the pull request #{open_pr['number']}",
            )
        entry = await hass.async_add_executor_job(
            data.catalog.read, section, kind, entry_id
        )
        report, visuals = await _check(
            hass, target, {**item, "data": entry, "remove_visual": False}
        )
        errors += report.errors
        warnings += report.warnings
        batch.append(
            BatchEntry(
                section,
                kind,
                entry_id,
                entry_label(kind, entry_id, entry),
                entry,
                visuals,
            )
        )
    if errors:
        return {"submitted": False, "errors": errors, "warnings": warnings}
    by_repo: dict[str, list[BatchEntry]] = {}
    for entry in batch:
        by_repo.setdefault(repo_of(entry.section), []).append(entry)
    pulls: list[dict[str, Any]] = []
    skipped: list[BatchEntry] = []
    for repo, entries in by_repo.items():
        client = _client(hass, data, entries[0].section)
        try:
            pull, done, same = await contribute_batch(
                client, str(data.contributions.login), entries
            )
        except GithubError as err:
            if err.code == "no_change" and len(by_repo) > 1:
                skipped += entries  # this catalog has them all, another may not
                continue
            await _signed_out(data, err)
            raise
        skipped += same
        now = datetime.now(UTC).isoformat(timespec="seconds")
        await data.contributions.async_record(
            *(
                {
                    "section": entry.section,
                    "kind": entry.kind,
                    "id": entry.entry_id,
                    "label": entry.label,
                    "number": pull.number,
                    "url": pull.url,
                    "branch": pull.branch,
                    "state": pull.state,
                    "update": update,
                    "created": now,
                    "released": False,
                }
                for entry, update in done
            )
        )
        pulls.append(
            {"repo": repo, "number": pull.number, "url": pull.url, "count": len(done)}
        )
    if not pulls:
        raise GithubError("no_change", "Nothing differs from the catalogs")
    return {
        "submitted": True,
        # The first pull request, for a card that shows a single one
        "number": pulls[0]["number"],
        "url": pulls[0]["url"],
        "pulls": pulls,
        "count": sum(pull["count"] for pull in pulls),
        "skipped": [f"{entry.kind}/{entry.entry_id}" for entry in skipped],
        "warnings": warnings,
    }


def _released(data: EditorData, source: SectionSource, item: dict[str, Any]) -> bool:
    """The catalog the integrations run has the entry, as the user has it."""
    section, kind, entry_id = item["section"], item["kind"], item["id"]
    if not data.catalog.has(section, kind, entry_id):
        return False
    own = data.catalog.path_of(section, kind, entry_id)
    relative = own.relative_to(data.catalog.root(section))
    if kind != "task":
        relative /= DESCRIPTORS[kind]
    mine = (data.catalog.root(section) / relative).read_bytes()
    for layer in source.layers():
        if layer.name == "pack":
            theirs = layer.root / relative
            if theirs.is_file() and theirs.read_bytes() == mine:
                return True
    return False


async def _retire(hass: HomeAssistant, data: EditorData, item: dict[str, Any]) -> None:
    """Once a merged entry reached the catalog, the local copy is redundant."""
    source = data.sources.get(item["section"])
    if source is None or source.installed is None:
        return
    if await hass.async_add_executor_job(_released, data, source, item):
        await hass.async_add_executor_job(
            data.catalog.delete, item["section"], item["kind"], item["id"]
        )
        item["released"] = True
        await _user_changed(hass, source)


async def _retire_merged(hass: HomeAssistant, data: EditorData) -> None:
    """Retire the local copy of every merged entry the catalog has now."""
    for item in data.contributions.items:
        if item["state"] == "merged" and not item.get("released"):
            await _retire(hass, data, item)
    await data.contributions.async_save()


@_command({}, "contributions")
async def ws_contributions(
    hass: HomeAssistant, msg: dict[str, Any]
) -> list[dict[str, Any]]:
    """The pull requests made with the editor, their state refreshed."""
    data = _editor(hass)
    store = data.contributions
    if store.token is not None:
        try:
            # A pull request is a number in the repository of its section
            states: dict[tuple[str, int], str] = {}
            for item in store.items:
                if item["state"] == "open":
                    key = (repo_of(item["section"]), item["number"])
                    if key not in states:
                        client = _client(hass, data, item["section"])
                        states[key] = (await client.pull(key[1])).state
                    item["state"] = states[key]
        except GithubError as err:
            await _signed_out(data, err)  # offline or refused: the last state stays
    await _retire_merged(hass, data)
    return store.items


# -- upload -----------------------------------------------------------------------


class ImageUploadView(HomeAssistantView):
    """`POST /api/catalog_editor/image` with a `file` field."""

    url = f"/api/{DOMAIN}/image"
    name = f"api:{DOMAIN}:image"

    async def post(self, request):
        """Normalise a picture and keep it until the entry is saved."""
        hass: HomeAssistant = request.app["hass"]
        data = _data(hass)
        if not request["hass_user"].is_admin:
            return self.json_message("Administrators only", 403, "unauthorized")
        if data is None:
            return self.json_message("The editor is not loaded", 503, "not_loaded")
        form = await request.post()
        upload = form.get("file")
        if not hasattr(upload, "file"):
            return self.json_message("Field 'file' expected", 400, "invalid_format")
        blob = upload.file.read(MAX_UPLOAD_BYTES + 1)
        try:
            visual = await hass.async_add_executor_job(process_image, blob)
        except ImageError as err:
            return self.json_message(f"Picture refused: {err}", 400, str(err))
        preview = base64.b64encode(visual.thumb).decode()
        return self.json(
            {
                "token": data.store(visual),
                "has_alpha": visual.has_alpha,
                "width": visual.size[0],
                "height": visual.size[1],
                "image_bytes": len(visual.image),
                "thumb_bytes": len(visual.thumb),
                "preview": f"data:image/webp;base64,{preview}",
            }
        )


class PhotoUploadView(HomeAssistantView):
    """`POST /api/catalog_editor/photo` with a `file` field: the photo of a species."""

    url = f"/api/{DOMAIN}/photo"
    name = f"api:{DOMAIN}:photo"

    async def post(self, request):
        """Check a photo and keep it until its atlas is built."""
        hass: HomeAssistant = request.app["hass"]
        data = _data(hass)
        if not request["hass_user"].is_admin:
            return self.json_message("Administrators only", 403, "unauthorized")
        if data is None:
            return self.json_message("The editor is not loaded", 503, "not_loaded")
        form = await request.post()
        upload = form.get("file")
        if not hasattr(upload, "file"):
            return self.json_message("Field 'file' expected", 400, "invalid_format")
        blob = upload.file.read(MAX_PHOTO_BYTES + 1)
        key = form.get("key")
        try:
            photo = await hass.async_add_executor_job(
                inspect_photo,
                blob,
                {"type": "photo"},
                key if key in BACKGROUND_KEYS else None,
            )
            reply = await _photo_reply(hass, data, photo)
        except ImageError as err:
            return self.json_message(f"Photo refused: {err}", 400, str(err))
        return self.json(reply)


def async_register_api(hass: HomeAssistant) -> None:
    """Register the commands and the upload endpoint (once per run)."""
    if hass.data.get(f"{DOMAIN}_api"):
        return
    hass.data[f"{DOMAIN}_api"] = True
    for command in (
        ws_catalogs,
        ws_refresh,
        ws_translate,
        ws_brands,
        ws_form,
        ws_entries,
        ws_entry,
        ws_suggest_id,
        ws_validate,
        ws_save,
        ws_delete,
        ws_github_status,
        ws_github_login,
        ws_github_login_poll,
        ws_github_logout,
        ws_contribute,
        ws_pending,
        ws_contribute_batch,
        ws_contributions,
        ws_image_status,
        ws_image_prompt,
        ws_image_generate,
        ws_image_build,
        ws_atlas_view,
    ):
        async_register_command(hass, command)
    if getattr(hass, "http", None) is not None:
        hass.http.register_view(ImageUploadView())
        hass.http.register_view(PhotoUploadView())
