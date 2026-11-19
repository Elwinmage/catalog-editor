"""Turn an entry of the user into a pull request against the catalog."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .catalogs import EXTERNAL_KINDS
from .github import GithubClient, GithubError, PullRequest
from .rules import ASSET_FILES, DESCRIPTORS, FOLDERS
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
        "Made with the Catalog editor; the entry was checked with the "
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


# -- several entries in one pull request ----------------------------------------------


@dataclass(frozen=True)
class BatchEntry:
    """An entry of the user to propose with others."""

    section: str
    kind: str
    entry_id: str
    label: str
    data: dict[str, Any]
    visuals: dict[str, bytes]


#: What an entry may refer to comes first: a pull request is reviewed (and its
#: commits read) from the tasks to the items using them
KIND_ORDER = (
    "task",
    "category",
    "parameter",
    "supplement",
    "item",
    "water_test",
    # the declared catalogs (catalogs.py), whose entries refer to nothing
    *EXTERNAL_KINDS,
)


def batch_order(entries: list[BatchEntry]) -> list[BatchEntry]:
    """Dependency order: tasks, categories, parameters, supplements, items, tests."""
    return sorted(
        entries, key=lambda e: (KIND_ORDER.index(e.kind), e.section, e.entry_id)
    )


def batch_texts(done: list[tuple[BatchEntry, bool]]) -> tuple[str, str]:
    """Title and description of a pull request holding several entries."""
    title = (
        f"Add {len(done)} entries"
        if len(done) > 1
        else texts(
            done[0][0].kind, done[0][0].entry_id, done[0][0].label, done[0][1], False
        )[0]
    )
    lines = [
        f"{len(done)} entries, one commit each, in dependency order:",
        "",
    ]
    for entry, update in done:
        verb = "Update" if update else "Add"
        lines.append(
            f"- {verb} **{entry.label}** "
            f"(`{entry_to_path(entry.kind, entry.entry_id)}`)"
        )
    lines += [
        "",
        "Made with the Catalog editor; every entry was checked with the same "
        "rules as the catalog CI.",
    ]
    if any(entry.visuals for entry, _ in done):
        lines += ["", "Some of these entries contain a picture:"]
    lines += ["", LICENCE]
    return title, "\n".join(lines)


async def contribute_batch(
    client: GithubClient, login: str, entries: list[BatchEntry]
) -> tuple[PullRequest, list[tuple[BatchEntry, bool]], list[BatchEntry]]:
    """One pull request, one commit per entry; returns it, the entries proposed (with
    whether each updates the catalog) and the ones the catalog already has as is."""
    fork = await client.ensure_fork(login)
    base = await client.default_branch()
    parent = str(await client.head(client.upstream, base))
    done: list[tuple[BatchEntry, bool]] = []
    skipped: list[BatchEntry] = []
    for entry in batch_order(entries):
        folder = entry_folder(entry.kind, entry.entry_id)
        present = await client.folder(folder, client.upstream, base)
        if entry.kind == "task":
            update = f"{entry.entry_id}.json" in present
        else:
            update = DESCRIPTORS[entry.kind] in present
        files = repo_files(entry.kind, entry.entry_id, entry.data, entry.visuals)
        files.update(stale_files(entry.kind, entry.entry_id, present, entry.visuals))
        verb = "Update" if update else "Add"
        try:
            parent = await client.commit(
                fork, parent, files, f"{verb} {entry.kind} {entry.entry_id}"
            )
        except GithubError as err:
            if err.code != "no_change":
                raise
            skipped.append(entry)
            continue
        done.append((entry, update))
    if not done:
        raise GithubError("no_change", "Nothing differs from the catalog")
    branch = f"editor/batch-{int(time.time())}"
    await client.create_branch(fork, branch, parent)
    title, body = batch_texts(done)
    return await client.open_pull(login, branch, base, title, body), done, skipped
