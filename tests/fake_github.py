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
API = re.compile(r"https://api\.github\.com/.*")


def _sha(*parts: Any) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True).encode()).hexdigest()


class FakeGithub:
    """The repositories of one upstream and, once forked, of one user."""

    def __init__(self, aioclient_mock, files: dict[str, bytes] | None = None) -> None:
        self.login = "elwin"
        self.valid = True  # False: every call answers 401
        self.status: int | None = None  # forced answer of every call
        self.forked = False
        self.can_push = False  # the account may push to the upstream itself
        self.fork_polls = 0  # GETs of the fork answering 404 once requested
        self.fork_kind = "fork"  # or "plain": a repository that is not a fork
        self.blobs: dict[str, bytes] = {}
        self.trees: dict[str, dict[str, str]] = {}
        self.commits: dict[str, tuple[str, str | None]] = {}
        self.refs: dict[tuple[str, str], str] = {}
        self.pulls: dict[int, dict[str, Any]] = {}
        self.calls: list[tuple[str, str]] = []
        tree = {path: self._blob(blob) for path, blob in (files or {}).items()}
        self.trees[_sha(tree)] = tree
        commit = _sha("root", tree)
        self.commits[commit] = (_sha(tree), None)
        self.refs[(UP, "main")] = commit
        for method in ("get", "post", "patch"):
            getattr(aioclient_mock, method)(API, side_effect=self.handle)

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
        fork = f"{self.login}/{UP.split('/')[1]}"
        known = repo == UP or (repo == fork and self.forked)
        if repo == fork and repo != UP and rest == "" and method == "GET":
            if self.forked and self.fork_polls <= 0:
                parent = {"full_name": UP} if self.fork_kind == "fork" else None
                body = {"fork": self.fork_kind == "fork", "parent": parent}
                return self.reply(method, url, body=body)
            self.fork_polls -= 1 if self.forked else 0
            return self.reply(method, url, 404, {"message": "Not Found"})
        if not known:
            return self.reply(method, url, 404, {"message": "Not Found"})
        if rest == "" and repo == UP:
            return self.reply(
                method,
                url,
                body={"default_branch": "main", "permissions": {"push": self.can_push}},
            )
        if rest == "/forks":
            self.forked = True
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
        if rest == "/pulls":
            number = len(self.pulls) + 1
            branch = data["head"].split(":", 1)[1]
            self.pulls[number] = {
                "number": number,
                "html_url": f"https://github.com/{UP}/pull/{number}",
                "state": "open",
                "merged_at": None,
                "head": {"ref": branch},
                "request": data,
            }
            return self.reply(method, url, 201, self.pulls[number])
        if rest.startswith("/pulls/"):
            return self.reply(method, url, body=self.pulls[int(rest.rsplit("/", 1)[1])])
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
