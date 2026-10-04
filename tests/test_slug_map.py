"""Slug rules per object type, and building/writing index/slug_map.json.

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

from wrfdb_data import slug_map  # noqa: E402
from wrfdb_data.paths import OBJECTS_REL, SLUG_MAP_REL  # noqa: E402

LIGHT_WEAPON = {"light-weapon": {"id": "light-weapon", "name": {"en": "Light Weapon"}}}


class DataDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        for object_type in slug_map.OBJECT_TYPES:
            self.write_objects(object_type, {})

    def write_objects(self, object_type: str, objects: dict) -> None:
        path = self.data / OBJECTS_REL / f"{object_type}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(objects), encoding="utf-8")

    def build(self) -> slug_map.SlugMapResult:
        return slug_map.build_slug_map(self.data)


class TestStringHelpers(unittest.TestCase):
    def test_to_slug_drops_apostrophes_and_collapses_separators(self):
        self.assertEqual(slug_map.to_slug("  O'Reilly -- Jean_Luc!! "), "oreilly-jean-luc")

    def test_camel_to_kebab_expands_difficulty_and_strips_bot_prefixes(self):
        self.assertEqual(slug_map.camel_to_kebab("DA_Preset_Bot_AdvRaider.0"), "advanced-raider")
        self.assertEqual(slug_map.camel_to_kebab("DA_Preset_Guardian.0"), "guardian")
        self.assertEqual(slug_map.camel_to_kebab("DA_Preset_Begin_DevBot_Titan.3"), "beginner-dev-titan")

    def test_default_string_prefers_en_for_localized_keys(self):
        key = {"Key": "k", "TableNamespace": "t", "en": "English", "InvariantString": "raw"}
        self.assertEqual(slug_map.default_string(key), "English")
        self.assertEqual(slug_map.default_string({"InvariantString": "raw", "en": "x"}), "raw")
        with self.assertRaises(ValueError):
            slug_map.default_string({"Key": "k", "TableNamespace": "t"})


class TestSlugRules(DataDirCase):
    def test_pilot_first_and_last_name(self):
        self.write_objects("Pilot", {
            "p1": {"first_name": {"en": "John"}, "last_name": {"en": "Doe"}},
            "p2": {"first_name": {"en": "Jean-Luc"}, "second_name": {"en": "O'Reilly"}},
            "p3": {"first_name": {"en": "Cher"}},
        })
        self.assertEqual(self.build().slug_map, {"p1": "john-doe", "p2": "jean-luc-oreilly", "p3": "cher"})

    def test_module_group_and_name_only_when_ready(self):
        self.write_objects("ModuleGroup", LIGHT_WEAPON)
        self.write_objects("Module", {
            "m1": {"name": {"en": "Laser Cannon"}, "production_status": "Ready",
                   "module_group_ref": "OBJID_ModuleGroup::light-weapon"},
            "m2": {"name": {"en": "Prototype"}, "module_group_ref": "OBJID_ModuleGroup::light-weapon"},
            "m3": {"name": {"en": "Orphan"}, "production_status": "Ready"},
        })
        result = self.build().slug_map
        self.assertEqual(result["m1"], "light-weapon-laser-cannon")
        self.assertNotIn("m2", result)
        self.assertEqual(result["m3"], "module-orphan")

    def test_titan_shoulders_by_side_and_robot(self):
        self.write_objects("Module", {
            "l": {"production_status": "Ready", "shoulder_side": "L",
                  "module_group_ref": "OBJID_ModuleGroup::titan-shoulder",
                  "virtual_bot_ref": "OBJID_VirtualBot::norna"},
            "r": {"production_status": "Ready", "shoulder_side": "R",
                  "module_group_ref": "OBJID_ModuleGroup::titan-shoulder",
                  "virtual_bot_ref": "OBJID_VirtualBot::norna"},
        })
        self.assertEqual(self.build().slug_map,
                         {"l": "titan-shoulder-left-norna", "r": "titan-shoulder-right-norna"})

    def test_character_presets_factory_by_name_ai_by_id(self):
        self.write_objects("CharacterPreset", {
            "DA_Preset_Factory.0": {"id": "DA_Preset_Factory.0", "name": {"en": "Assembler"},
                                    "is_factory_preset": True},
            "DA_Preset_Guardian.0": {"id": "DA_Preset_Guardian.0", "name": {"en": "Ignored"},
                                     "is_factory_preset": False},
        })
        self.assertEqual(self.build().slug_map,
                         {"DA_Preset_Factory.0": "assembler", "DA_Preset_Guardian.0": "guardian"})

    def test_robots_use_their_id_unchanged(self):
        self.write_objects("VirtualBot", {"relic-bulgasari": {"name": {"en": "Relic Bulgasari"}}})
        self.assertEqual(self.build().slug_map, {"relic-bulgasari": "relic-bulgasari"})

    def test_currency_and_default_types_by_name(self):
        self.write_objects("Currency", {"c": {"name": {"en": "Salvage"}}})
        self.write_objects("Faction", {"f": {"name": {"en": "Free Contractors"}}})
        self.assertEqual(self.build().slug_map, {"c": "salvage", "f": "free-contractors"})


class TestProblems(DataDirCase):
    def test_nameless_object_is_skipped_not_mapped_to_empty(self):
        self.write_objects("Pilot", {"p1": {}})
        result = self.build()
        self.assertEqual(result.slug_map, {})
        self.assertEqual([object_id for object_id, _ in result.skipped], ["p1"])

    def test_unreadable_name_is_skipped(self):
        self.write_objects("Faction", {"f": {"name": {"Key": "k", "TableNamespace": "t"}}})
        self.assertEqual([object_id for object_id, _ in self.build().skipped], ["f"])

    def test_collisions_within_a_type_are_reported(self):
        self.write_objects("Faction", {"a": {"name": {"en": "Same"}}, "b": {"name": {"en": "same"}}})
        self.write_objects("Currency", {"c": {"name": {"en": "Same"}}})  # other type: fine
        self.assertEqual(self.build().collisions, [("Faction", "same", ["a", "b"])])


class TestWrite(DataDirCase):
    def test_writes_only_when_changed(self):
        self.write_objects("Faction", {"f": {"name": {"en": "Freecon"}}})
        self.assertTrue(slug_map.write_slug_map(self.data).changed)
        written = json.loads((self.data / SLUG_MAP_REL).read_text(encoding="utf-8"))
        self.assertEqual(written, {"f": "freecon"})
        self.assertFalse(slug_map.write_slug_map(self.data).changed)

        self.write_objects("Faction", {"f": {"name": {"en": "Freecon"}}, "g": {"name": {"en": "Gen"}}})
        self.assertTrue(slug_map.write_slug_map(self.data).changed)


class TestPublishedData(unittest.TestCase):
    """The repo's own current/ data builds a clean map."""

    def test_current_data_has_no_collisions_or_skips(self):
        if not (ROOT_DIR / OBJECTS_REL).is_dir():
            self.skipTest("no current/ data in this checkout")
        result = slug_map.build_slug_map(ROOT_DIR)
        self.assertEqual(result.collisions, [])
        self.assertEqual(result.skipped, [])


if __name__ == "__main__":
    unittest.main()
