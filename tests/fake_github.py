"""A small stateful GitHub, enough for a fork, a branch, a commit and a pull request."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, cast

from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)

UP = "Elwinmage/reeftech-catalog"
HOUSE = "Elwinmage/house-catalog"
#: The catalog repositories; a pull request is a number in one of them
UPSTREAMS = (UP, HOUSE)
API = re.compile(r"https://api\.github\.com/.*")


def _sha(*parts: Any) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True).encode()).hexdigest()


class FakeGithub:
    """The catalog repositories and, once forked, the ones of one user.

    `forked`, `pulls` and `files` given at creation are about the reef catalog,
    which most tests use; `forks` and `pulls_of` hold the same per repository.
    """

    def __init__(self, aioclient_mock, files: dict[str, bytes] | None = None) -> None:
        self.login = "elwin"
        self.valid = True  # False: every call answers 401
        self.status: int | None = None  # forced answer of every call
        self.forks: set[str] = set()  # upstreams the user has forked
        self.can_push = False  # the account may push to the upstream itself
        self.fork_polls = 0  # GETs of the fork answering 404 once requested
        self.fork_kind = "fork"  # or "plain": a repository that is not a fork
        self.blobs: dict[str, bytes] = {}
        self.trees: dict[str, dict[str, str]] = {}
        self.commits: dict[str, tuple[str, str | None]] = {}
        self.refs: dict[tuple[str, str], str] = {}
        self.pulls_of: dict[str, dict[int, dict[str, Any]]] = {
            repo: {} for repo in UPSTREAMS
        }
        self.pulls = self.pulls_of[UP]
        self.calls: list[tuple[str, str]] = []
        tree = {path: self._blob(blob) for path, blob in (files or {}).items()}
        self.trees[_sha(tree)] = tree
        commit = _sha("root", tree)
        self.commits[commit] = (_sha(tree), None)
        self.refs[(UP, "main")] = commit
        empty: dict[str, str] = {}
        self.trees[_sha(empty)] = empty
        self.commits[_sha("root", empty)] = (_sha(empty), None)
        self.refs[(HOUSE, "main")] = _sha("root", empty)
        for method in ("get", "post", "patch"):
            getattr(aioclient_mock, method)(API, side_effect=self.handle)

    @property
    def forked(self) -> bool:
        """The user has a fork of the reef catalog."""
        return UP in self.forks

    @forked.setter
    def forked(self, value: bool) -> None:
        (self.forks.add if value else self.forks.discard)(UP)

    def _blob(self, blob: bytes) -> str:
        sha = _sha(base64.b64encode(blob).decode())
        self.blobs[sha] = blob
        return sha

    def files(self, repo: str, branch: str) -> dict[str, bytes]:
        """The files a branch holds."""
        tree, _ = self.commits[self.refs[(repo, branch)]]
        return {path: self.blobs[sha] for path, sha in self.trees[tree].items()}

    def reply(self, method, url, status=200, body=None):
        return AiohttpClientMockResponse(
            method, url, status=cast(Any, status), json=body
        )

    async def handle(self, method, url, data):
        path = url.path
        self.calls.append((method, path))
        query = dict(url.query)
        if self.status is not None:
            return self.reply(method, url, self.status, {"message": "forced"})
        if not self.valid:
            return self.reply(method, url, 401, {"message": "Bad credentials"})
        match = re.fullmatch(r"/repos/([^/]+/[^/]+)(/.*)?", path)
        if path == "/user":
            return self.reply(method, url, body={"login": self.login})
        if match is None:
            return self.reply(method, url, 404, {"message": "Not Found"})
        repo, rest = match.group(1), match.group(2) or ""
        # The upstream the repository is, or is the fork of
        up = next((u for u in UPSTREAMS if repo.split("/")[1] == u.split("/")[1]), UP)
        fork = f"{self.login}/{up.split('/')[1]}"
        forked = up in self.forks
        known = repo == up or (repo == fork and forked)
        if repo == fork and repo != up and rest == "" and method == "GET":
            if forked and self.fork_polls <= 0:
                parent = {"full_name": up} if self.fork_kind == "fork" else None
                body = {"fork": self.fork_kind == "fork", "parent": parent}
                return self.reply(method, url, body=body)
            self.fork_polls -= 1 if forked else 0
            return self.reply(method, url, 404, {"message": "Not Found"})
        if not known:
            return self.reply(method, url, 404, {"message": "Not Found"})
        if rest == "" and repo == up:
            return self.reply(
                method,
                url,
                body={"default_branch": "main", "permissions": {"push": self.can_push}},
            )
        if rest == "/forks":
            self.forks.add(up)
            return self.reply(method, url, 202, {})
        if rest.startswith("/contents/"):
            return self._contents(method, url, repo, rest[len("/contents/") :], query)
        if rest.startswith("/git/ref/heads/") or rest.startswith("/git/refs"):
            return self._ref(method, url, repo, rest, data)
        if rest.startswith("/git/commits/") and method == "GET":
            sha = rest.rsplit("/", 1)[1]
            return self.reply(method, url, body={"tree": {"sha": self.commits[sha][0]}})
        if rest == "/git/blobs":
            sha = self._blob(base64.b64decode(data["content"]))
            return self.reply(method, url, 201, {"sha": sha})
        if rest == "/git/trees":
            return self._tree(method, url, data)
        if rest == "/git/commits":
            sha = _sha("commit", data["tree"], data["parents"], data["message"])
            self.commits[sha] = (data["tree"], data["parents"][0])
            return self.reply(method, url, 201, {"sha": sha})
        pulls = self.pulls_of[up]
        if rest == "/pulls":
            number = len(pulls) + 1
            branch = data["head"].split(":", 1)[1]
            pulls[number] = {
                "number": number,
                "html_url": f"https://github.com/{up}/pull/{number}",
                "state": "open",
                "merged_at": None,
                "head": {"ref": branch},
                "request": data,
            }
            return self.reply(method, url, 201, pulls[number])
        if rest.startswith("/pulls/"):
            return self.reply(method, url, body=pulls[int(rest.rsplit("/", 1)[1])])
        return self.reply(
            method, url, 404, {"message": "Not Found"}
        )  # pragma: no cover

    def _contents(self, method, url, repo, folder, query):
        branch = query.get("ref", "main")
        if (repo, branch) not in self.refs:
            return self.reply(method, url, 404, {"message": "Not Found"})
        names = sorted(
            path.rsplit("/", 1)[1]
            for path in self.files(repo, branch)
            if path.rsplit("/", 1)[0] == folder
        )
        if not names:
            return self.reply(method, url, 404, {"message": "Not Found"})
        return self.reply(
            method, url, body=[{"name": n, "type": "file"} for n in names]
        )

    def _ref(self, method, url, repo, rest, data):
        if method == "GET":
            branch = rest[len("/git/ref/heads/") :]
            if (repo, branch) not in self.refs:
                return self.reply(method, url, 404, {"message": "Not Found"})
            return self.reply(
                method, url, body={"object": {"sha": self.refs[(repo, branch)]}}
            )
        if method == "POST":
            self.refs[(repo, data["ref"].removeprefix("refs/heads/"))] = data["sha"]
            return self.reply(method, url, 201, {})
        self.refs[(repo, rest.removeprefix("/git/refs/heads/"))] = data["sha"]
        return self.reply(method, url, body={})

    def _tree(self, method, url, data):
        tree = dict(self.trees[data["base_tree"]])
        for entry in data["tree"]:
            if entry["sha"] is None:
                if entry["path"] not in tree:
                    return self.reply(method, url, 422, {"message": "path not found"})
                del tree[entry["path"]]
            else:
                tree[entry["path"]] = entry["sha"]
        sha = _sha(tree)
        self.trees[sha] = tree
        return self.reply(method, url, 201, {"sha": sha})
