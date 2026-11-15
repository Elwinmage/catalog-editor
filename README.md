# ReefTech catalog editor

A Home Assistant integration to add and edit entries of the
[ReefTech catalog](https://github.com/Elwinmage/reeftech-catalog) (equipment,
supplements, parameters) from the UI, with the picture upload included.

An entry you save is written in the **user layer shared by every integration
reading the catalog** (`<config>/reeftech_catalog/user/<section>/`): it is
usable at once, without waiting for a release. Contributing it to the catalog
itself (a pull request) comes on top of that.

## How it works

- The **form** of each kind of entry is generated from the JSON Schemas
  published by the catalog releases (`schema.zip`), so a new field of the
  catalog shows up here without a new version of the editor.
- A draft is checked with the **same rules as the catalog CI**
  (`catalog_rules.py`): what the editor accepts is what the CI accepts.
- Pictures are normalised (transparent WebP, 512 px and 128 px, size limits).
- The editor does not read the catalog by itself: it asks the integration that
  consumes each section (`maintenance_hub` or `reef_maintenance` for equipment,
  `redsea` for supplements, `reeftank` or `redsea` for parameters), so it sees
  the same merged view as the user.
- An entry of the catalog is edited as a local override; overriding keeps its
  picture unless a new one is uploaded.

## API (administrators only)

Websocket commands `reeftech_catalog_editor/…`: `catalogs`, `form`, `entries`,
`entry`, `suggest_id`, `validate`, `save`, `delete`. Pictures are uploaded with
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
```

## License

Code: see the catalog repository. Pictures contributed to the catalog are
published under CC BY 4.0 and must be your own.
