"""Websocket commands and image upload of the editor (administrators only)."""

from __future__ import annotations

import base64
import re
import secrets
import time
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

from .catalog_rules import DESCRIPTORS, Report, validate_draft
from .catalog_runtime import SIGNAL_USER_CATALOG_CHANGED
from .compat import vol
from .const import DOMAIN, MAX_UPLOADS, SECTION_KINDS, UPLOAD_TTL_S, VIEW_GROUPS
from .context import (
    build_context,
    entry_label,
    list_entries,
    locate_visual,
    strip_entry,
)
from .contribute import contribute
from .contributions import Contributions
from .forms import build_form, suggest_id
from .github import (
    GithubClient,
    GithubError,
    poll_login,
    start_login,
)
from .hints import HAS_VISUAL
from .images import MAX_UPLOAD_BYTES, ImageError, Visual, process_image
from .schemas import SchemaStore
from .source import SectionSource
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
    contributions: Contributions
    #: OAuth App of the editor (its client id is public)
    client_id: str
    #: Login in progress: device code, expiry (monotonic clock), poll interval
    login: tuple[str, float, int] | None = None
    #: token -> (processed picture, expiry on the monotonic clock)
    uploads: dict[str, tuple[Visual, float]] = field(default_factory=dict)
    #: The merged catalog of each section (shared pack + user layer)
    sources: dict[str, SectionSource] = field(default_factory=dict)

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
    source = data.sources[section]
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
    source = data.sources["parameters"]
    if source.installed is None:
        return {}
    view = await source.async_view()
    return {
        entry_id: strip_entry("parameter", entry, view)
        for entry_id, entry in view.get("items", {}).items()
    }


async def _check(
    hass: HomeAssistant, target: _Target, msg: dict[str, Any]
) -> tuple[Report, dict[str, bytes]]:
    """Everything the catalog CI checks about a draft."""
    entry_id, kind = msg["entry_id"], target.kind
    visuals = await _visuals(hass, target, msg)
    files = {name: len(blob) for name, blob in visuals.items()}
    if kind != "task":
        files[DESCRIPTORS[kind]] = len(dump(msg["data"]))
    context = build_context(
        target.view,
        target.section,
        exclude=(kind, entry_id),
        parameters=await _parameters(target.data, target.section),
    )
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
    for section, kinds in SECTION_KINDS.items():
        pack = data.sources[section].pack
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
    sections = [msg["section"]] if "section" in msg else list(SECTION_KINDS)
    for section in sections:
        source = data.sources[section]
        await source.pack.async_check(force=True)
        await data.schemas.async_refresh(section)
        await source.async_reload()
    # What reached the catalog no longer needs its local copy
    await _retire_merged(hass, data)
    return _catalogs(data)


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


# -- GitHub -----------------------------------------------------------------------


def _editor(hass: HomeAssistant) -> EditorData:
    data = _data(hass)
    if data is None:
        raise _Refused("not_loaded", "The editor is not loaded")
    return data


def _client(hass: HomeAssistant, data: EditorData) -> GithubClient:
    if data.contributions.token is None:
        raise _Refused("auth_required", "Sign in to GitHub first")
    return GithubClient(async_get_clientsession(hass), data.contributions.token)


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
    client = _client(hass, data)
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
    source = data.sources[item["section"]]
    if source.installed is None:
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
        client = _client(hass, data)
        try:
            for item in store.items:
                if item["state"] == "open":
                    item["state"] = (await client.pull(item["number"])).state
        except GithubError as err:
            await _signed_out(data, err)  # offline or refused: the last state stays
    await _retire_merged(hass, data)
    return store.items


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
        ws_refresh,
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
        ws_contributions,
    ):
        async_register_command(hass, command)
    if getattr(hass, "http", None) is not None:
        hass.http.register_view(ImageUploadView())
