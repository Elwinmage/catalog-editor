"""Sign in and the calls of a contribution, against a fake GitHub."""

from __future__ import annotations

from typing import Any, cast

import aiohttp
import pytest
from fake_github import UP, FakeGithub
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from yarl import URL

from custom_components.reeftech_catalog_editor import github
from custom_components.reeftech_catalog_editor.github import GithubClient, GithubError

LOGIN = "https://github.com/login"


@pytest.fixture(autouse=True)
def fast_fork(monkeypatch):
    monkeypatch.setattr(github, "FORK_DELAY_S", 0)


async def test_device_flow(hass, aioclient_mock):
    session = async_get_clientsession(hass)
    aioclient_mock.post(
        f"{LOGIN}/device/code",
        json={
            "device_code": "dev",
            "user_code": "ABCD-1234",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        },
    )
    code = await github.start_login(session, "cid")
    assert (code.user_code, code.interval, code.device_code) == ("ABCD-1234", 5, "dev")
    assert aioclient_mock.mock_calls[0][2] == {
        "client_id": "cid",
        "scope": "public_repo",
    }

    answers = iter(
        [
            {"error": "authorization_pending"},
            {"error": "slow_down", "interval": 10},
            {"error": "expired_token"},
            {"error": "access_denied"},
            {"access_token": "tok"},
        ]
    )

    async def answer(*args):
        return _json(next(answers))

    aioclient_mock.post(f"{LOGIN}/oauth/access_token", side_effect=answer)
    assert await github.poll_login(session, "cid", "dev") == ("pending", 0)
    assert await github.poll_login(session, "cid", "dev") == ("pending", 10)
    assert await github.poll_login(session, "cid", "dev") == ("expired", 0)
    assert await github.poll_login(session, "cid", "dev") == ("denied", 0)
    assert await github.poll_login(session, "cid", "dev") == ("ok", "tok")


def _json(body, status=200):
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMockResponse,
    )

    return AiohttpClientMockResponse(
        "POST", URL("https://x"), status=cast(Any, status), json=body
    )


async def test_device_flow_failures(hass, aioclient_mock):
    session = async_get_clientsession(hass)
    aioclient_mock.post(
        f"{LOGIN}/device/code",
        json={
            "error": "unauthorized_client",
            "error_description": "Device flow disabled",
        },
    )
    with pytest.raises(GithubError, match="Device flow disabled") as refused:
        await github.start_login(session, "cid")
    assert refused.value.code == "login_refused"
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{LOGIN}/device/code", json=["not", "an", "object"])
    with pytest.raises(GithubError) as odd:
        await github.start_login(session, "cid")
    assert odd.value.code == "github_error"
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{LOGIN}/oauth/access_token", exc=aiohttp.ClientError("down"))
    with pytest.raises(GithubError) as down:
        await github.poll_login(session, "cid", "dev")
    assert down.value.code == "network"
    aioclient_mock.clear_requests()
    aioclient_mock.post(
        f"{LOGIN}/oauth/access_token",
        json={"error": "device_flow_disabled", "error_description": "Disabled"},
    )
    with pytest.raises(GithubError, match="Disabled"):
        await github.poll_login(session, "cid", "dev")
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{LOGIN}/oauth/access_token", json={"error": "weird"})
    with pytest.raises(GithubError, match="weird"):
        await github.poll_login(session, "cid", "dev")


async def test_errors_are_coded(hass, aioclient_mock):
    fake = FakeGithub(aioclient_mock)
    client = GithubClient(async_get_clientsession(hass), "tok")
    assert await client.login() == "elwin"
    for status, code in (
        (401, "auth_required"),
        (403, "rate_limited"),
        (429, "rate_limited"),
        (404, "not_found"),
        (422, "rejected"),
        (500, "github_error"),
    ):
        fake.status = status
        with pytest.raises(GithubError) as err:
            await client.login()
        assert err.value.code == code
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{github.API}/user", exc=aiohttp.ClientError("down"))
    with pytest.raises(GithubError) as down:
        await client.login()
    assert down.value.code == "network"
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{github.API}/user", status=500, text="plain text")
    with pytest.raises(GithubError, match="500"):
        await client.login()


