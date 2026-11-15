"""Turn an entry of the user into a pull request against the catalog."""

from __future__ import annotations

import time
from typing import Any

from .catalog_rules import ASSET_FILES, DESCRIPTORS, FOLDERS
from .github import GithubClient, PullRequest
from .storage import dump

LICENCE = (
    "- [x] I certify that any picture in this pull request is my own work "
    "(or I hold the rights to it) and I agree to publish it under "
    "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)."
)


def entry_folder(kind: str, entry_id: str) -> str:
    """Folder holding the files of an entry in the repository."""
    return FOLDERS[kind] if kind == "task" else f"{FOLDERS[kind]}/{entry_id}"


def repo_files(
    kind: str, entry_id: str, data: dict[str, Any], visuals: dict[str, bytes]
) -> dict[str, bytes | None]:
    """The files of an entry, by path in the repository."""
    if kind == "task":
        return {f"{FOLDERS[kind]}/{entry_id}.json": dump(data)}
    folder = entry_folder(kind, entry_id)
    files: dict[str, bytes | None] = {f"{folder}/{DESCRIPTORS[kind]}": dump(data)}
    files.update({f"{folder}/{name}": blob for name, blob in visuals.items()})
    return files


def stale_files(
    kind: str, entry_id: str, present: list[str], visuals: dict[str, bytes]
) -> dict[str, None]:
    """Visuals of the repository the entry no longer has (to delete)."""
    if kind == "task":
        return {}
    folder = entry_folder(kind, entry_id)
    return {
        f"{folder}/{name}": None
        for name in present
        if name in ASSET_FILES and name not in visuals
    }


def branch_name(kind: str, entry_id: str, now: float) -> str:
    """A branch name no earlier contribution can have."""
    return f"editor/{kind}-{entry_id}-{int(now)}"[:120]


def texts(
    kind: str, entry_id: str, label: str, update: bool, pictured: bool
) -> tuple[str, str]:
    """Title and description of the pull request."""
    verb = "Update" if update else "Add"
    title = f"{verb} {kind} {entry_id}"
    lines = [
        f"{verb} **{label}** (`{entry_to_path(kind, entry_id)}`).",
        "",
        "Made with the ReefTech catalog editor; the entry was checked with the "
        "same rules as the catalog CI.",
    ]
    if pictured:
        lines += ["", "This pull request contains a picture:"]
    lines += ["", LICENCE]
    return title, "\n".join(lines)


def entry_to_path(kind: str, entry_id: str) -> str:
    """Path shown in the description."""
    if kind == "task":
        return f"{FOLDERS[kind]}/{entry_id}.json"
    return entry_folder(kind, entry_id) + "/"


async def contribute(
    client: GithubClient,
    login: str,
    *,
    previous: dict[str, Any] | None,
    kind: str,
    entry_id: str,
    label: str,
    data: dict[str, Any],
    visuals: dict[str, bytes],
) -> tuple[PullRequest, bool, bool]:
    """Push an entry; returns the pull request, whether it is an update of the
    catalog and whether it only added a commit to an open pull request."""
    fork = await client.ensure_fork(login)
    pull: PullRequest | None = None
    branch = parent = None
    if previous is not None:
        pull = await client.pull(previous["number"])
        branch = pull.branch if pull.state == "open" else None
        parent = await client.head(fork, branch, missing_ok=True) if branch else None
    base = ""
    if parent is None:
        base = await client.default_branch()
        parent = await client.head(client.upstream, base)
        branch = branch_name(kind, entry_id, time.time())
        pull = None
        where = (client.upstream, base)
    else:
        where = (fork, branch)
    present = await client.folder(entry_folder(kind, entry_id), *where)
    if pull is not None and previous is not None:
        update = bool(previous["update"])
    elif kind == "task":
        update = f"{entry_id}.json" in present
    else:
        update = DESCRIPTORS[kind] in present
    files = repo_files(kind, entry_id, data, visuals)
    files.update(stale_files(kind, entry_id, present, visuals))
    verb = "Update" if update else "Add"
    commit = await client.commit(fork, str(parent), files, f"{verb} {kind} {entry_id}")
    assert branch is not None
    if pull is not None:
        await client.move_branch(fork, branch, commit)
        return pull, update, True
    await client.create_branch(fork, branch, commit)
    title, body = texts(kind, entry_id, label, update, bool(visuals))
    return await client.open_pull(login, branch, base, title, body), update, False
