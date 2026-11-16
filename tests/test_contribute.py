"""From an entry of the user to a pull request, and what follows."""

from __future__ import annotations

import json

import pytest
from fake_github import FakeGithub
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.reeftech_catalog_editor import contribute as contribution
from custom_components.reeftech_catalog_editor import github
from custom_components.reeftech_catalog_editor.contributions import (
    MAX_ITEMS,
    Contributions,
)
from custom_components.reeftech_catalog_editor.github import GithubClient, GithubError
from custom_components.reeftech_catalog_editor.storage import dump

ITEM = {"category": "heater", "brand": "Acme", "model": "X1"}
FORK = "elwin/reeftech-catalog"
UP = "Elwinmage/reeftech-catalog"


@pytest.fixture(autouse=True)
def fast_fork(monkeypatch):
    monkeypatch.setattr(github, "FORK_DELAY_S", 0)


def client_of(hass) -> GithubClient:
    return GithubClient(async_get_clientsession(hass), "tok")


def test_pure_helpers():
    assert contribution.entry_folder("task", "t") == "equipment/tasks"
    assert contribution.entry_folder("item", "a") == "equipment/items/a"
    assert contribution.repo_files("task", "t", {"a": 1}, {}) == {
        "equipment/tasks/t.json": dump({"a": 1})
    }
    files = contribution.repo_files("item", "a", ITEM, {"image.webp": b"I"})
    assert files == {
        "equipment/items/a/item.json": dump(ITEM),
        "equipment/items/a/image.webp": b"I",
    }
    assert contribution.stale_files("task", "t", ["t.json"], {}) == {}
    assert contribution.stale_files(
        "item",
        "a",
        ["item.json", "image.png", "thumb.webp", "notes.txt"],
        {"thumb.webp": b""},
    ) == {"equipment/items/a/image.png": None}
    assert contribution.branch_name("item", "a" * 200, 1.9).startswith(
        "editor/item-aaa"
    )
    assert len(contribution.branch_name("item", "a" * 200, 1.9)) == 120
    title, body = contribution.texts("item", "a", "Acme", False, True)
    assert (
        title == "Add item a" and "CC BY 4.0" in body and "contains a picture" in body
    )
    title, body = contribution.texts("task", "t", "Rinse", True, False)
    assert title == "Update task t" and "equipment/tasks/t.json" in body
    assert "picture" not in body.replace("any picture", "")


async def test_new_entry_makes_a_fork_a_branch_and_a_pull(hass, aioclient_mock):
    fake = FakeGithub(aioclient_mock, {"equipment/items/other/item.json": b"{}"})
    fake.fork_polls = 1
    pull, update, appended = await contribution.contribute(
        client_of(hass),
        "elwin",
        previous=None,
        kind="item",
        entry_id="acme-x1",
        label="Acme X1",
        data=ITEM,
        visuals={"image.webp": b"IMG", "thumb.webp": b"THUMB"},
    )
    assert (update, appended, pull.state) == (False, False, "open")
    files = fake.files(FORK, pull.branch)
    assert files["equipment/items/acme-x1/item.json"] == dump(ITEM)
    assert files["equipment/items/acme-x1/image.webp"] == b"IMG"
    assert files["equipment/items/other/item.json"] == b"{}"  # based on the catalog
    request = fake.pulls[pull.number]["request"]
    assert request["title"] == "Add item acme-x1" and request["base"] == "main"
    assert request["head"] == f"elwin:{pull.branch}" and "CC BY 4.0" in request["body"]
    assert pull.branch.startswith("editor/item-acme-x1-")


async def test_an_account_that_can_push_uses_the_catalog_itself(hass, aioclient_mock):
    fake = FakeGithub(aioclient_mock)
    fake.can_push = True
    fake.login = owner = "elwinmage"
    pull, _, appended = await contribution.contribute(
        client_of(hass),
        owner,
        previous=None,
        kind="item",
        entry_id="acme-x1",
        label="Acme X1",
        data=ITEM,
        visuals={},
    )
    assert appended is False
    assert ("POST", f"/repos/{UP}/forks") not in fake.calls
    assert fake.files(UP, pull.branch)["equipment/items/acme-x1/item.json"] == dump(
        ITEM
    )
    assert fake.refs[(UP, "main")] != fake.refs[(UP, pull.branch)]  # main is untouched
    assert fake.pulls[pull.number]["request"]["head"] == f"{owner}:{pull.branch}"
    # A second save adds a commit to the same branch of the catalog
    again = await contribution.contribute(
        client_of(hass),
        owner,
        previous={"number": pull.number, "update": False},
        kind="item",
        entry_id="acme-x1",
        label="Acme X1",
        data={**ITEM, "model": "X2"},
        visuals={},
    )
    assert again[2] is True


