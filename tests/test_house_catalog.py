"""The catalogs of the house view (trees, objects): rules and a repository of their own."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from conftest import HOUSE_SCHEMAS, setup_editor
from fake_github import HOUSE, UP, FakeGithub
from test_api import RINSE, call, png, save_rinse, sign_in, upload

from custom_components.catalog_editor import (
    catalog_pack,
    catalog_rules,
    catalogs,
    const,
    github,
    hints,
    house_catalog_rules,
    house_catalog_sections,
    reeftank_catalog_sections,
    rules,
)
from custom_components.catalog_editor.context import house_context
from custom_components.catalog_editor.contribute import KIND_ORDER
from custom_components.catalog_editor.forms import build_form, suggest_id
from custom_components.catalog_editor.storage import dump


@pytest.fixture
async def editor(hass, aioclient_mock, providers, hass_ws_client):
    await setup_editor(hass, aioclient_mock)
    return await hass_ws_client(hass)


@pytest.fixture
def gh(aioclient_mock, monkeypatch):
    monkeypatch.setattr(github, "FORK_DELAY_S", 0)
    return FakeGithub(aioclient_mock)


OAK_AT = {"section": "trees", "kind": "tree", "entry_id": "oak"}
OAK = {
    "name": {"en": "Oak"},
    "latin": "Quercus robur",
    "shape": "round",
    "evergreen": True,
    "height": {"default": 9, "min": 4, "max": 25},
    "crown_radius": 3.8,
    "trunk": {"height": 3.2, "radius": 0.3, "color": "#5c4636"},
    "seasons": {"summer": {"foliage": "#3f7f35"}},
}
STOOL_AT = {"section": "objects", "kind": "object", "entry_id": "stool"}
STOOL = {
    "name": {"en": "Stool"},
    "category": "seating",
    "parts": [
        {
            "shape": "cylinder",
            "width": 0.3,
            "height": 0.45,
            "depth": 0.3,
            "color": "#b8915f",
        }
    ],
}


def schemas() -> dict[str, dict]:
    return {
        path.name.split(".")[0]: json.loads(path.read_text())
        for path in HOUSE_SCHEMAS.glob("*.schema.json")
    }


def flat(fields: list[dict], path: str = "") -> dict[str, str]:
    """Type of every field of a form, by dotted path."""
    found = {}
    for field in fields:
        name = f"{path}{field.get('name', '')}"
        found[name] = field["type"]
        if field["type"] == "object":
            found |= flat(field["fields"], f"{name}.")
        if field["type"] == "list" and field["item"]["type"] == "object":
            found |= flat(field["item"]["fields"], f"{name}[].")
    return found


async def save(client, at: dict, data: dict, hass_client=None) -> None:
    extra = {}
    if hass_client is not None:
        http = await hass_client()
        extra["visual"] = (await (await upload(http, png())).json())["token"]
    saved = (await call(client, "save", data=data, **at, **extra))["result"]
    assert saved["saved"] is True, saved


# -- declaration, rules, forms, context -----------------------------------------------


def test_the_house_sections_are_declared_to_the_client():
    """The client knows no house: the editor declares what house-catalog describes."""
    assert catalogs.EXTERNAL_SECTIONS == {
        **house_catalog_sections.SECTIONS,
        **reeftank_catalog_sections.SECTIONS,
    }
    assert catalogs.EXTERNAL_KINDS == (
        "tree",
        "object",
        "fish",
        "coral",
        "plant",
        "invertebrate",
    )
    assert {
        **dict.fromkeys(("trees", "objects"), "Elwinmage/house-catalog"),
        **dict.fromkeys(
            ("fish", "corals", "plants", "invertebrates"),
            "Elwinmage/reeftank-catalog",
        ),
    } == catalog_pack.SECTION_REPOS
    assert catalog_pack.repo_of("trees") == house_catalog_sections.REPO
    assert catalog_pack.repo_of("equipment") == catalog_pack.REPO
    assert catalog_pack.SECTION_KINDS["objects"] == frozenset({"object"})
    assert catalog_pack.KIND_LAYOUT["tree"] == ("items", "tree.json")
    # ...and everything the editor lists per kind follows from that description
    assert const.SECTION_KINDS["trees"] == ("tree",)
    assert const.SECTION_KINDS["objects"] == ("object",)
    assert list(const.SECTION_KINDS)[:4] == [
        "equipment",
        "supplements",
        "parameters",
        "water_tests",
    ]
    assert const.VIEW_GROUPS["tree"] == const.VIEW_GROUPS["object"] == "items"
    assert hints.ID_FROM["tree"] == hints.ID_FROM["object"] == ("name.en",)
    assert hints.HAS_VISUAL["tree"] is True and hints.HAS_VISUAL["task"] is False
    assert KIND_ORDER[-6:-4] == ("tree", "object") and KIND_ORDER[0] == "task"


def test_each_kind_has_the_rules_of_its_catalog():
    assert rules.rules_of("tree") is rules.rules_of("object") is house_catalog_rules
    assert rules.rules_of("item") is rules.rules_of("water_test") is catalog_rules
    assert rules.DESCRIPTORS["tree"] == "tree.json"
    assert rules.DESCRIPTORS["item"] == "item.json"
    assert rules.FOLDERS["object"] == "objects/items"
    assert rules.FOLDERS["task"] == catalog_rules.FOLDERS["task"]
    # the limits of the pictures and the languages are the same everywhere
    assert house_catalog_rules.ASSET_FILES == rules.ASSET_FILES
    assert house_catalog_rules.KNOWN_LANGS == rules.KNOWN_LANGS


def test_forms_are_drawn_without_raw_json():
    tree = build_form("tree", schemas())
    assert (tree["section"], tree["has_visual"], tree["id_from"]) == (
        "trees",
        True,
        ["name.en"],
    )
    fields = flat(tree["fields"])
    assert "json" not in fields.values()
    assert fields["name"] == "i18n" and fields["icon"] == "icon"
    assert fields["shape"] == "enum" and fields["evergreen"] == "boolean"
    assert fields["trunk.color"] == "color"
    assert fields["seasons.spring.foliage"] == "color"
    assert fields["seasons.autumn.fallen.color"] == "color"
    assert fields["height.default"] == "number" and fields["keywords"] == "list"

    thing = build_form("object", schemas())
    assert thing["section"] == "objects"
    fields = flat(thing["fields"])
    assert "json" not in fields.values()
    assert fields["parts"] == "list" and fields["parts[].color"] == "color"
    assert fields["parts[].shape"] == "enum" and fields["parts[].tint"] == "boolean"

    assert suggest_id("tree", {"name": {"en": "Cherry tree"}}, set()) == "cherry-tree"
    assert suggest_id("object", {"name": {"en": "Chair"}}, {"chair"}) == "chair-2"


def test_context_of_the_house_sections():
    view = {
        "items": {
            "oak": {**OAK, "source": "pack", "image": None, "thumb": None},
            "pine": {"latin": "Pinus", "source": "user", "image": "/i", "thumb": "/t"},
        }
    }
    trees = house_context(view, "trees", exclude=("tree", "pine"))
    assert isinstance(trees, house_catalog_rules.Context)
    assert trees.trees == {"oak": OAK} and trees.objects == {}
    things = house_context({"items": {"stool": {**STOOL, "source": "pack"}}}, "objects")
    assert isinstance(things, house_catalog_rules.Context)
    assert things.objects == {"stool": STOOL} and things.trees == {}


# -- the editor -----------------------------------------------------------------------


async def test_a_tree_is_checked_with_the_rules_of_its_catalog(editor, hass):
    form = (await call(editor, "form", section="trees", kind="tree"))["result"]
    assert form["kind"] == "tree" and "json" not in flat(form["fields"]).values()

    bad = copy.deepcopy(OAK)
    bad["trunk"]["height"] = 12
    bad["evergreen"] = False
    report = (await call(editor, "validate", data=bad, **OAK_AT))["result"]
    assert report["errors"] == [
        "trees/items/oak: trunk height 12 must be below the tree height 9"
    ]
    assert any("deciduous tree without spring" in w for w in report["warnings"])
    refused = (await call(editor, "save", data=bad, **OAK_AT))["result"]
    assert refused["saved"] is False

    await save(editor, OAK_AT, OAK)
    written = Path(hass.config.path("reeftech_catalog/user/trees/items/oak/tree.json"))
    assert json.loads(written.read_text()) == OAK
    listed = (await call(editor, "entries", section="trees", kind="tree"))["result"]
    assert [(e["id"], e["label"], e["source"]) for e in listed] == [
        ("oak", "Oak", "user")
    ]

    # the other trees are known: a botanical name is used once
    twin = await call(editor, "validate", data=OAK, **{**OAK_AT, "entry_id": "oak-2"})
    assert twin["result"]["errors"] == [
        "trees/items/oak-2: latin 'Quercus robur' already used by 'oak'"
    ]
    # ...but an entry is not checked against itself
    assert (await call(editor, "validate", data=OAK, **OAK_AT))["result"][
        "errors"
    ] == []

    off = copy.deepcopy(STOOL)
    off["parts"][0]["x"] = 0.5
    report = (await call(editor, "validate", data=off, **STOOL_AT))["result"]
    assert report["errors"] == [
        "objects/items/stool: footprint off centre along x: shift every part by -0.500 m"
    ]


async def test_a_tree_is_proposed_to_the_house_catalog(editor, hass, hass_client, gh):
    await sign_in(hass)
    await save(editor, OAK_AT, OAK, hass_client)
    done = (await call(editor, "contribute", attest=True, **OAK_AT))["result"]
    assert done["submitted"] is True and done["number"] == 1
    assert done["url"] == f"https://github.com/{HOUSE}/pull/1"
    assert gh.pulls == {} and list(gh.pulls_of[HOUSE]) == [1]
    branch = gh.pulls_of[HOUSE][1]["head"]["ref"]
    assert set(gh.files("elwin/house-catalog", branch)) == {
        "trees/items/oak/tree.json",
        "trees/items/oak/image.webp",
        "trees/items/oak/thumb.webp",
    }
    assert gh.files("elwin/house-catalog", branch)["trees/items/oak/tree.json"] == dump(
        OAK
    )
    assert ("POST", f"/repos/{HOUSE}/forks") in gh.calls
    assert not any(path.startswith(f"/repos/{UP}") for _, path in gh.calls)


async def test_a_batch_opens_one_pull_request_per_repository(editor, hass, gh):
    await sign_in(hass)
    await save_rinse(editor)
    await save(editor, OAK_AT, OAK)
    await save(editor, STOOL_AT, STOOL)
    pending = (await call(editor, "pending"))["result"]
    assert [(p["section"], p["id"]) for p in pending] == [
        ("equipment", "rinse"),
        ("trees", "oak"),
        ("objects", "stool"),
    ]
    entries = [STOOL_AT, RINSE, OAK_AT]
    done = (await call(editor, "contribute_batch", entries=entries, attest=True))[
        "result"
    ]
    assert done["submitted"] is True and done["count"] == 3 and done["skipped"] == []
    # the house entries travel together, apart from the reef ones
    assert done["pulls"] == [
        {
            "repo": HOUSE,
            "number": 1,
            "url": f"https://github.com/{HOUSE}/pull/1",
            "count": 2,
        },
        {"repo": UP, "number": 1, "url": f"https://github.com/{UP}/pull/1", "count": 1},
    ]
    assert (done["number"], done["url"]) == (1, f"https://github.com/{HOUSE}/pull/1")
    house = gh.pulls_of[HOUSE][1]
    assert set(gh.files("elwin/house-catalog", house["head"]["ref"])) == {
        "trees/items/oak/tree.json",
        "objects/items/stool/object.json",
    }
    body = house["request"]["body"]
    assert body.index("trees/items/oak") < body.index("objects/items/stool")
    assert set(gh.files("elwin/reeftech-catalog", gh.pulls[1]["head"]["ref"])) == {
        "equipment/tasks/rinse.json"
    }

    # the same number in two repositories is two pull requests
    gh.pulls_of[HOUSE][1]["state"] = "closed"
    listed = (await call(editor, "contributions"))["result"]
    assert sorted((i["section"], i["number"], i["state"]) for i in listed) == [
        ("equipment", 1, "open"),
        ("objects", 1, "closed"),
        ("trees", 1, "closed"),
    ]


async def test_a_batch_one_catalog_already_has(
    editor, hass, aioclient_mock, monkeypatch
):
    monkeypatch.setattr(github, "FORK_DELAY_S", 0)
    task = await save_rinse(editor)
    await save(editor, OAK_AT, OAK)
    both = [RINSE, OAK_AT]
    signed_out = await call(editor, "contribute_batch", entries=both, attest=True)
    assert signed_out["error"]["code"] == "auth_required"

    await sign_in(hass)
    fake = FakeGithub(aioclient_mock, files={"equipment/tasks/rinse.json": dump(task)})
    done = (await call(editor, "contribute_batch", entries=both, attest=True))["result"]
    # nothing to propose to the reef catalog: only the house one gets a pull request
    assert done["count"] == 1 and done["skipped"] == ["task/rinse"]
    assert [pull["repo"] for pull in done["pulls"]] == [HOUSE]
    assert fake.pulls == {} and list(fake.pulls_of[HOUSE]) == [1]

    # merged: both catalogs hold the entries as they are
    branch = fake.pulls_of[HOUSE][1]["head"]["ref"]
    fake.refs[(HOUSE, "main")] = fake.refs[("elwin/house-catalog", branch)]
    fake.pulls_of[HOUSE][1]["state"] = "closed"
    await call(editor, "contributions")
    again = await call(editor, "contribute_batch", entries=both, attest=True)
    assert again["error"]["code"] == "no_change"
    assert list(fake.pulls_of[HOUSE]) == [1]
