"""Paths within a WRFrontiersDB-Data checkout, and the JSON read/write helpers.

`current/` is the Parser's output for the latest game version; the Parser's push
replaces it wholesale each run. Everything else the repo publishes is derived
from `current/` (or curated by hand on top of it) and lives in `index/`.
"""

from __future__ import annotations

import json
from pathlib import Path

CURRENT_REL = Path("current")
OBJECTS_REL = CURRENT_REL / "Objects"
VERSION_REL = CURRENT_REL / "version.txt"

INDEX_REL = Path("index")
SLUG_MAP_REL = INDEX_REL / "slug_map.json"
NICKNAMES_REL = INDEX_REL / "nicknames.json"
ALIASES_REL = INDEX_REL / "aliases.json"
ABBREVIATIONS_REL = INDEX_REL / "abbreviations.json"
RELEASE_DATES_REL = INDEX_REL / "robot_release_dates.json"
PATCHES_REL = INDEX_REL / "patch_manifests.json"
BUILD_CODES_REL = INDEX_REL / "build_codes.json"
BUILD_CODE_VECTORS_REL = INDEX_REL / "build_code_vectors.json"


class DataRepoError(RuntimeError):
    """The data repo could not be read or written."""


def objects_file(data_dir: Path, object_type: str) -> Path:
    return Path(data_dir) / OBJECTS_REL / f"{object_type}.json"


def read_version(data_dir: Path) -> str:
    path = Path(data_dir) / VERSION_REL
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise DataRepoError(f"version.txt unreadable ({path}): {exc}") from exc


def load_json(path: Path, what: str) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataRepoError(f"{what} not found: {path}") from exc
    except (json.JSONDecodeError, OSError) as exc:
        raise DataRepoError(f"{what} unreadable ({path}): {exc}") from exc
    if not isinstance(doc, dict):
        raise DataRepoError(f"{what} is not an object: {path}")
    return doc


def save_json(path: Path, doc: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
