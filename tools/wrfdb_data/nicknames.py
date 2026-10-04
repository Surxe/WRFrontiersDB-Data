"""Build `index/nicknames.json`: object id -> other names the object is known by.

A nickname is a short alternative to an object's full name for consumers that
match what people type (the Discord bot's `[[marcus]]`). It never builds a URL;
links go through the slug map. Today only pilots have nicknames:

* A pilot's nickname is its first name. Hero pilots carry it in `first_name`
  (their surname is `second_name`); everyone else keeps the whole name in
  `first_name`, so the first word is taken (`"Hammer" Petrova` -> `Hammer`).
* A nickname that is the pilot's whole name adds nothing and is left out
  (`Echo`, `Ever`).
* Pilots sharing a first name: the premium (hero) pilot gets it, so `marcus` is
  Marcus Shedd, not Marcus Davis. Two premiums sharing one is a conflict: neither
  gets it and the caller reports it as an error. Commons only: nobody gets it.

Console-I/O free: problems come back in the result for the caller to report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .paths import NICKNAMES_REL, DataRepoError, load_json, objects_file, save_json
from .slug_map import default_string, ref_to_id, to_slug

PREMIUM_PILOT_TYPE = "DA_PilotType_Legendary.0"
"""Hero pilots, sold for real money; every other pilot is a common one."""

_EDGE_PUNCTUATION = re.compile(r"^\W+|\W+$")

Nicknames = dict[str, list[str]]


@dataclass
class NicknamesResult:
    nicknames: Nicknames
    conflicts: list[tuple[str, list[str]]] = field(default_factory=list)
    """(nickname, pilot ids): two or more premium pilots share it, so nobody got it."""
    ambiguous: list[tuple[str, list[str]]] = field(default_factory=list)
    """(nickname, pilot ids): only common pilots share it, so nobody got it."""
    changed: bool = False
    """The file on disk was different (or missing) and has been rewritten."""


def _full_name(pilot: dict) -> str:
    first = default_string(pilot.get("first_name")) or ""
    last = default_string(pilot.get("last_name") or pilot.get("second_name")) or ""
    return f"{first} {last}".strip()


def first_name(pilot: dict) -> str:
    """`Marcus` for Marcus Shedd (first_name + second_name) and Marcus Davis (one string)."""
    words = (default_string(pilot.get("first_name")) or "").split()
    if not words:
        return ""
    has_surname = bool((default_string(pilot.get("last_name") or pilot.get("second_name")) or "").strip())
    name = " ".join(words) if has_surname else words[0]
    return _EDGE_PUNCTUATION.sub("", name)


def _is_premium(pilot: dict) -> bool:
    ref = pilot.get("pilot_type_ref")
    return bool(ref) and ref_to_id(ref) == PREMIUM_PILOT_TYPE


def build_nicknames(data_dir: Path) -> NicknamesResult:
    """Compute the nicknames from `current/Objects`. Raises DataRepoError if a file is unreadable."""
    pilots = load_json(objects_file(data_dir, "Pilot"), "Pilot objects")

    # nickname key -> [(pilot id, nickname)], in Pilot.json order
    candidates: dict[str, list[tuple[str, str]]] = {}
    for pilot_id, pilot in pilots.items():
        try:
            nickname = first_name(pilot)
            full_name = _full_name(pilot)
        except ValueError:
            continue  # no usable name; slug_map reports it
        key = to_slug(nickname)
        if key and key != to_slug(full_name):
            candidates.setdefault(key, []).append((pilot_id, nickname))

    result = NicknamesResult(nicknames={})
    for key, holders in candidates.items():
        if len(holders) > 1:
            premiums = [h for h in holders if _is_premium(pilots[h[0]])]
            ids = [pilot_id for pilot_id, _ in holders]
            if len(premiums) > 1:
                result.conflicts.append((key, ids))
                continue
            if not premiums:
                result.ambiguous.append((key, ids))
                continue
            holders = premiums
        pilot_id, nickname = holders[0]
        result.nicknames[pilot_id] = [nickname]

    # Pilot.json order, so the file only changes when the data does.
    result.nicknames = {pid: result.nicknames[pid] for pid in pilots if pid in result.nicknames}
    return result


def write_nicknames(data_dir: Path) -> NicknamesResult:
    """Build the nicknames and write `index/nicknames.json` if they changed."""
    result = build_nicknames(data_dir)
    path = Path(data_dir) / NICKNAMES_REL
    try:
        current = load_json(path, "nicknames")
    except DataRepoError:
        current = None
    if current != result.nicknames or list(current) != list(result.nicknames):
        save_json(path, result.nicknames)
        result.changed = True
    return result
