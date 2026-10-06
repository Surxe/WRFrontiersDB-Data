"""Build `index/aliases.json`: object id -> full alternative names.

An alias is another complete name for an object, for consumers that match what
people type (the Discord bot's `[[wyrm chassis]]`). Unlike a nickname it stands
as well as the object's own name: it can be matched loosely and shown in its
place. It never builds a URL; links go through the slug map. Today only robot
parts have aliases:

* A robot part module is named after its robot (`Wyrm`), which says nothing on
  its own, so it gets `<robot> <part>`: `Wyrm Chassis`, `Wyrm Torso`. The part
  is the end of its module group's name (`Titan Chassis` -> `Chassis`).
* A shoulder also gets its side, both ways round: `Wyrm Shoulder Left`, `Wyrm
  Left Shoulder`. The first alias is the one to show.

Only modules with a page (`production_status == "Ready"`) are listed. The chassis
`<robot> Legs` nickname is built from the same parts (`nicknames.py`).

Console-I/O free: the caller reports the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import ALIASES_REL, DataRepoError, load_json, objects_file, save_json
from .slug_map import default_string, ref_to_id

PARTS = ("Chassis", "Torso", "Shoulder")
CHASSIS = "Chassis"
_SHOULDER_SIDES = {"L": "Left", "R": "Right"}

Aliases = dict[str, list[str]]


@dataclass(frozen=True)
class RobotPart:
    module_id: str
    robot_name: str
    """The module's English name, which is its robot's (`Wyrm`)."""
    part: str
    """One of PARTS."""
    side: str | None = None
    """`Left` / `Right` for a shoulder."""


@dataclass
class AliasesResult:
    aliases: Aliases
    changed: bool = False
    """The file on disk was different (or missing) and has been rewritten."""


def robot_parts(data_dir: Path) -> list[RobotPart]:
    """The published robot part modules, in Module.json order. Raises DataRepoError if a file is unreadable."""
    modules = load_json(objects_file(data_dir, "Module"), "Module objects")
    groups = load_json(objects_file(data_dir, "ModuleGroup"), "ModuleGroup objects")
    parts = []
    for module_id, module in modules.items():
        if module.get("production_status") != "Ready" or not module.get("virtual_bot_ref"):
            continue
        try:
            name = default_string(module.get("name")) or ""
            group = groups.get(ref_to_id(module.get("module_group_ref") or ""), {})
            group_name = default_string(group.get("name")) or ""
        except ValueError:
            continue  # no usable name or group; slug_map reports it
        part = next((p for p in PARTS if group_name.endswith(p)), None)
        if part is None or not name.strip():
            continue
        parts.append(RobotPart(module_id, name.strip(), part, _SHOULDER_SIDES.get(module.get("shoulder_side", ""))))
    return parts


def part_aliases(part: RobotPart) -> list[str]:
    if part.side:
        return [f"{part.robot_name} {part.part} {part.side}", f"{part.robot_name} {part.side} {part.part}"]
    return [f"{part.robot_name} {part.part}"]


def build_aliases(data_dir: Path) -> AliasesResult:
    """Compute the aliases from `current/Objects`. Raises DataRepoError if a file is unreadable."""
    return AliasesResult({part.module_id: part_aliases(part) for part in robot_parts(data_dir)})


def write_aliases(data_dir: Path) -> AliasesResult:
    """Build the aliases and write `index/aliases.json` if they changed."""
    result = build_aliases(data_dir)
    path = Path(data_dir) / ALIASES_REL
    try:
        current = load_json(path, "aliases")
    except DataRepoError:
        current = None
    if current != result.aliases or list(current) != list(result.aliases):
        save_json(path, result.aliases)
        result.changed = True
    return result
