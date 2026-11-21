# Catalog editor

A Home Assistant integration to add and edit entries of the
[ReefTech catalog](https://github.com/Elwinmage/reeftech-catalog) (equipment,
supplements, parameters, water tests) and of the
[house catalog](https://github.com/Elwinmage/house-catalog) (trees and objects
of the house view) and the species of the
[reeftank catalog](https://github.com/Elwinmage/reeftank-catalog) (fish,
corals, plants, invertebrates) from the UI, with the picture upload included
(the pictures of a species are an atlas built by the tools of its catalog: the
editor edits its description).

An entry you save is written in the **user layer shared by every integration
reading the catalog** (`<config>/reeftech_catalog/user/<section>/`): it is
usable at once, without waiting for a release. Contributing it to the catalog
itself (a pull request) comes on top of that.

## User guide

A step-by-step guide with screenshots (install, download a catalog, find and edit an entry, the three levels of rendering of a fish, photo and animation, propose to the catalog, follow your pull requests):

[<img src="https://flagicons.lipis.dev/flags/4x3/gb.svg" width="5%" alt="English" title="English"/>](docs/guide/guide.en.md) [<img src="https://flagicons.lipis.dev/flags/4x3/fr.svg" width="5%" alt="Français" title="Français"/>](docs/guide/guide.fr.md) [<img src="https://flagicons.lipis.dev/flags/4x3/de.svg" width="5%" alt="Deutsch" title="Deutsch"/>](docs/guide/guide.de.md) [<img src="https://flagicons.lipis.dev/flags/4x3/es.svg" width="5%" alt="Español" title="Español"/>](docs/guide/guide.es.md) [<img src="https://flagicons.lipis.dev/flags/4x3/it.svg" width="5%" alt="Italiano" title="Italiano"/>](docs/guide/guide.it.md) [<img src="https://flagicons.lipis.dev/flags/4x3/nl.svg" width="5%" alt="Nederlands" title="Nederlands"/>](docs/guide/guide.nl.md) [<img src="https://flagicons.lipis.dev/flags/4x3/pl.svg" width="5%" alt="Polski" title="Polski"/>](docs/guide/guide.pl.md) [<img src="https://flagicons.lipis.dev/flags/4x3/pt.svg" width="5%" alt="Português" title="Português"/>](docs/guide/guide.pt.md)

## Install

1. Install the integration (HACS custom repository, or copy
   `custom_components/catalog_editor`) and add it in *Settings →
   Devices & services*.
2. It asks for the **client ID of a GitHub OAuth App** (see below). It is public
   (no secret is needed with the device flow). It also asks which **catalogs to
   subscribe to** (equipment, supplements, parameters, water tests, trees, objects;
   all by default);
   change them later in the *Configure* menu of the integration, which reloads it.
   A catalog you are not subscribed to is neither downloaded nor editable.
3. Add the card to a dashboard: `type: custom:catalog-editor-card`. The
   integration serves it and loads it by itself, nothing to add to the
   resources, and there is no build step.

The editor works **on its own**: it downloads the catalogs it edits (equipment,
supplements, parameters) into the **shared pack**
(`<config>/reeftech_catalog/pack/<section>/`) the first time you open the card
(*Download* button), and the *Check for updates* button fetches a newer release.
When an integration reading the same catalog is installed (`maintenance_hub`,
`reef_maintenance`, `redsea`, `reeftank`), they share that pack: one download for
everybody, and an update is seen by all.

### The GitHub OAuth App

Only needed to propose entries to the catalog (editing locally works without).
Create the app in a minute:

1. Open <https://github.com/settings/applications/new> (sign in to GitHub).
2. *Application name*: anything (e.g. `Catalog editor`). *Homepage URL* and
   *Authorization callback URL*: any address, e.g.
   `https://github.com/Elwinmage/catalog-editor`; they are not used.
3. Tick **Enable Device Flow**, then **Register application**.
4. Copy the **Client ID** of the next page (no secret needed) into the
   integration (at setup, or later by removing and adding it again).

Then *Connect to GitHub* in the card: you get a code to type on a GitHub page.
The editor asks for the `public_repo` scope only: it forks the catalog, pushes a
branch of the fork and opens the pull request. The token stays in Home Assistant's
storage (`.storage/catalog_editor`).

## How it works

- The **form** of each kind of entry is generated from the JSON Schemas
  published by the catalog releases (`schema.zip`), so a new field of the
  catalog shows up here without a new version of the editor or of the card.
- A draft is checked with the **same rules as the catalog CI**: what the editor
  accepts is what the CI accepts. Each catalog repository owns its rules and
  copies them here with its `sync_client.py` (`catalog_rules.py` from
  reeftech-catalog, `house_catalog_rules.py` from house-catalog,
  `reeftank_catalog_rules.py` from reeftank-catalog); `rules.py` picks the ones
  of a kind of entry.
- The catalog client only knows the sections of reeftech-catalog. Another
  catalog describes itself (repository, sections, layout) in a module it copies
  here (`house_catalog_sections.py`, `reeftank_catalog_sections.py`), which
  `catalogs.py` declares to the client: a new section of that catalog normally
  needs only its translations here.
- reeftank-catalog publishes **one release for all its species** (what the
  reeftank integration reads), not one per section: `reeftank_pack.py` cuts its
  manifest into the sections of the editor (fish, corals, plants,
  invertebrates) and reads their JSON Schemas from the `schema.zip` of that
  release.
