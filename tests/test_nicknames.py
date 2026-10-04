"""Pilot nicknames (first names), and building/writing index/nicknames.json.

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

from wrfdb_data import nicknames  # noqa: E402
from wrfdb_data.paths import NICKNAMES_REL, OBJECTS_REL  # noqa: E402

PREMIUM = "OBJID_PilotType::DA_PilotType_Legendary.0"
COMMON = "OBJID_PilotType::DA_PilotType_Common.0"


def hero(first: str, second: str) -> dict:
    return {"first_name": {"en": first}, "second_name": {"en": second}, "pilot_type_ref": PREMIUM}


def common(name: str, pilot_type_ref: str = COMMON) -> dict:
    return {"first_name": {"en": name}, "pilot_type_ref": pilot_type_ref}


class NicknamesCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write_pilots(self, pilots: dict) -> None:
        path = self.data / OBJECTS_REL / "Pilot.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(pilots), encoding="utf-8")

    def build(self, pilots: dict) -> nicknames.NicknamesResult:
        self.write_pilots(pilots)
        return nicknames.build_nicknames(self.data)


class TestFirstName(NicknamesCase):
    def test_hero_first_name_field(self):
        self.assertEqual(self.build({"p": hero("Marcus", "Shedd")}).nicknames, {"p": ["Marcus"]})

    def test_common_first_word_without_quotes(self):
        result = self.build({
            "a": common("Marcus Davis"),
            "b": common('"Hammer" Petrova'),
            "c": common('﻿"Wild" Wilson'),
        })
        self.assertEqual(result.nicknames, {"a": ["Marcus"], "b": ["Hammer"], "c": ["Wild"]})

    def test_hero_with_whole_name_in_first_name(self):
        self.assertEqual(self.build({"p": common("Emma James", PREMIUM)}).nicknames, {"p": ["Emma"]})

    def test_single_name_gets_no_nickname(self):
        result = self.build({"a": common("Echo"), "b": hero("Ever", " ")})
        self.assertEqual(result.nicknames, {})


class TestSharedFirstName(NicknamesCase):
    def test_premium_wins(self):
        result = self.build({"davis": common("Marcus Davis"), "shedd": hero("Marcus", "Shedd")})
        self.assertEqual(result.nicknames, {"shedd": ["Marcus"]})
        self.assertEqual((result.conflicts, result.ambiguous), ([], []))

    def test_two_premiums_conflict(self):
        result = self.build({
            "a": hero("Marcus", "Shedd"), "b": hero("Marcus", "Other"), "c": common("Marcus Davis"),
        })
        self.assertEqual(result.nicknames, {})
        self.assertEqual(result.conflicts, [("marcus", ["a", "b", "c"])])

    def test_commons_only_are_ambiguous(self):
        result = self.build({"a": common("Sarah Ali"), "b": common("Sarah Nguyen"), "c": common("Rex Cole")})
        self.assertEqual(result.nicknames, {"c": ["Rex"]})
        self.assertEqual(result.ambiguous, [("sarah", ["a", "b"])])
        self.assertEqual(result.conflicts, [])


class TestWrite(NicknamesCase):
    def test_write_only_when_changed(self):
        self.write_pilots({"p": hero("Kate", "Sinclair")})
        self.assertTrue(nicknames.write_nicknames(self.data).changed)
        written = json.loads((self.data / NICKNAMES_REL).read_text(encoding="utf-8"))
        self.assertEqual(written, {"p": ["Kate"]})
        self.assertFalse(nicknames.write_nicknames(self.data).changed)


if __name__ == "__main__":
    unittest.main()
