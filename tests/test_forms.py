"""Form models derived from the real schemas of the catalog."""

from __future__ import annotations

import json

import pytest
from conftest import KINDS, SCHEMAS

from custom_components.reeftech_catalog_editor import forms
from custom_components.reeftech_catalog_editor.const import SECTION_KINDS


def schemas_of(section: str) -> dict:
    return {
        name: json.loads((SCHEMAS / f"{name}.schema.json").read_text())
        for name in ("common", *KINDS[section])
    }


def fields(form: dict) -> dict:
    return {field["name"]: field for field in form["fields"]}


def form(kind: str) -> dict:
    section = next(s for s, kinds in SECTION_KINDS.items() if kind in kinds)
    return forms.build_form(kind, schemas_of(section))


def test_item_form():
    item = form("item")
    assert item["section"] == "equipment" and item["has_visual"] is True
    assert item["id_from"] == ["brand", "model"]
    assert item["visual_limits"] == {"image": 300_000, "thumb": 40_000}
    by_name = fields(item)
    assert by_name["category"] | {"type": "ref"} == by_name["category"]
    assert (
        by_name["category"]["ref"] == "categories" and by_name["category"]["required"]
    )
    assert by_name["brand"]["type"] == "string" and by_name["brand"]["maxLength"] == 64
    assert by_name["name"]["type"] == "i18n" and by_name["name"][
        "required_languages"
    ] == ["en"]
    assert by_name["name"]["languages"][0] == "en"
    assert by_name["scopes"]["type"] == "multi_enum"
    assert by_name["scopes"]["options"] == ["aquarium", "pool", "home"]
    assert by_name["icon"]["type"] == "icon"
    assert (
        by_name["power_w"]["type"] == "number"
        and by_name["power_w"]["exclusiveMinimum"] == 0
    )
    assert by_name["inherit_maintenance"]["type"] == "boolean"
    assert by_name["inherit_maintenance"]["default"] is True
    maintenance = by_name["maintenance"]
    assert maintenance["type"] == "list" and maintenance["uniqueItems"] is True
    sub = fields(maintenance["item"])
    assert sub["task"]["type"] == "ref" and sub["task"]["ref"] == "tasks"
    assert (
        sub["schedule"]["type"] == "schedule" and sub["regulatory"]["type"] == "boolean"
    )


def test_task_and_category_forms():
    task = form("task")
    assert task["has_visual"] is False and task["id_from"] == ["name.en"]
    assert fields(task)["schedule"]["required"] is True
    category = form("category")
    assert fields(category)["maintenance"]["item"]["fields"][0]["ref"] == "tasks"


def test_supplement_form():
    supplement = fields(form("supplement"))
    assert (
        supplement["kind"]["type"] == "enum"
        and "bundle" in supplement["kind"]["options"]
    )
    assert (
        supplement["sizes"]["type"] == "list"
        and supplement["sizes"]["item"]["type"] == "integer"
    )
    bundle = supplement["bundle"]["item"]["fields"]
    assert {f["name"]: f["type"] for f in bundle} == {
        "slot": "integer",
        "part": "ref",
        "ratio": "number",
    }
    assert bundle[1]["ref"] == "items"
    effects = {f["name"]: f for f in supplement["effects"]["item"]["fields"]}
    assert effects["unit"]["type"] == "enum" and "dkh" in effects["unit"]["options"]
    assert fields(form("supplement"))["concentration_g_l"]["type"] == "bounded_int"
    assert supplement["regulation"]["type"] == "multi_enum"


def test_parameter_form():
    parameter = fields(form("parameter"))
    assert parameter["range"]["type"] == "object"
    assert {f["name"] for f in parameter["range"]["fields"]} >= {
        "min",
        "low",
        "optimal",
        "high",
        "max",
    }
    assert parameter["sources"]["type"] == "multi_enum"
    assert parameter["decimals"]["maximum"] == 4


def test_unknown_shapes_fall_back_to_json():
    common = {"$defs": {}}
    schema = {
        "title": "x",
        "properties": {
            "odd": {"oneOf": [{"type": "string"}, {"type": "number"}]},
            "dangling": {"$ref": "other.schema.json"},
            "list": {"type": "array", "items": {"type": "string", "maxLength": 3}},
        },
    }
    form_ = forms.build_form("task", {"task": schema, "common": common})
    by_name = fields(form_)
    assert by_name["odd"]["type"] == "json" and by_name["dangling"]["type"] == "json"
    assert by_name["list"]["item"] == {"type": "string", "maxLength": 3}


@pytest.mark.parametrize(
    ("parts", "slug"),
    [
        (("Tunze", "Turbelle nanostream"), "tunze-turbelle-nanostream"),
        (("Évian", "Ça  va!"), "evian-ca-va"),
        (("", "  "), ""),
        (("x" * 80,), "x" * 64),
    ],
)
def test_slugify(parts, slug):
    assert forms.slugify(*parts) == slug


def test_value_at_and_suggest_id():
    assert forms.value_at({"name": {"en": "Heater"}}, "name.en") == "Heater"
    assert forms.value_at({"name": "x"}, "name.en") == ""
    assert forms.value_at({"a": 3}, "a") == ""
    data = {"brand": "Eheim", "model": "200"}
    assert forms.suggest_id("item", data, set()) == "eheim-200"
    assert forms.suggest_id("item", data, {"eheim-200", "eheim-200-2"}) == "eheim-200-3"
    assert forms.suggest_id("item", {}, set()) == ""
    long = {"brand": "x" * 64, "model": ""}
    assert forms.suggest_id("item", long, {"x" * 64}) == "x" * 62 + "-2"


def test_id_fields_and_lists_of_references(monkeypatch):
    common = {
        "$defs": {"id": {"type": "string", "pattern": "^[a-z]+$", "maxLength": 8}}
    }
    schema = {
        "properties": {
            "parent": {"$ref": "common.schema.json#/$defs/id"},
            "links": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["parent"],
    }
    monkeypatch.setitem(forms.REFS, "task", {"links[]": "tasks"})
    by_name = fields(forms.build_form("task", {"task": schema, "common": common}))
    assert by_name["parent"]["type"] == "id" and by_name["parent"]["required"] is True
    assert by_name["links"] == {
        "name": "links",
        "required": False,
        "type": "list",
        "item": {"type": "ref", "ref": "tasks"},
    }