- The catalogs are picked in a **drop-down list**, each followed by its family:
  *(reeftech)*, *(reeftank)* or *(house view)*.
- **Photo of a fish and its animation** (reeftank): a fish has no picture to
  upload; a photo (side view, head to the right, flat magenta or green
  background) is turned into the *degraded* atlas the reeftank integration plays
  (`swim`, `idle`, `turn`; the same code as `scripts/still_atlas.py` of
  reeftank-catalog, copied here as `reeftank_catalog_still.py`). The photo
  comes from an image model, with the **fixed, versioned prompt** of
  reeftank-catalog (`prompts/still_photo.json`) and **your own API key**, or
  from your own photo (then give its author and license). *Show the prompt*
  lets you use any other image tool by hand. The photo is checked first (flat
  background, whole fish, large enough). The entry records where it comes from
  (`source`: `ai-generated` and the model, or `photo`, author, license), and
  the pull request holds the atlas and its thumbnail, **never the photo**. A
  species with a real animation made from videos is not replaced unless you say
  so. *Play the animation* opens a panel beside the form that loops one sequence:
  `stay`, `swim`, `turn`, then `turn` again drawn mirrored (so the fish faces the
  way it started), and over again. It plays the animation the entry has, or the
  one just built, on a water, dark or light background.
- **Photo of a plant, and trying again until it suits**: a plant has one
  picture (one specimen standing on the bottom of a square frame, clip `still`),
  made from the plant prompt of reeftank-catalog (`prompts/still_plant.json`;
  the form of the plant comes from its zone, so choose the zone first; the code
  is `reeftank_catalog_plant.py`). A plant is asked on a **magenta** background:
  green is only for the species listed in `species_keys` (red, pink or purple
  plants), because a green plant on a green background is keyed out and turns
  grey. After each generation the card shows the picture received **beside the
  same picture once its background is removed**, on a checkerboard, so that a
  grey or eaten plant is seen before anything is built, with the result of the
  automatic checks. Then *Keep it* builds the picture, or *Try again* asks the
  image model again, **on the same background or on the other one** (choosing
  green for a plant that is not listed shows a warning). The attempts of the
  session stay as thumbnails to compare and go back to one. An entry that
  already has a picture shows it at the top of the panel, above the attempts, to
  compare, and offers *Regenerate the picture*; nothing changes in the entry
  until the new picture is built and the entry saved.
  Choose the provider (Google Gemini, OpenAI or Cloudflare Workers AI, whose key is written `<account id>:<API token>` and which has a free daily allowance; another is a function in
  `image_providers.py`), the key and, if you want, a model in the **options** of
  the integration. The key stays in the config entry and is never sent back to
  the card.
- A **colour** of an entry (trees, objects) is picked or typed as `#rrggbb`.
- Pictures are normalised (transparent WebP, 512 px and 128 px, size limits).
- The editor reads the shared pack plus the shared user layer itself, so it sees
  the same merged view as the integrations. A consumer too old for a new release
  keeps its own copy of the previous pack.
- **Save** writes the entry in the user layer shared by the integrations: usable
  at once. An entry of the catalog is edited as a local override; overriding
  keeps its picture unless a new one is uploaded.
- **Propose to the catalog** (needs the certification that any picture is yours,
  CC BY 4.0) makes one commit holding the entry and opens a pull request from
  your fork. Saving again while the pull request is open adds a commit to it.
  Once it is merged and released, your local copy is removed automatically when
  it is identical to the catalog's (otherwise it stays; delete it by hand).
- A pull request goes to the **repository of the catalog** of its entry.
  *Propose all my entries* therefore opens one pull request per repository
  when your entries belong to both.
- The list of your pull requests is filtered: **Open** (default), **Merged**
  (not yet in a release), **In the catalog** (released) and **All**; refused
  (closed) pull requests only show in *All*, with a badge.

## API (administrators only)

Websocket commands `catalog_editor/…`: `catalogs`, `refresh`, `form`, `entries`,
`entry`, `suggest_id`, `validate`, `save`, `delete`, `github_status`,
`github_login`, `github_login_poll`, `github_logout`, `contribute`,
`contributions`, and for the photo of a fish or a plant `image_status`, `image_prompt`,
`image_generate`, `image_build`. Pictures are uploaded with
`POST /api/catalog_editor/image` (multipart field `file`); the answer
carries a `token` to give to `validate` / `save`. A photo of a species is
uploaded with `POST /api/catalog_editor/photo` (fields `file`, optional `key`);
`image_build` turns the photo into an atlas and answers with a `token` to give
to `validate` / `save` as `atlas`.

## Synced files

`custom_components/catalog_editor/catalog_pack.py`,
`catalog_runtime.py` and `catalog_rules.py` are **copies** made by
`scripts/sync_client.py` of the catalog repository, and so are
`house_catalog_*.py` and `reeftank_catalog_*.py` (including the atlas code
`reeftank_catalog_still.py`; each from its own
repository). Do not edit them here.

## Development

```
pip install -r requirements.txt
ruff check . && ruff format --check .
pyright custom_components/catalog_editor tests
pytest --cov=custom_components --cov-fail-under=100
cd tests/js && npm install && node --test   # the card, in jsdom
```

## License

Code: see the catalog repository. Pictures contributed to the catalog are
published under CC BY 4.0 and must be your own.
