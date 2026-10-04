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
    name. A first name shared by several pilots goes to the premium (hero) one; two
    premiums sharing one is an error and neither gets it. Rules in
    `tools/wrfdb_data/nicknames.py`.
  - `robot_release_dates.json`: first-availability date per robot, keyed by
    `OBJID_VirtualBot::<id>`. New robots are added automatically; article-derived
    fields are filled by hand.
  - `patch_manifests.json`: one entry per Steam build, keyed by manifest GID.
- `textures/`: exported images.
- `tools/wrfdb_data/`: the Python code that builds `index/` (standard library only).

## Tools

The Orchestrator calls these after each parse. To run them by hand:

```bash
PYTHONPATH=tools python3 -m wrfdb_data slug-map            # rebuild index/slug_map.json
PYTHONPATH=tools python3 -m wrfdb_data slug-map --no-write # report only
PYTHONPATH=tools python3 -m wrfdb_data nicknames          # rebuild index/nicknames.json
PYTHONPATH=tools python3 -m wrfdb_data releases --no-write # detect new robots only
python3 -m unittest discover -s tests                     # tests
```

Slug rules per type are documented in `tools/wrfdb_data/slug_map.py`. A slug change
moves a page, so change a rule only on purpose.
