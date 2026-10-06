"""Robot part aliases (`Wyrm Chassis`), and building/writing index/aliases.json.

Run: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "tools"))

from wrfdb_data import robot_parts  # noqa: E402
from wrfdb_data.paths import ALIASES_REL, OBJECTS_REL  # noqa: E402

GROUPS = {
    "titan-chassis": {"name": {"en": "Titan Chassis"}},
    "non-titan-torsos": {"name": {"en": "Torso"}},
    "non-titan-shoulder": {"name": {"en": "Shoulder"}},
    "light-weapon": {"name": {"en": "Light Weapon"}},
}


def module(name: str, group: str, status: str = "Ready", robot: str | None = "wyrm", **extra) -> dict:
    obj = {"name": {"en": name}, "production_status": status, "module_group_ref": f"OBJID_ModuleGroup::{group}"}
    if robot:
        obj["virtual_bot_ref"] = f"OBJID_VirtualBot::{robot}"
    return obj | extra


class RobotPartsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write_modules(self, modules: dict) -> None:
        objects = self.data / OBJECTS_REL
        objects.mkdir(parents=True, exist_ok=True)
        (objects / "Module.json").write_text(json.dumps(modules), encoding="utf-8")
        (objects / "ModuleGroup.json").write_text(json.dumps(GROUPS), encoding="utf-8")
        robots = {"wyrm": {"name": {"en": "Wyrm"}}, "relic-bulgasari": {"name": {"en": "Relic Bulgasari"}}}
        (objects / "VirtualBot.json").write_text(json.dumps(robots), encoding="utf-8")

    def build(self, modules: dict) -> robot_parts.AliasesResult:
        self.write_modules(modules)
        return robot_parts.build_aliases(self.data)


class TestAliases(RobotPartsCase):
    def test_part_from_group_name(self):
        result = self.build({
            "chassis": module("Wyrm", "titan-chassis"),
            "torso": module("Wyrm", "non-titan-torsos"),
        })
        self.assertEqual(result.aliases, {"chassis": ["Wyrm Chassis"], "torso": ["Wyrm Torso"]})

    def test_shoulder_side_both_ways(self):
        result = self.build({"l": module("Wyrm", "non-titan-shoulder", shoulder_side="L")})
        self.assertEqual(result.aliases, {"l": ["Wyrm Shoulder Left", "Wyrm Left Shoulder", "Wyrm Shoulder"]})

    def test_variants_and_the_plain_name_to_the_top_mark(self):
        result = self.build({
            "mk2": module("Relic Bulgasari Mk. II", "non-titan-shoulder", robot="relic-bulgasari", shoulder_side="L"),
            "mk1": module("Relic Bulgasari Mk. I", "non-titan-shoulder", robot="relic-bulgasari", shoulder_side="R"),
        })
        self.assertEqual(result.aliases, {
            "mk2": ["Relic Bulgasari Shoulder Mk. II", "Relic Bulgasari Shoulder Left",
                    "Relic Bulgasari Left Shoulder", "Relic Bulgasari Shoulder"],
            "mk1": ["Relic Bulgasari Shoulder Mk. I", "Relic Bulgasari Shoulder Right", "Relic Bulgasari Right Shoulder"],
        })

    def test_unranked_siblings_all_get_the_plain_name(self):
        result = self.build({
            "l": module("Wyrm", "non-titan-shoulder", shoulder_side="L"),
            "r": module("Wyrm", "non-titan-shoulder", shoulder_side="R"),
        })
        self.assertEqual([a[-1] for a in result.aliases.values()], ["Wyrm Shoulder", "Wyrm Shoulder"])

    def test_skips_non_parts_and_unpublished(self):
        result = self.build({
            "weapon": module("Scourge", "light-weapon", robot=None),
            "robotless": module("Wyrm", "titan-chassis", robot=None),
            "unreleased": module("Wyrm", "titan-chassis", status="InDevelopment"),
        })
        self.assertEqual(result.aliases, {})


class TestWrite(RobotPartsCase):
    def test_write_only_when_changed(self):
        self.write_modules({"chassis": module("Wyrm", "titan-chassis")})
        self.assertTrue(robot_parts.write_aliases(self.data).changed)
        written = json.loads((self.data / ALIASES_REL).read_text(encoding="utf-8"))
        self.assertEqual(written, {"chassis": ["Wyrm Chassis"]})
        self.assertFalse(robot_parts.write_aliases(self.data).changed)


if __name__ == "__main__":
    unittest.main()
