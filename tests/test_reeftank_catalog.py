"""The species of reeftank-catalog: its single release cut into sections, rules, forms."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import cast

import pytest
from aiohttp import ClientSession
from conftest import (
    REEFTANK_RELEASES,
    REEFTANK_SCHEMAS,
    REEFTANK_VERSION,
    serve,
    setup_editor,
)
from fake_github import REEFTANK, UP, FakeGithub
from test_api import call, sign_in

from custom_components.catalog_editor import (
    catalog_pack,
    catalog_runtime,
    catalogs,
    github,
    hints,
    reeftank_catalog_rules,
    rules,
)
from custom_components.catalog_editor.catalog_pack import PackClient, PackError
from custom_components.catalog_editor.context import entry_label, external_context
from custom_components.catalog_editor.forms import (
    build_form,
    species_id,
    suggest_id,
)
from custom_components.catalog_editor.reeftank_pack import (
    ReeftankPackClient,
    pack_client,
    section_manifest,
)
from custom_components.catalog_editor.storage import dump

NAMES = {
    lang: f"Clown {lang}" for lang in ("en", "fr", "de", "es", "it", "nl", "pl", "pt")
}
CLOWN = {
    "kind": "fish",
    "names": NAMES,
    "scientific": "Amphiprion ocellaris",
    "water_types": ["marine"],
    "size_cm": [6, 11],
    "behavior": {
        "profile": "hover",
        "band": [0.1, 0.5],
        "depth": [0.2, 0.7],
        "speed_cm_s": [2, 8],
        "turn_rate": 2,
    },
    "night": "hide",
    "feeding_response": 0.9,
    "frame": [220, 116],
    "columns": 9,
    "clips": {"swim": {"from": 0, "to": 71, "fps": 24, "loop": True}},
    "atlas": {"1x": "clown.webp"},
    "thumbnail": "thumb.webp",
    "facing": "right",
    "length_frac": 0.87,
}
# What the form sends: no kind, no picture keys
DRAFT = {
    key: value
    for key, value in CLOWN.items()
    if key not in reeftank_catalog_rules.PICTURE_KEYS and key != "kind"
}
AT = {"section": "fish", "kind": "fish", "entry_id": "amphiprion_ocellaris"}
PLANT = {
    "kind": "plant",
    "names": NAMES,
    "scientific": "Cryptocoryne wendtii",
    "water_types": ["freshwater"],
    "size_cm": [10, 25],
    "zone": "midground",
}


def species_zip(descriptor: dict, files: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("species.json", json.dumps(descriptor))
        for name, blob in (files or {}).items():
            archive.writestr(name, blob)
    return buffer.getvalue()


def serve_species(aioclient_mock, species: dict[str, tuple[dict, dict]]):
    """Serve a reeftank-catalog release holding `folder/id -> (descriptor, files)`."""
    entries = {}
    for key, (descriptor, files) in species.items():
        blob = species_zip(descriptor, files)
        file = key.replace("/", "-") + ".zip"
        entries[key] = {
            "version": REEFTANK_VERSION,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size": len(blob),
            "file": file,
        }
        aioclient_mock.get(
            f"{REEFTANK_RELEASES}/download/{REEFTANK_VERSION}/{file}", content=blob
        )
    serve(aioclient_mock, reeftank_entries=entries)
    # serve() clears the mocks: serve the archives again
    for key, (descriptor, files) in species.items():
        aioclient_mock.get(
            f"{REEFTANK_RELEASES}/download/{REEFTANK_VERSION}/{key.replace('/', '-')}.zip",
            content=species_zip(descriptor, files),
        )


@pytest.fixture
async def editor(hass, aioclient_mock, hass_ws_client):
    serve_species(
        aioclient_mock,
        {
            "fish/amphiprion_ocellaris": (
                CLOWN,
                {"clown.webp": b"RIFFclown", "thumb.webp": b"RIFFthumb"},
            ),
            "plants/cryptocoryne_wendtii": (PLANT, {}),
        },
    )
    await setup_editor(hass, aioclient_mock, release=False)
    return await hass_ws_client(hass)


@pytest.fixture
def gh(aioclient_mock, monkeypatch):
    monkeypatch.setattr(github, "FORK_DELAY_S", 0)
    return FakeGithub(aioclient_mock)


def manifest(entries: dict) -> dict:
    return {
        "version": "2026.11.0",
        "min_integration": "0.1.0",
        "notes": "n",
        "entries": entries,
        "schema": {"sha256": "a" * 64, "size": 10, "file": "schema.zip"},
    }


def record(**extra) -> dict:
    return {
        "version": "2026.10.0",
        "sha256": "b" * 64,
        "size": 100,
        "file": "f.zip",
        **extra,
    }


# -- the manifest of the single release, cut into sections ------------------------------


def test_the_manifest_is_cut_by_folder():
    raw = manifest(
        {
            "fish/amphiprion": record(),
            "plants/anubias": record(),
            "textures/live_rock": record(),
            "defaults/unknown_fish": record(),
        }
    )
    fish = section_manifest(raw, "fish")
    assert fish["section"] == "fish" and fish["format"] == 1
    assert fish["version"] == "2026.11.0"
    assert fish["min_integration"] == {"reeftank": "0.1.0"}
    assert fish["entries"] == {
        "fish.amphiprion": {
            "kind": "fish",
            "sha256": "b" * 64,
            "size": 100,
            "archive": "fish-2026.11.0/f.zip",
            "since": "2026.10.0",
        }
    }
    assert fish["schema"]["archive"] == "fish-2026.11.0/schema.zip"
    assert list(section_manifest(raw, "plants")["entries"]) == ["plant.anubias"]
    assert section_manifest(raw, "corals")["entries"] == {}
    # the client parses it like the manifest of any other section
    parsed = catalog_pack.parse_manifest(fish, "fish")
    assert parsed.entries["fish.amphiprion"].rel_dir.as_posix() == "fish/amphiprion"
    assert parsed.schema is not None


def test_what_the_client_cannot_take_is_left_out(caplog):
    raw = manifest(
        {
            "fish/Bad_Case": record(),
            "fish/not_an_object": "x",
            "fish/too_big": record(size=catalog_pack.MAX_ENTRY_BYTES + 1),
            "fish/no_size": record(size="big"),
            "fish/fine": record(),
        }
    )
    del raw["min_integration"], raw["schema"]
    cut = section_manifest(raw, "fish")
    assert list(cut["entries"]) == ["fish.fine"]
    assert "min_integration" not in cut and "schema" not in cut
    assert "Entry fish/Bad_Case of reeftank-catalog ignored" in caplog.text
    with pytest.raises(PackError):
        section_manifest([], "fish")
    with pytest.raises(PackError):
        section_manifest({"version": "1"}, "fish")


def test_each_section_gets_the_right_client(hass):
    session = cast("ClientSession", object())
    for section in ("fish", "corals", "plants", "invertebrates"):
        assert isinstance(pack_client(session, section), ReeftankPackClient)
    other = pack_client(session, "equipment")
    assert type(other) is PackClient
    # the shared packs of the editor build their client with it
    assert catalog_runtime.PackClient is pack_client
    assert catalogs.pack_client is pack_client
    client = pack_client(session, "fish")
    assert client.repo == "Elwinmage/reeftank-catalog"
    assert client.manifest_url == f"{REEFTANK_RELEASES}/latest/download/manifest.json"
    assert client.release_url("2026.11.0") == f"{REEFTANK_RELEASES}/tag/2026.11.0"


async def test_the_client_reads_the_release(hass, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    serve_species(aioclient_mock, {"fish/amphiprion_ocellaris": (CLOWN, {})})
    client = pack_client(async_get_clientsession(hass), "fish")
    latest = await client.latest()
    assert list(latest.entries) == ["fish.amphiprion_ocellaris"]
    assert latest.schema is not None
    blob = await client.entry(latest.entries["fish.amphiprion_ocellaris"])
    assert zipfile.ZipFile(io.BytesIO(blob)).namelist() == ["species.json"]
    schema = await client.entry(latest.schema)
    assert "fish.schema.json" in zipfile.ZipFile(io.BytesIO(schema)).namelist()
    # a damaged download is refused
    bad = copy.copy(latest.entries["fish.amphiprion_ocellaris"])
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{REEFTANK_RELEASES}/download/{REEFTANK_VERSION}/fish-amphiprion_ocellaris.zip",
        content=b"x" * bad.size,
    )
    with pytest.raises(PackError):
        await client.entry(bad)


async def test_an_unreadable_manifest_is_refused(hass, aioclient_mock):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    aioclient_mock.get(
        f"{REEFTANK_RELEASES}/latest/download/manifest.json", content=b"\xff{"
    )
    client = pack_client(async_get_clientsession(hass), "fish")
    with pytest.raises(PackError, match="unreadable manifest"):
        await client.latest()


# -- declaration and rules --------------------------------------------------------------


def test_the_kinds_follow_their_catalog():
    assert rules.rules_of("fish") is reeftank_catalog_rules
    assert rules.rules_of("invertebrate") is reeftank_catalog_rules
    assert (
        rules.FOLDERS["coral"] == "corals"
        and rules.DESCRIPTORS["plant"] == "species.json"
    )
    assert rules.asset_files("fish") == {} and rules.asset_files("item")
    assert rules.languages("fish")[-3:] == ("nl", "pl", "pt")
    assert "nl" in rules.ALL_LANGS and "nl" not in rules.KNOWN_LANGS
    assert rules.hidden_keys("fish")[0] == "kind" and "atlas" in rules.hidden_keys(
        "fish"
    )
    assert rules.hidden_keys("item") == ()
    assert list(rules.complete("fish", {"night": "hide"})) == ["kind", "night"]
    assert rules.complete("item", {"a": 1}) == {"a": 1}
    assert hints.HAS_VISUAL["fish"] is False and hints.HAS_VISUAL["tree"] is True
    assert hints.ID_FROM["coral"] == ("scientific",)


def test_a_species_id_is_its_scientific_name():
    assert species_id("Acanthurus leucosternon") == "acanthurus_leucosternon"
    assert species_id("Amphiprion sp.") == "amphiprion"
    assert species_id("Hippocampus kuda kuda") == "hippocampus_kuda_kuda"
    assert species_id("  ") == ""
    assert suggest_id("fish", {"scientific": "Amphiprion sp."}, set()) == "amphiprion"
    taken = {"amphiprion", "amphiprion_2"}
    assert suggest_id("fish", {"scientific": "Amphiprion sp."}, taken) == "amphiprion_3"
    assert suggest_id("fish", {}, set()) == ""
    # the others keep their way
    assert suggest_id("task", {"name": {"en": "Clean me"}}, set()) == "clean-me"


def test_a_species_is_named_after_its_english_name():
    assert entry_label("fish", "x", CLOWN) == "Clown en"
    assert entry_label("fish", "x", {}) == "x"


def schemas() -> dict:
    return {
        path.name.split(".")[0]: json.loads(path.read_text())
        for path in REEFTANK_SCHEMAS.glob("*.schema.json")
    }


def flat(fields, prefix=""):
    found = {}
    for field in fields:
        name = f"{prefix}{field['name']}"
        found[name] = field["type"]
        if field["type"] == "object":
            found |= flat(field["fields"], f"{name}.")
        if field["type"] == "list" and field["item"].get("type") == "object":
            found |= flat(field["item"]["fields"], f"{name}[].")
    return found


def test_the_forms_ask_for_the_description_only():
    fish = build_form("fish", schemas())
    assert (fish["section"], fish["has_visual"], fish["id_from"]) == (
        "fish",
        False,
        ["scientific"],
    )
    # only a fish has a photo to make an animation from
    assert fish["has_atlas"] is True
    assert build_form("plant", schemas())["has_atlas"] is False
    fields = flat(fish["fields"])
    assert "json" not in {t for n, t in fields.items() if n != "behavior.shoal"}
    assert fields["names"] == "i18n" and fields["scientific"] == "string"
    assert fields["water_types"] == "multi_enum" and fields["size_cm"] == "range"
    assert fields["behavior.band"] == "range" and fields["behavior.profile"] == "enum"
    assert fields["behavior.burrow"] == "boolean" and fields["night"] == "enum"
    # the fixed value and what the pictures are made of are not asked for
    assert not {
        "kind",
        "atlas",
        "thumbnail",
        "frame",
        "columns",
        "clips",
        "source",
    } & set(fields)
    names = next(f for f in fish["fields"] if f["name"] == "names")
    assert names["languages"] == list(reeftank_catalog_rules.KNOWN_LANGS)
    assert names["required_languages"] == names["languages"]
    size = next(f for f in fish["fields"] if f["name"] == "size_cm")
    assert size["bounds"] == {"minimum": 0.1}
    band = next(f for f in flat_fields(fish) if f["name"] == "band")
    assert band["bounds"] == {"minimum": 0, "maximum": 1}

    coral = flat(build_form("coral", schemas())["fields"])
    assert coral["palette"] == "list" and coral["palette[].default"] == "color"
    assert coral["palette[].fluo"] == "boolean"
    assert build_form("plant", schemas())["fields"][-1]["options"][0] == "background"
    invertebrate = flat(build_form("invertebrate", schemas())["fields"])
    assert invertebrate["role"] == "multi_enum" and invertebrate["movement"] == "enum"


def flat_fields(form):
    for field in form["fields"]:
        yield field
        if field["type"] == "object":
            yield from field["fields"]


def test_a_reef_form_keeps_its_languages_and_widgets():
    """Nothing changes for the catalogs that do not say which languages they use."""
    from conftest import SCHEMAS

    common = json.loads((SCHEMAS / "common.schema.json").read_text())
    task = json.loads((SCHEMAS / "task.schema.json").read_text())
    form = build_form("task", {"common": common, "task": task})
    name = next(f for f in form["fields"] if f["name"] == "name")
    assert name["languages"] == list(rules.KNOWN_LANGS)
    assert name["required_languages"] == ["en"]


def test_the_context_holds_the_species_of_the_section():
    view = {"fish": {"a": {"scientific": "A b", "source": "pack"}, "b": CLOWN}}
    context = external_context(view, "fish", ("fish", "b"))
    assert isinstance(context, reeftank_catalog_rules.Context)
    assert list(context.fish) == ["a"] and not context.corals


# -- the editor with the species ----------------------------------------------------------


async def test_the_species_are_listed_per_catalog(editor):
    reply = await call(editor, "catalogs")
    assert "result" in reply, reply
    catalogs_ = reply["result"]
    fish = next(c for c in catalogs_ if c["section"] == "fish")
    assert fish["installed"] == REEFTANK_VERSION and fish["schemas"] is True
    answer = await call(editor, "entries", section="fish", kind="fish")
    assert "result" in answer, answer
    listed = answer["result"]
    assert [(e["id"], e["label"], e["source"]) for e in listed] == [
        ("amphiprion_ocellaris", "Clown en", "pack")
    ]
    plants = (await call(editor, "entries", section="plants", kind="plant"))["result"]
    assert [e["id"] for e in plants] == ["cryptocoryne_wendtii"]
    assert (await call(editor, "entries", section="corals", kind="coral"))[
        "result"
    ] == []
    answer = await call(editor, "form", section="fish", kind="fish")
    assert "names" in {f["name"] for f in answer["result"]["fields"]}, answer


async def test_an_entry_comes_with_its_picture_keys(editor):
    entry = (await call(editor, "entry", **AT))["result"]
    assert entry["data"] == CLOWN and entry["source"] == "pack"


async def test_an_id_is_suggested_from_the_scientific_name(editor):
    result = await call(
        editor,
        "suggest_id",
        section="fish",
        kind="fish",
        data={"scientific": "Amphiprion ocellaris"},
    )
    assert result["result"] == {"id": "amphiprion_ocellaris_2"}


async def test_a_new_species_is_saved_with_its_kind(editor, hass):
    new = {**AT, "entry_id": "amphiprion_percula"}
    draft = {**DRAFT, "scientific": "Amphiprion percula"}
    saved = (await call(editor, "save", data=draft, new=True, **new))["result"]
    assert saved["saved"] is True, saved
    path = Path(hass.config.path("reeftech_catalog/user/fish/fish/amphiprion_percula"))
    written = json.loads((path / "species.json").read_text())
    assert next(iter(written)) == "kind" and written["kind"] == "fish"
    assert list(path.iterdir()) == [path / "species.json"]
    listed = (await call(editor, "entries", section="fish", kind="fish"))["result"]
    assert [e["id"] for e in listed] == ["amphiprion_ocellaris", "amphiprion_percula"]


async def test_a_draft_is_checked_with_the_rules_of_the_catalog(editor):
    bad = {**DRAFT, "size_cm": [20, 5], "scientific": "amphiprion"}
    del bad["night"]
    bad["names"] = {"en": "Clown"}
    result = (await call(editor, "validate", data=bad, **AT))["result"]
    errors = " ".join(result["errors"])
    assert "night" in errors and "scientific" in errors and "names" in errors
    ordered = (
        await call(editor, "validate", data={**DRAFT, "size_cm": [20, 5]}, **AT)
    )["result"]
    assert any("must not exceed" in e for e in ordered["errors"]) or ordered["errors"]
    refused = (await call(editor, "save", data=bad, **AT))["result"]
    assert refused["saved"] is False and refused["errors"]
    taken = await call(editor, "save", data=DRAFT, new=True, **AT)
    assert taken["error"]["code"] == "id_taken"
    other = {**AT, "entry_id": "Bad Id"}
    wrong = (await call(editor, "validate", data=DRAFT, **other))["result"]
    assert any("not a valid id" in e for e in wrong["errors"])


async def test_the_same_scientific_name_is_a_warning(editor):
    other = {**AT, "entry_id": "clown_two"}
    result = (await call(editor, "validate", data=DRAFT, **other))["result"]
    assert result["errors"] == []
    assert any(
        "already the species amphiprion_ocellaris" in w for w in result["warnings"]
    )


async def test_an_edited_species_keeps_its_pictures_keys(editor, hass):
    edited = {**CLOWN, "feeding_response": 0.5}
    saved = (await call(editor, "save", data=edited, **AT))["result"]
    assert saved["saved"] is True, saved
    path = Path(
        hass.config.path("reeftech_catalog/user/fish/fish/amphiprion_ocellaris")
    )
    written = json.loads((path / "species.json").read_text())
    assert (
        written["atlas"] == {"1x": "clown.webp"} and written["feeding_response"] == 0.5
    )
    # the picture itself is not the editor's to copy: the pull request leaves it alone
    assert list(path.iterdir()) == [path / "species.json"]


async def test_a_species_is_proposed_to_the_reeftank_catalog(editor, hass, gh):
    await sign_in(hass)
    new = {**AT, "entry_id": "amphiprion_percula"}
    draft = {**DRAFT, "scientific": "Amphiprion percula"}
    await call(editor, "save", data=draft, new=True, **new)
    done = (await call(editor, "contribute", attest=True, **new))["result"]
    assert done["submitted"] is True and done["number"] == 1
    assert done["url"] == f"https://github.com/{REEFTANK}/pull/1"
    assert gh.pulls == {} and list(gh.pulls_of[REEFTANK]) == [1]
    branch = gh.pulls_of[REEFTANK][1]["head"]["ref"]
    files = gh.files("elwin/reeftank-catalog", branch)
    assert set(files) == {"fish/amphiprion_percula/species.json"}
    assert files["fish/amphiprion_percula/species.json"] == dump(
        {"kind": "fish", **draft}
    )
    assert not any(path.startswith(f"/repos/{UP}") for _, path in gh.calls)


async def test_proposing_an_edit_leaves_the_pictures_of_the_catalog(editor, hass, gh):
    """The pictures of a species are named by its descriptor: none may be deleted."""
    await sign_in(hass)
    edited = {**CLOWN, "feeding_response": 0.5}
    await call(editor, "save", data=edited, **AT)
    # the catalog already holds the species with its pictures
    tree = {
        "fish/amphiprion_ocellaris/species.json": dump(CLOWN),
        "fish/amphiprion_ocellaris/thumb.webp": b"RIFFthumb",
        "fish/amphiprion_ocellaris/clown.webp": b"RIFFclown",
    }
    gh.set_files(REEFTANK, tree)
    done = (await call(editor, "contribute", attest=True, **AT))["result"]
    assert done["submitted"] is True
    assert (
        gh.pulls_of[REEFTANK][1]["request"]["title"]
        == "Update fish amphiprion_ocellaris"
    )
    branch = gh.pulls_of[REEFTANK][1]["head"]["ref"]
    files = gh.files("elwin/reeftank-catalog", branch)
    assert set(files) == set(tree)
    assert files["fish/amphiprion_ocellaris/thumb.webp"] == b"RIFFthumb"
    assert (
        json.loads(files["fish/amphiprion_ocellaris/species.json"])["feeding_response"]
        == 0.5
    )


def test_the_copy_of_the_client_is_the_one_of_the_catalog():
    text = Path(reeftank_catalog_rules.__file__).read_text()
    assert text.startswith("# Generated from reeftank-catalog/client/")
