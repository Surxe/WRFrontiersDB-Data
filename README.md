# WRFrontiersDB-Data
Parsed data for WRFrontiersDB

## Layout

- `current/`: the Parser's output for the latest game version (`version.txt`,
  `Objects/`, `Localization/`, ...). The Parser's push replaces it wholesale.
- `index/`: everything derived from `current/`, or curated on top of it. Kept outside
  `current/` so a parse never wipes it. Rebuilt and pushed by the Orchestrator's INDEX
  stage after each parse.
  - `slug_map.json`: object id -> slug, the URL path segment of the object's page
    (`/pilots/<slug>/`). Only objects that have a page are listed. The Site and the
    Discord bot both read it.
  - `nicknames.json`: object id -> other names it is known by, for matching what people
    type (the Discord bot's `[[marcus]]`); never used for URLs. Today: a pilot's first
    name, and a robot chassis's legs (`Wyrm Legs`). A first name shared by several
    pilots goes to the premium (hero) one; two premiums sharing one is an error and
    neither gets it. A nickname answers only when no object has that exact name. Rules
    in `tools/wrfdb_data/nicknames.py`.
  - `aliases.json`: object id -> full alternative names, matched like the object's own
    name (and shown in its place: the first one). Today: robot parts, named after their
    robot, get `<robot> <part>` (`Wyrm Chassis`, `Wyrm Shoulder Left`), variants
    `<robot> <part> <variant>` (`Relic Bulgasari Shoulder Mk. II`). Rules in
    `tools/wrfdb_data/robot_parts.py`.
  - `abbreviations.json`: shorthand -> full word(s) (`r` -> `relic`, `bulg` -> `bulgasari`,
    `2` / `mk2` / `mk 2` -> `mk ii`), for expanding the words of a query that matched
    nothing as typed; the longest shorthand matches first.
    Curated in `tools/wrfdb_data/abbreviations.py`; a full form whose words no published
    name has is reported.
  - `robot_release_dates.json`: first-availability date per robot, keyed by
    `OBJID_VirtualBot::<id>`. New robots are added automatically; article-derived
    fields are filled by hand.
  - `patch_manifests.json`: one entry per Steam build, keyed by manifest GID.
  - `build_codes.json`: the build-code registry, so a robot build fits in a short
    string (`/models?a=<code>`). Append-only; specified in `docs/build-codes.md`.
    `build_code_vectors.json` holds builds and their codes that every codec must
    reproduce.
- `textures/`: exported images.
- `tools/wrfdb_data/`: the Python code that builds `index/` and deploy records
  (standard library only), and the reference build-code codec (`build_code.py`).
- `tools/js/build_code.js`: the same build-code codec for JavaScript (no
  dependencies), used by the Site.
- `docs/build-codes.md`: build codes for other apps (the codec and registry the Site
  serves at `https://wrf-db.info/build-code.js` and `/build_codes.json`), and the
  format, for anyone writing a codec.
- `.github/actions/`: composite actions the frontends (Site, Discount Visualizer) use.

## Tools

The Orchestrator's INDEX stage (`SHOULD_BUILD_INDEX`, on in every `--patch-day` run)
calls these after each parse and publishes `index/`. To run them by hand:

```bash
PYTHONPATH=tools python3 -m wrfdb_data slug-map            # rebuild index/slug_map.json
PYTHONPATH=tools python3 -m wrfdb_data slug-map --no-write # report only
PYTHONPATH=tools python3 -m wrfdb_data nicknames          # rebuild index/nicknames.json
PYTHONPATH=tools python3 -m wrfdb_data aliases            # rebuild index/aliases.json
PYTHONPATH=tools python3 -m wrfdb_data abbreviations      # rebuild index/abbreviations.json
PYTHONPATH=tools python3 -m wrfdb_data build-codes        # rebuild index/build_codes.json + vectors
PYTHONPATH=tools python3 -m wrfdb_data releases --no-write # detect new robots only
PYTHONPATH=tools python3 -m wrfdb_data deploy-record --app-dir ../WRFrontiersDB-Site
python3 -m unittest discover -s tests                     # tests
node --test 'tests/js/*.test.mjs'                          # JavaScript codec tests
```

Slug rules per type are documented in `tools/wrfdb_data/slug_map.py`. A slug change
moves a page, so change a rule only on purpose.

## Frontend deploys: which data is live

The Site and the Discount Visualizer build from a checkout of this repo, using two
shared actions (referenced as `Surxe/WRFrontiersDB-Data/.github/actions/<name>@main`):

- `checkout-data`: checks this repo out (it's public, so no token) at `ref` (default
  `main`) and outputs the commit `sha` and `version`. Pass a sha as `ref` to pin every
  job of a run to the same data.
- `record-deploy`: after the build, writes the deploy record into the build output as
  `deploy.json` and uploads it as the `deploy-record` run artifact.

So each live frontend serves `/deploy.json` saying which Data commit it was built from
(`data_commit`, `data_commit_date_utc`, `data_version`), plus its own commit and run.
Fields are documented in `tools/wrfdb_data/deploy_record.py`. Check both at once with
the Orchestrator's `bin/wrf-deployed`.
