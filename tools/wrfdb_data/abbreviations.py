"""Build `index/abbreviations.json`: shorthand -> the full word(s) it stands for.

An abbreviation is a shorthand for words of a name, for consumers that match
what people type: the Discord bot reads `[[r bulg 2]]` as `relic bulgasari mk
ii`. A shorthand can be several words (`mk 2`); consumers match the longest one
first, so `mk 2` is `mk ii`, not `mk mk ii`. It
applies to every name with that word (the robot, its parts, relic weapons), so
one entry covers what would otherwise be a nickname per object. Consumers expand
a query's words only after it fails to match as typed, so an abbreviation never
hides a real name. It never builds a URL.

The table is curated here (ABBREVIATIONS), not derived. Building it checks each
full form's words against the published names: one that no name has any more is
reported as unused (renamed or removed in game), and is still written.

Console-I/O free: problems come back in the result for the caller to report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .paths import ABBREVIATIONS_REL, DataRepoError, load_json, objects_file, save_json
from .slug_map import OBJECT_TYPES, _has_page, default_string, to_slug

ABBREVIATIONS: dict[str, str] = {
    # Relic robots and weapons: `Relic Bulgasari`, `Relic Orkan`.
    "r": "relic",
    # Robots whose names are long enough that players shorten them.
    "bulg": "bulgasari",
    "lance": "lancelot",
    "scorp": "scorpion",
    "matri": "matriarch",
    "varang": "varangian",
    "cyc": "cyclops",
    # Variant marks: `Relic Bulgasari Mk. II` is `r bulg 2`, `r bulg mk2`, `r bulg mk 2`.
    "1": "mk i",
    "2": "mk ii",
    "mk1": "mk i",
    "mk2": "mk ii",
    "mk 1": "mk i",
    "mk 2": "mk ii",
}
"""Lowercase words, space-separated, on both sides."""

Abbreviations = dict[str, str]


@dataclass
class AbbreviationsResult:
    abbreviations: Abbreviations
    unused: list[tuple[str, str]] = field(default_factory=list)
    """(abbreviation, full form) where no published name has all its words."""
    changed: bool = False
    """The file on disk was different (or missing) and has been rewritten."""


def _name_words(data_dir: Path) -> set[str]:
    """Every word of every published object's English name."""
    words: set[str] = set()
    for object_type in OBJECT_TYPES:
        for obj in load_json(objects_file(data_dir, object_type), f"{object_type} objects").values():
            if not _has_page(object_type, obj):
                continue
            texts = (obj.get("name"), obj.get("first_name"), obj.get("last_name"), obj.get("second_name"))
            for text in texts:
                try:
                    words.update(to_slug(default_string(text) or "").split("-"))
                except ValueError:
                    continue  # no usable name; slug_map reports it
    return words


def build_abbreviations(data_dir: Path) -> AbbreviationsResult:
    """The curated table, checked against `current/Objects`. Raises DataRepoError if a file is unreadable."""
    words = _name_words(data_dir)
    result = AbbreviationsResult(dict(ABBREVIATIONS))
    result.unused = [(short, full) for short, full in ABBREVIATIONS.items() if not set(full.split()) <= words]
    return result


def write_abbreviations(data_dir: Path) -> AbbreviationsResult:
    """Build the abbreviations and write `index/abbreviations.json` if they changed."""
    result = build_abbreviations(data_dir)
    path = Path(data_dir) / ABBREVIATIONS_REL
    try:
        current = load_json(path, "abbreviations")
    except DataRepoError:
        current = None
    if current != result.abbreviations or list(current) != list(result.abbreviations):
        save_json(path, result.abbreviations)
        result.changed = True
    return result
