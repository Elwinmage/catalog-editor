"""GitHub: sign in (OAuth device flow) and propose an entry as a pull request.

No Home Assistant here, only an aiohttp session. The pull request is made the
usual way for a contribution: a fork of the catalog in the account of the user,
a branch, one commit holding the entry (descriptor and visuals), a pull request
against the default branch of the catalog. The branch is built from the head of
the catalog itself, so the fork never needs to be synchronised.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import aiohttp

from .catalog_pack import REPO

API = "https://api.github.com"
LOGIN_URL = "https://github.com/login"
SCOPE = "public_repo"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
TIMEOUT = aiohttp.ClientTimeout(total=30)
#: A fork is made in the background by GitHub: wait for it this long
FORK_POLLS = 15
FORK_DELAY_S = 2.0
MAX_FILE_BYTES = 1_000_000


class GithubError(Exception):
    """A request that cannot go on: a short code for the card and a message."""

    def __init__(self, code: str, message: str) -> None:
        """Keep the code next to the message."""
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DeviceCode:
    """What the user needs to authorise the editor on github.com."""

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class PullRequest:
    """A pull request of the user against the catalog."""

    number: int
    url: str
    branch: str
    state: str  # open, merged or closed


async def _post_form(
    session: aiohttp.ClientSession, url: str, fields: dict[str, str]
) -> dict[str, Any]:
    try:
        async with session.post(
            url, data=fields, headers={"Accept": "application/json"}, timeout=TIMEOUT
        ) as reply:
            body = await reply.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise GithubError("network", f"GitHub unreachable: {err}") from err
    if not isinstance(body, dict):
        raise GithubError("github_error", "Unexpected answer from GitHub")
    return body


async def start_login(session: aiohttp.ClientSession, client_id: str) -> DeviceCode:
    """Ask GitHub for a code the user types on github.com/login/device."""
    body = await _post_form(
        session,
        f"{LOGIN_URL}/device/code",
        {"client_id": client_id, "scope": SCOPE},
    )
    if "error" in body or "device_code" not in body:
        raise GithubError(
            "login_refused", str(body.get("error_description", "Login refused"))
        )
    return DeviceCode(
        body["device_code"],
        body["user_code"],
        body["verification_uri"],
        int(body.get("expires_in", 900)),
        int(body.get("interval", 5)),
    )


async def poll_login(
    session: aiohttp.ClientSession, client_id: str, device_code: str
) -> tuple[str, str | int]:
    """One check of the login: ('ok', token), ('pending', interval) or an end.

    The end is 'expired' or 'denied' (the user refused, or the code is wrong).
    """
    body = await _post_form(
        session,
        f"{LOGIN_URL}/oauth/access_token",
        {
            "client_id": client_id,
            "device_code": device_code,
            "grant_type": DEVICE_GRANT,
        },
    )
    if "access_token" in body:
        return "ok", body["access_token"]
    error = body.get("error")
    if error == "authorization_pending":
        return "pending", int(body.get("interval", 0))
    if error == "slow_down":
        return "pending", int(body.get("interval", 10))
    if error == "expired_token":
        return "expired", 0
    if error in ("access_denied", "incorrect_device_code", "unsupported_grant_type"):
        return "denied", 0
    raise GithubError("login_refused", str(body.get("error_description", error)))


class GithubClient:
    """The few calls of the GitHub REST API a contribution needs."""

    def __init__(
        self, session: aiohttp.ClientSession, token: str, upstream: str = REPO
    ) -> None:
        """Bind to a token and to the `owner/name` repository to contribute to."""
        self._session = session
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.upstream = upstream
        self.repo_name = upstream.split("/", 1)[1]

    async def _call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        missing_ok: bool = False,
    ) -> Any:
        """One request; None for a missing resource when `missing_ok`."""
        try:
            async with self._session.request(
                method,
                f"{API}{path}",
                json=body,
                headers=self._headers,
                timeout=TIMEOUT,
            ) as reply:
                status = reply.status
                try:
                    data = await reply.json(content_type=None)
                except ValueError:  # an HTML error page, say
                    data = None
        except (aiohttp.ClientError, TimeoutError) as err:
            raise GithubError("network", f"GitHub unreachable: {err}") from err
        if status == 404 and missing_ok:
            return None
        if status < 300 and data is not None:
            return data
        message = data.get("message", "") if isinstance(data, dict) else ""
        if status == 401:
            raise GithubError("auth_required", "GitHub login expired or revoked")
        if status in (403, 429):
            raise GithubError("rate_limited", message or "GitHub refused the request")
        if status == 404:
            raise GithubError("not_found", message or "Not found on GitHub")
        if status == 422:
            raise GithubError("rejected", message or "GitHub rejected the request")
        raise GithubError("github_error", f"GitHub answered {status}: {message}")

    async def login(self) -> str:
        """Account name behind the token."""
        return (await self._call("GET", "/user"))["login"]

    async def ensure_fork(self, login: str) -> str:
        """`login/name` of the fork of the catalog, made when it is missing."""
        fork = f"{login}/{self.repo_name}"
        found = await self._call("GET", f"/repos/{fork}", missing_ok=True)
        if found is None:
            await self._call("POST", f"/repos/{self.upstream}/forks", {})
            for _ in range(FORK_POLLS):
                await asyncio.sleep(FORK_DELAY_S)
                found = await self._call("GET", f"/repos/{fork}", missing_ok=True)
                if found is not None:
                    break
            else:
                raise GithubError("fork_pending", "The fork is not ready yet, retry")
        if not found.get("fork") or found["parent"]["full_name"] != self.upstream:
            raise GithubError(
                "fork_conflict", f"{fork} exists and is not a fork of {self.upstream}"
            )
        return fork

    async def default_branch(self) -> str:
        """Branch of the catalog a pull request is opened against."""
        return (await self._call("GET", f"/repos/{self.upstream}"))["default_branch"]

    async def folder(
        self, path: str, repo: str | None = None, ref: str | None = None
    ) -> list[str]:
        """Names of the files in a folder of a repository (empty when missing).

        Defaults to the catalog at its default branch.
        """
        query = f"?ref={quote(ref)}" if ref else ""
        listing = await self._call(
            "GET",
            f"/repos/{repo or self.upstream}/contents/{quote(path)}{query}",
            missing_ok=True,
        )
        if not isinstance(listing, list):
            return []
        return [item["name"] for item in listing if item.get("type") == "file"]

    async def head(
        self, repo: str, branch: str, missing_ok: bool = False
    ) -> str | None:
        """Commit a branch points to."""
        ref = await self._call(
            "GET",
            f"/repos/{repo}/git/ref/heads/{quote(branch)}",
            missing_ok=missing_ok,
        )
        return None if ref is None else ref["object"]["sha"]

    async def commit(
        self,
        fork: str,
        parent: str,
        files: dict[str, bytes | None],
        message: str,
    ) -> str:
        """A commit on top of `parent`, with these files (None deletes one).

        Raises `no_change` when the files are what the parent already has.
        """
        base = (await self._call("GET", f"/repos/{fork}/git/commits/{parent}"))["tree"][
            "sha"
        ]
        tree = []
        for path, blob in sorted(files.items()):
            if blob is None:
                sha = None
            else:
                if len(blob) > MAX_FILE_BYTES:
                    raise GithubError("too_big", f"{path} is too big")
                sha = (
                    await self._call(
                        "POST",
                        f"/repos/{fork}/git/blobs",
                        {
                            "content": base64.b64encode(blob).decode(),
                            "encoding": "base64",
                        },
                    )
                )["sha"]
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": sha})
        made = (
            await self._call(
                "POST", f"/repos/{fork}/git/trees", {"base_tree": base, "tree": tree}
            )
        )["sha"]
        if made == base:
            raise GithubError("no_change", "Nothing differs from the catalog")
        return (
            await self._call(
                "POST",
                f"/repos/{fork}/git/commits",
                {"message": message, "tree": made, "parents": [parent]},
            )
        )["sha"]

    async def create_branch(self, fork: str, branch: str, sha: str) -> None:
        """A new branch of the fork."""
        await self._call(
            "POST",
            f"/repos/{fork}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": sha},
        )

    async def move_branch(self, fork: str, branch: str, sha: str) -> None:
        """Add a commit to a branch of the fork (never rewriting it)."""
        await self._call(
            "PATCH",
            f"/repos/{fork}/git/refs/heads/{quote(branch)}",
            {"sha": sha, "force": False},
        )

    async def open_pull(
        self, login: str, branch: str, base: str, title: str, body: str
    ) -> PullRequest:
        """The pull request of a branch of the fork against the catalog."""
        made = await self._call(
            "POST",
            f"/repos/{self.upstream}/pulls",
            {
                "title": title,
                "body": body,
                "head": f"{login}:{branch}",
                "base": base,
                "maintainer_can_modify": True,
            },
        )
        return _pull(made)

    async def pull(self, number: int) -> PullRequest:
        """Current state of a pull request."""
        return _pull(await self._call("GET", f"/repos/{self.upstream}/pulls/{number}"))


def _pull(data: dict[str, Any]) -> PullRequest:
    state = "merged" if data.get("merged_at") else data["state"]
    return PullRequest(data["number"], data["html_url"], data["head"]["ref"], state)
