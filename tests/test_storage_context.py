"""The user layer on disk, and the view of the catalog the editor works from."""

from __future__ import annotations

import json

from conftest import FakeSource, equipment_view

from custom_components.reeftech_catalog_editor import context
from custom_components.reeftech_catalog_editor.storage import UserCatalog, dump


def test_user_catalog_entries(tmp_path):
    catalog = UserCatalog(lambda *parts: str(tmp_path.joinpath(*parts)))
    root = tmp_path / "reeftech_catalog/user/equipment"
    assert catalog.root("equipment") == root
    assert not catalog.has("equipment", "item", "mine")
    assert catalog.read_visuals("equipment", "item", "mine") == {}

    catalog.write("equipment", "item", "mine", {"brand": "Me"}, {"image.webp": b"IMG"})
    assert json.loads((root / "items/mine/item.json").read_text()) == {"brand": "Me"}
    assert catalog.has("equipment", "item", "mine")
    assert catalog.read_visuals("equipment", "item", "mine") == {"image.webp": b"IMG"}

    # Replaced in one move, nothing left behind (dot folders are ignored by readers)
    catalog.write("equipment", "item", "mine", {"brand": "Me2"}, {"thumb.webp": b"T"})
    assert catalog.read_visuals("equipment", "item", "mine") == {"thumb.webp": b"T"}
    assert sorted(p.name for p in (root / "items").iterdir()) == ["mine"]

    catalog.write("equipment", "task", "clean", {"name": {"en": "Clean"}})
    assert catalog.has("equipment", "task", "clean")
    assert catalog.read_visuals("equipment", "task", "clean") == {}
    assert sorted(p.name for p in (root / "tasks").iterdir()) == ["clean.json"]

    assert catalog.delete("equipment", "item", "mine") is True
    assert catalog.delete("equipment", "task", "clean") is True
    assert catalog.delete("equipment", "item", "mine") is False
    assert dump({"é": 1}) == '{\n  "é": 1\n}\n'.encode()


def test_strip_entry_and_context(tmp_path):
    view = equipment_view(tmp_path / "pack")
    item = view["items"]["eheim-200"]
    assert context.strip_entry("item", item, view) == {
        "category": "heater",
        "brand": "Eheim",
        "model": "200",
    }
    explicit = {**item, "scopes": ["aquarium", "home"]}
    assert context.strip_entry("item", explicit, view)["scopes"] == ["aquarium", "home"]
    assert context.strip_entry("task", {"name": 1, "source": "x"}, view) == {"name": 1}

    ctx = context.build_context(view, "equipment")
    assert set(ctx.tasks) == {"clean"} and set(ctx.categories) == {"heater"}
    assert "source" not in ctx.categories["heater"]
    assert context.build_context(view, "equipment", ("task", "clean")).tasks == {}
    items = {"items": {"a": {"symbol": "A", "image": "x"}}}
    assert context.build_context(items, "parameters").parameters == {
        "a": {"symbol": "A"}
    }
    assert (
        context.build_context(items, "supplements", ("supplement", "a")).supplements
        == {}
    )


def test_water_test_context_and_label():
    view = {"items": {"a": {"brand": "B", "name": "K", "image": "x"}}}
    parameters = {"kh": {"unit": "dkh"}}
    ctx = context.build_context(view, "water_tests", ("water_test", "z"), parameters)
    assert ctx.water_tests == {"a": {"brand": "B", "name": "K"}}
    assert ctx.parameters == parameters
    assert (
        context.build_context(view, "water_tests", ("water_test", "a")).water_tests
        == {}
    )
    assert context.entry_label("water_test", "a", {"brand": "B", "name": "K"}) == "B K"
    assert context.entry_label("water_test", "a", {}) == "a"


def test_labels_and_lists(tmp_path):
    view = equipment_view(tmp_path / "pack")
    assert context.entry_label("supplement", "x", {"fullname": "B - KH"}) == "B - KH"
    assert context.entry_label("supplement", "x", {}) == "x"
    assert (
        context.entry_label("category", "heater", {"name": {"en": "Heater"}})
        == "Heater"
    )
    assert (
        context.entry_label("item", "e", {"brand": "Eheim", "model": "200"})
        == "Eheim 200"
    )
    assert context.entry_label("item", "e", {}) == "e"
    assert context.entry_label("task", "t", {"name": "bad"}) == "t"
    assert [e["id"] for e in context.list_entries(view, "item")] == ["eheim-200"]
    listed = context.list_entries(view, "item")[0]
    assert (listed["brand"], listed["category"]) == ("Eheim", "heater")
    assert context.list_entries(view, "item")[0]["label"] == "Eheim 200"
    assert context.list_entries({}, "item") == []


def test_locate_visual(tmp_path):
    pack = tmp_path / "pack"
    view = equipment_view(pack)
    updater = FakeSource("fake", "equipment", pack, view)
    item = view["items"]["eheim-200"]
    assert (
        context.locate_visual(updater, item, "image")
        == (pack / "items/eheim-200/image.png").resolve()
    )
    thumb = context.locate_visual(updater, item, "thumb")
    assert thumb is not None and thumb.name == "thumb.webp"
    assert context.locate_visual(updater, {"image": None}, "image") is None
    for url in (
        "/other/pack/x.png",  # not a served layer
        "/fake_catalog/pack/items/nope/image.png",  # no such file
        "/fake_catalog/pack/../../etc/passwd",  # leaves the layer
    ):
        assert context.locate_visual(updater, {"image": url}, "image") is None