async def test_update_replaces_the_visual_and_deletes_the_old_one(hass, aioclient_mock):
    fake = FakeGithub(
        aioclient_mock,
        {
            "equipment/items/acme-x1/item.json": b"{}",
            "equipment/items/acme-x1/image.png": b"OLD",
            "equipment/items/acme-x1/thumb.webp": b"T",
        },
    )
    fake.forked = True
    pull, update, _ = await contribution.contribute(
        client_of(hass),
        "elwin",
        previous=None,
        kind="item",
        entry_id="acme-x1",
        label="Acme X1",
        data=ITEM,
        visuals={"image.webp": b"NEW", "thumb.webp": b"T"},
    )
    assert update is True
    files = fake.files(FORK, pull.branch)
    assert "equipment/items/acme-x1/image.png" not in files
    assert files["equipment/items/acme-x1/image.webp"] == b"NEW"
    assert fake.pulls[pull.number]["request"]["title"] == "Update item acme-x1"


async def test_task_has_no_folder(hass, aioclient_mock):
    fake = FakeGithub(aioclient_mock, {"equipment/tasks/clean.json": b"{}"})
    fake.forked = True
    pull, update, _ = await contribution.contribute(
        client_of(hass),
        "elwin",
        previous=None,
        kind="task",
        entry_id="clean",
        label="Clean",
        data={"name": {"en": "Clean"}},
        visuals={},
    )
    assert update is True
    assert fake.files(FORK, pull.branch)["equipment/tasks/clean.json"] != b"{}"
    _other, update, _ = await contribution.contribute(
        client_of(hass),
        "elwin",
        previous=None,
        kind="task",
        entry_id="new-task",
        label="New",
        data={"name": {"en": "New"}},
        visuals={},
    )
    assert update is False


async def test_nothing_to_propose(hass, aioclient_mock):
    fake = FakeGithub(aioclient_mock, {"equipment/items/a/item.json": dump(ITEM)})
    fake.forked = True
    with pytest.raises(GithubError) as same:
        await contribution.contribute(
            client_of(hass),
            "elwin",
            previous=None,
            kind="item",
            entry_id="a",
            label="A",
            data=ITEM,
            visuals={},
        )
    assert same.value.code == "no_change"
    assert fake.pulls == {}


async def test_a_second_save_adds_a_commit_to_the_open_pull(hass, aioclient_mock):
    fake = FakeGithub(aioclient_mock)
    fake.forked = True
    client = client_of(hass)
    kwargs = {"kind": "item", "entry_id": "a", "label": "A", "visuals": {}}
    pull, update, _ = await contribution.contribute(
        client, "elwin", previous=None, data=ITEM, **kwargs
    )
    previous = {"number": pull.number, "update": update}
    again, _, appended = await contribution.contribute(
        client, "elwin", previous=previous, data={**ITEM, "model": "X2"}, **kwargs
    )
    assert appended is True and again.number == pull.number and len(fake.pulls) == 1
    committed = json.loads(fake.files(FORK, pull.branch)["equipment/items/a/item.json"])
    assert committed["model"] == "X2"

    # The branch was deleted meanwhile: a fresh branch and pull request
    del fake.refs[(FORK, pull.branch)]
    fresh, _, appended = await contribution.contribute(
        client, "elwin", previous=previous, data=ITEM, **kwargs
    )
    assert appended is False and fresh.number == 2

    # The pull request was merged: same
    fake.pulls[2]["merged_at"] = "2026-11-16T10:00:00Z"
    last, _, appended = await contribution.contribute(
        client,
        "elwin",
        previous={"number": 2, "update": False},
        data={**ITEM, "model": "X3"},
        **kwargs,
    )
    assert appended is False and last.number == 3


async def test_contributions_store(hass):
    store = Contributions(hass)
    await store.async_load()
    assert store.token is None and store.items == []
    await store.async_sign_in("tok", "elwin")
    item = {
        "section": "equipment",
        "kind": "item",
        "id": "a",
        "number": 1,
        "state": "open",
    }
    await store.async_record(item)
    await store.async_record({**item, "state": "merged"})
    assert len(store.items) == 1 and store.find("equipment", "item", "a") is None
    await store.async_record({**item, "number": 2})
    found = store.find("equipment", "item", "a")
    assert found is not None and found["number"] == 2
    assert store.find("equipment", "item", "b") is None
    assert store.find("supplements", "item", "a") is None
    store.items[0]["state"] = "closed"
    await store.async_save()

    again = Contributions(hass)
    await again.async_load()
    assert (again.token, again.login) == ("tok", "elwin")
    assert [i["number"] for i in again.items] == [2, 1]
    await again.async_sign_out()
    assert again.token is None and again.login is None and len(again.items) == 2

    for number in range(10, 10 + MAX_ITEMS + 5):
        await again.async_record({**item, "number": number, "state": "closed"})
    assert (
        len(again.items) == MAX_ITEMS and again.items[0]["number"] == 10 + MAX_ITEMS + 4
    )