async def test_fork(hass, aioclient_mock):
    fake = FakeGithub(aioclient_mock)
    client = GithubClient(async_get_clientsession(hass), "tok")
    fake.fork_polls = 2
    assert await client.ensure_fork("elwin") == "elwin/reeftech-catalog"
    assert ("POST", f"/repos/{UP}/forks") in fake.calls
    forks = fake.calls.count(("POST", f"/repos/{UP}/forks"))
    assert await client.ensure_fork("elwin") == "elwin/reeftech-catalog"  # found
    assert fake.calls.count(("POST", f"/repos/{UP}/forks")) == forks

    fake.fork_kind = "plain"
    with pytest.raises(GithubError) as conflict:
        await client.ensure_fork("elwin")
    assert conflict.value.code == "fork_conflict"


async def test_fork_never_ready(hass, aioclient_mock, monkeypatch):
    fake = FakeGithub(aioclient_mock)
    fake.fork_polls = 10_000
    monkeypatch.setattr(github, "FORK_POLLS", 2)
    client = GithubClient(async_get_clientsession(hass), "tok")
    with pytest.raises(GithubError) as pending:
        await client.ensure_fork("elwin")
    assert pending.value.code == "fork_pending"


async def test_reads(hass, aioclient_mock):
    fake = FakeGithub(
        aioclient_mock, {"a/x.json": b"1", "a/y.json": b"2", "b/z.json": b"3"}
    )
    client = GithubClient(async_get_clientsession(hass), "tok")
    assert await client.default_branch() == "main"
    assert await client.folder("a") == ["x.json", "y.json"]
    assert await client.folder("nope") == []
    assert await client.folder("a", UP, "main") == ["x.json", "y.json"]
    assert await client.head(UP, "main") == fake.refs[(UP, "main")]
    assert await client.head(UP, "other", missing_ok=True) is None
    with pytest.raises(GithubError):
        await client.head(UP, "other")
    # A file is not a folder
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{github.API}/repos/{UP}/contents/a/x.json", json={"type": "file"}
    )
    assert await client.folder("a/x.json") == []


async def test_commit_and_pull(hass, aioclient_mock):
    fake = FakeGithub(aioclient_mock, {"a/x.json": b"1", "a/y.json": b"2"})
    client = GithubClient(async_get_clientsession(hass), "tok")
    fake.forked = True
    parent = fake.refs[(UP, "main")]
    with pytest.raises(GithubError) as same:
        await client.commit("elwin/reeftech-catalog", parent, {"a/x.json": b"1"}, "m")
    assert same.value.code == "no_change"
    sha = await client.commit(
        "elwin/reeftech-catalog",
        parent,
        {"a/x.json": b"9", "a/y.json": None, "a/n.json": b"4"},
        "msg",
    )
    await client.create_branch("elwin/reeftech-catalog", "editor/x-1", sha)
    assert fake.files("elwin/reeftech-catalog", "editor/x-1") == {
        "a/x.json": b"9",
        "a/n.json": b"4",
    }
    more = await client.commit(
        "elwin/reeftech-catalog", sha, {"a/n.json": b"5"}, "again"
    )
    await client.move_branch("elwin/reeftech-catalog", "editor/x-1", more)
    assert fake.files("elwin/reeftech-catalog", "editor/x-1")["a/n.json"] == b"5"

    pull = await client.open_pull("elwin", "editor/x-1", "main", "T", "B")
    assert (pull.number, pull.branch, pull.state) == (1, "editor/x-1", "open")
    assert fake.pulls[1]["request"]["head"] == "elwin:editor/x-1"
    fake.pulls[1]["state"] = "closed"
    assert (await client.pull(1)).state == "closed"
    fake.pulls[1]["merged_at"] = "2026-11-16T10:00:00Z"
    assert (await client.pull(1)).state == "merged"

    with pytest.raises(GithubError) as big:
        await client.commit(
            "elwin/reeftech-catalog", parent, {"a/big.webp": b"x" * 1_000_001}, "m"
        )
    assert big.value.code == "too_big"
    with pytest.raises(GithubError) as bad:
        await client.commit(
            "elwin/reeftech-catalog", parent, {"a/none.json": None}, "m"
        )
    assert bad.value.code == "rejected"
