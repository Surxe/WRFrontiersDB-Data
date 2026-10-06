"""Build `index/aliases.json`: object id -> full alternative names.

An alias is another complete name for an object, for consumers that match what
people type (the Discord bot's `[[wyrm chassis]]`). Unlike a nickname it stands
as well as the object's own name: it can be matched loosely and shown in its
place. It never builds a URL; links go through the slug map. Today only robot
parts have aliases:

* A robot part module is named after its robot (`Wyrm`), which says nothing on
  its own, so it gets `<robot> <part>`: `Wyrm Chassis`, `Wyrm Torso`. The part
  is the end of its module group's name (`Titan Chassis` -> `Chassis`); the
  robot's name is its VirtualBot's.
* A variant's module name adds to the robot's (`Relic Bulgasari Mk. II`); the
  rest goes after the part: `Relic Bulgasari Shoulder Mk. II`. When one robot
  has several modules for a part, the plain `<robot> <part>` goes to the highest
  `Mk.` only, or to all of them if they aren't ranked that way (titan shoulders).
* A shoulder with a side also gets it, both ways round: `Wyrm Shoulder Left`,
  `Wyrm Left Shoulder`. The first alias is the one to show.

Only modules with a page (`production_status == "Ready"`) are listed. The chassis
`<robot> Legs` nickname is built from the same parts (`nicknames.py`).

Console-I/O free: the caller reports the result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .paths import ALIASES_REL, DataRepoError, load_json, objects_file, save_json
from .slug_map import default_string, ref_to_id

PARTS = ("Chassis", "Torso", "Shoulder")
CHASSIS = "Chassis"
_SHOULDER_SIDES = {"L": "Left", "R": "Right"}
_MARK = re.compile(r"^Mk\. ([IVX]+)$")
_ROMAN = {"I": 1, "V": 5, "X": 10}

Aliases = dict[str, list[str]]


@dataclass(frozen=True)
class RobotPart:
    module_id: str
    robot_name: str
    """The robot's English name (`Relic Bulgasari`)."""
    part: str
    """One of PARTS."""
    side: str | None = None
    """`Left` / `Right` for a shoulder."""
    variant: str = ""
    """What the module's name adds to the robot's (`Mk. II`), else ""."""

    @property
    def mark(self) -> int:
        """The `Mk.` number of the variant, 0 if it has none."""
        found = _MARK.match(self.variant)
        return _roman(found.group(1)) if found else 0


@dataclass
class AliasesResult:
    aliases: Aliases
    changed: bool = False
    """The file on disk was different (or missing) and has been rewritten."""


def robot_parts(data_dir: Path) -> list[RobotPart]:
    """The published robot part modules, in Module.json order. Raises DataRepoError if a file is unreadable."""
    modules = load_json(objects_file(data_dir, "Module"), "Module objects")
    groups = load_json(objects_file(data_dir, "ModuleGroup"), "ModuleGroup objects")
    robots = load_json(objects_file(data_dir, "VirtualBot"), "VirtualBot objects")
    parts = []
    for module_id, module in modules.items():
        if module.get("production_status") != "Ready" or not module.get("virtual_bot_ref"):
            continue
        try:
            name = (default_string(module.get("name")) or "").strip()
            group = groups.get(ref_to_id(module.get("module_group_ref") or ""), {})
            group_name = default_string(group.get("name")) or ""
            robot = robots.get(ref_to_id(module["virtual_bot_ref"]), {})
            robot_name = (default_string(robot.get("name")) or "").strip()
        except ValueError:
            continue  # no usable name or group; slug_map reports it
        part = next((p for p in PARTS if group_name.endswith(p)), None)
        if part is None or not name:
            continue
        variant = ""
        if robot_name and name.startswith(robot_name + " "):
            variant = name[len(robot_name):].strip()
        else:
            robot_name = name
        side = _SHOULDER_SIDES.get(module.get("shoulder_side", ""))
        parts.append(RobotPart(module_id, robot_name, part, side, variant))
    return parts


def part_aliases(part: RobotPart, plain: bool = True) -> list[str]:
    """Its aliases, the one to show first. `plain`: include `<robot> <part>`."""
    base = f"{part.robot_name} {part.part}"
    aliases = [f"{base} {part.variant}"] if part.variant else []
    if part.side:
        aliases += [f"{base} {part.side}", f"{part.robot_name} {part.side} {part.part}"]
    if plain:
        aliases.append(base)
    return aliases


def build_aliases(data_dir: Path) -> AliasesResult:
    """Compute the aliases from `current/Objects`. Raises DataRepoError if a file is unreadable."""
    parts = robot_parts(data_dir)
    siblings: dict[tuple[str, str], list[RobotPart]] = {}
    for part in parts:
        siblings.setdefault((part.robot_name, part.part), []).append(part)
    top_mark = {key: max(p.mark for p in group) for key, group in siblings.items()}
    return AliasesResult({
        part.module_id: part_aliases(part, plain=part.mark == top_mark[(part.robot_name, part.part)])
        for part in parts
    })


def _roman(numeral: str) -> int:
    values = [_ROMAN[c] for c in numeral]
    return sum(-v if i + 1 < len(values) and v < values[i + 1] else v for i, v in enumerate(values))


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
