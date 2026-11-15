# ReefTech catalog editor

A Home Assistant integration to add and edit entries of the
[ReefTech catalog](https://github.com/Elwinmage/reeftech-catalog) (equipment,
supplements, parameters) from the UI, with the picture upload included.

An entry you save is written in the **user layer shared by every integration
reading the catalog** (`<config>/reeftech_catalog/user/<section>/`): it is
usable at once, without waiting for a release. Contributing it to the catalog
itself (a pull request) comes on top of that.

## Install

1. Install the integration (HACS custom repository, or copy
   `custom_components/reeftech_catalog_editor`) and add it in *Settings →
   Devices & services*.
2. It asks for the **client ID of a GitHub OAuth App** (see below). It is public
   (no secret is needed with the device flow).
3. Add the card to a dashboard: `type: custom:reeftech-catalog-editor-card`. The
   integration serves it and loads it by itself, nothing to add to the
   resources, and there is no build step.

The editor needs at least one integration reading each catalog it edits:
`maintenance_hub` or `reef_maintenance` (equipment), `redsea` (supplements),
`reeftank` or `redsea` (parameters). Their copies of the catalog client must be
up to date (see `scripts/sync_client.py` in reeftech-catalog).

### The GitHub OAuth App

*GitHub → Settings → Developer settings → OAuth Apps → New OAuth App*, tick
**Enable Device Flow**; the callback URL is not used (put any URL). The editor
asks for the `public_repo` scope only: it forks the catalog, pushes a branch of
the fork and opens the pull request. The token stays in Home Assistant's storage
(`.storage/reeftech_catalog_editor`).

## How it works

- The **form** of each kind of entry is generated from the JSON Schemas
  published by the catalog releases (`schema.zip`), so a new field of the
  catalog shows up here without a new version of the editor or of the card.
- A draft is checked with the **same rules as the catalog CI**
  (`catalog_rules.py`): what the editor accepts is what the CI accepts.
- Pictures are normalised (transparent WebP, 512 px and 128 px, size limits).
- The editor does not read the catalog by itself: it asks the integration that
  consumes each section, so it sees the same merged view as the user.
- **Save** writes the entry in the user layer shared by the integrations: usable
  at once. An entry of the catalog is edited as a local override; overriding
  keeps its picture unless a new one is uploaded.
- **Propose to the catalog** (needs the certification that any picture is yours,
  CC BY 4.0) makes one commit holding the entry and opens a pull request from
  your fork. Saving again while the pull request is open adds a commit to it.
  Once it is merged and released, your local copy is removed automatically when
  it is identical to the catalog's (otherwise it stays; delete it by hand).

## API (administrators only)

Websocket commands `reeftech_catalog_editor/…`: `catalogs`, `form`, `entries`,
`entry`, `suggest_id`, `validate`, `save`, `delete`, `github_status`,
`github_login`, `github_login_poll`, `github_logout`, `contribute`,
`contributions`. Pictures are uploaded with
`POST /api/reeftech_catalog_editor/image` (multipart field `file`); the answer
carries a `token` to give to `validate` / `save`.

## Synced files

`custom_components/reeftech_catalog_editor/catalog_pack.py`,
`catalog_runtime.py` and `catalog_rules.py` are **copies** made by
`scripts/sync_client.py` of the catalog repository. Do not edit them here.

## Development

```
pip install -r requirements.txt
ruff check . && ruff format --check .
pyright custom_components/reeftech_catalog_editor tests
pytest --cov=custom_components --cov-fail-under=100
cd tests/js && npm install && node --test   # the card, in jsdom
```

## License

Code: see the catalog repository. Pictures contributed to the catalog are
published under CC BY 4.0 and must be your own.
