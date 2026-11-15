"""Websocket commands and image upload of the editor (administrators only)."""

from __future__ import annotations

import base64
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from homeassistant.components.websocket_api import async_register_command
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import (
    async_response,
    require_admin,
    websocket_command,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.http import HomeAssistantView

# Home Assistant validates with probatio since 2026.9: schemas must come from it
if TYPE_CHECKING:
    import probatio as vol  # pyright: ignore[reportMissingImports]
else:
    try:
        import probatio as vol
    except ImportError:  # pragma: no cover - depends on the installed HA version
        import voluptuous as vol

from .catalog_rules import DESCRIPTORS, Report, validate_draft
from .catalog_runtime import SIGNAL_USER_CATALOG_CHANGED, CatalogUpdater
from .const import DOMAIN, MAX_UPLOADS, SECTION_KINDS, UPLOAD_TTL_S, VIEW_GROUPS
from .context import (
    build_context,
    list_entries,
    locate_visual,
    provider,
    strip_entry,
)
from .forms import build_form, suggest_id
from .hints import HAS_VISUAL
from .images import MAX_UPLOAD_BYTES, ImageError, Visual, process_image
from .schemas import SchemaStore
from .storage import UserCatalog, dump

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
}


@dataclass
class EditorData:
    """Run-time state of the integration."""

    schemas: SchemaStore
    catalog: UserCatalog
    #: token -> (processed picture, expiry on the monotonic clock)
    uploads: dict[str, tuple[Visual, float]] = field(default_factory=dict)

    def prune(self) -> None:
        """Forget expired uploads, then the oldest ones above the limit."""
        now = time.monotonic()
        self.uploads = {k: v for k, v in self.uploads.items() if v[1] > now}
        while len(self.uploads) > MAX_UPLOADS:
            del self.uploads[min(self.uploads, key=lambda k: self.uploads[k][1])]

    def store(self, visual: Visual) -> str:
        """Keep an uploaded picture until the entry is saved."""
        self.prune()
        token = secrets.token_urlsafe(16)
        self.uploads[token] = (visual, time.monotonic() + UPLOAD_TTL_S)
        self.prune()
        return token


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
    updater: CatalogUpdater
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
    updater = provider(hass, section)
    if updater is None:
        raise _Refused(
            "no_provider", f"No integration reading the {section} catalog is loaded"
        )
    if need_schemas and not data.schemas.ready(section):
        await data.schemas.async_refresh(section)
        if not data.schemas.ready(section):
            raise _Refused(
                "schemas_unavailable",
                data.schemas.errors.get(section, "Schemas not downloaded yet"),
            )
    return _Target(data, updater, section, kind, await updater.async_view())


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
            except _Refused as err:
                connection.send_error(msg["id"], err.code, str(err))
                return
            connection.send_result(msg["id"], result)

        handler.__name__ = f"ws_{name}"
        return handler

    return decorator


# -- drafts -----------------------------------------------------------------------


async def _visuals(
    hass: HomeAssistant, target: _Target, msg: dict[str, Any]
) -> dict[str, bytes]:
    """The visuals the entry will have once saved, by file name.

    A new upload; else the ones of the user's own entry; else the ones of the
    entry of the catalog being overridden (so that overriding keeps its visual).
    """
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
            path = locate_visual(target.updater, entry, key) if entry else None
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


async def _check(
    hass: HomeAssistant, target: _Target, msg: dict[str, Any]
) -> tuple[Report, dict[str, bytes]]:
    """Everything the catalog CI checks about a draft."""
    entry_id, kind = msg["entry_id"], target.kind
    visuals = await _visuals(hass, target, msg)
    files = {name: len(blob) for name, blob in visuals.items()}
    if kind != "task":
        files[DESCRIPTORS[kind]] = len(dump(msg["data"]))
    context = build_context(target.view, target.section, exclude=(kind, entry_id))
    report = validate_draft(
        kind,
        entry_id,
        msg["data"],
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


def _report(report: Report) -> dict[str, list[str]]:
    return {"errors": report.errors, "warnings": report.warnings}


# -- commands ---------------------------------------------------------------------


@_command({}, "catalogs")
async def ws_catalogs(hass: HomeAssistant, msg: dict[str, Any]) -> list[dict[str, Any]]:
    """The sections: which integration provides each, and whether it is editable."""
    data = _data(hass)
    if data is None:
        raise _Refused("not_loaded", "The editor is not loaded")
    result = []
    for section, kinds in SECTION_KINDS.items():
        updater = provider(hass, section)
        result.append(
            {
                "section": section,
                "kinds": list(kinds),
                "provider": updater.spec.domain if updater else None,
                "schemas": data.schemas.ready(section),
                "schema_error": data.schemas.errors.get(section),
            }
        )
    return result


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
    return {
        "data": strip_entry(target.kind, entry, target.view),
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
    report, visuals = await _check(hass, target, msg)
    if report.errors:
        return {"saved": False, **_report(report)}
    await hass.async_add_executor_job(
        target.data.catalog.write,
        target.section,
        target.kind,
        entry_id,
        msg["data"],
        visuals,
    )
    target.data.uploads.pop(msg.get("visual", ""), None)
    async_dispatcher_send(hass, SIGNAL_USER_CATALOG_CHANGED, target.section)
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
    async_dispatcher_send(hass, SIGNAL_USER_CATALOG_CHANGED, target.section)
    return {"deleted": True}


# -- upload -----------------------------------------------------------------------


class ImageUploadView(HomeAssistantView):
    """`POST /api/reeftech_catalog_editor/image` with a `file` field."""

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


def async_register_api(hass: HomeAssistant) -> None:
    """Register the commands and the upload endpoint (once per run)."""
    if hass.data.get(f"{DOMAIN}_api"):
        return
    hass.data[f"{DOMAIN}_api"] = True
    for command in (
        ws_catalogs,
        ws_form,
        ws_entries,
        ws_entry,
        ws_suggest_id,
        ws_validate,
        ws_save,
        ws_delete,
    ):
        async_register_command(hass, command)
    if getattr(hass, "http", None) is not None:
        hass.http.register_view(ImageUploadView())
