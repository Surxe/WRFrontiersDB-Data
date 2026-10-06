"""The curated abbreviations table, its check against names, and writing index/abbreviations.json.

Run: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "tools"))

from wrfdb_data import abbreviations  # noqa: E402
from wrfdb_data.paths import ABBREVIATIONS_REL, OBJECTS_REL  # noqa: E402
from wrfdb_data.slug_map import OBJECT_TYPES, to_slug  # noqa: E402


class AbbreviationsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        objects = self.data / OBJECTS_REL
        objects.mkdir(parents=True)
        for object_type in OBJECT_TYPES:
            (objects / f"{object_type}.json").write_text("{}", encoding="utf-8")
        robots = {"relic-bulgasari": {"name": {"en": "Relic Bulgasari"}}}
        (objects / "VirtualBot.json").write_text(json.dumps(robots), encoding="utf-8")
        table = mock.patch.dict(abbreviations.ABBREVIATIONS, {"r": "relic", "bulg": "bulgasari", "x": "gone", "rb": "relic gone"},
                                   clear=True)
        table.start()
        self.addCleanup(table.stop)


class TestBuild(AbbreviationsCase):
    def test_reports_full_words_no_name_has(self):
        result = abbreviations.build_abbreviations(self.data)
        self.assertEqual(result.abbreviations["bulg"], "bulgasari")
        self.assertEqual(result.unused, [("x", "gone"), ("rb", "relic gone")])

    def test_write_only_when_changed(self):
        self.assertTrue(abbreviations.write_abbreviations(self.data).changed)
        written = json.loads((self.data / ABBREVIATIONS_REL).read_text(encoding="utf-8"))
        self.assertEqual(written["bulg"], "bulgasari")
        self.assertFalse(abbreviations.write_abbreviations(self.data).changed)


class TestTable(unittest.TestCase):
    def test_entries_are_lowercase_words(self):
        for short, full in abbreviations.ABBREVIATIONS.items():
            self.assertEqual((to_slug(short).replace("-", " "), to_slug(full).replace("-", " ")), (short, full))


if __name__ == "__main__":
    unittest.main()
