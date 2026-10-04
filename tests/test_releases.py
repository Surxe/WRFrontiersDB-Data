"""Roster diffing into ref-keyed release dates, and fill-only patch manifest merges.

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

from wrfdb_data import releases  # noqa: E402
from wrfdb_data.paths import OBJECTS_REL, PATCHES_REL, RELEASE_DATES_REL, DataRepoError  # noqa: E402

REF = releases.virtual_bot_ref


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


class DataRepoCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write_roster(self, bots: dict[str, str]) -> None:
        _write(self.data / (OBJECTS_REL / "VirtualBot.json"), {
            bot_id: {"id": bot_id, "name": {"en": bot_id.title()}, "character_type": kind}
            for bot_id, kind in bots.items()
        })

    def write_curated(self, robots: dict, titans: dict | None = None) -> None:
        _write(self.data / RELEASE_DATES_REL,
               {"_meta": {}, "robots": robots, "titans": titans or {}})

    def curated(self) -> dict:
        return json.loads((self.data / RELEASE_DATES_REL).read_text(encoding="utf-8"))

    def patches(self) -> dict:
        return json.loads((self.data / PATCHES_REL).read_text(encoding="utf-8"))["patches"]


class TestRecordReleases(DataRepoCase):
    def test_new_bots_keyed_by_ref_and_split_by_type(self):
        self.write_roster({"ares": "Mech", "wyrm": "Mech", "norna": "Titan"})
        self.write_curated({REF("ares"): {"name": "Ares", "release_date": None}})

        result = releases.record_releases(self.data, "2026-10-06", "123")

        self.assertEqual({b["id"] for b in result.new_bots}, {"wyrm", "norna"})
        doc = self.curated()
        self.assertEqual(doc["robots"][REF("wyrm")]["release_date"], "2026-10-06")
        self.assertEqual(doc["robots"][REF("wyrm")]["manifest_id"], "123")
        self.assertNotIn("virtual_bot_ref", doc["robots"][REF("wyrm")])
        self.assertIn(REF("norna"), doc["titans"])
        self.assertEqual(doc["_meta"]["robot_count"], 2)

    def test_recorded_roster_is_a_no_op(self):
        self.write_roster({"ares": "Mech"})
        self.write_curated({REF("ares"): {"name": "Ares", "release_date": None}})
        before = (self.data / RELEASE_DATES_REL).read_text(encoding="utf-8")

        result = releases.record_releases(self.data, "2026-10-06", "123")

        self.assertFalse(result.changed)
        self.assertEqual((self.data / RELEASE_DATES_REL).read_text(encoding="utf-8"), before)

    def test_pending_roster_entry_is_settled_fill_only(self):
        self.write_roster({"angler": "Mech"})
        self.write_curated({REF("angler"): {
            "name": "Angler", "release_date": "2026-09-15", "manifest_id": None,
            "pending_roster": True,
        }})

        result = releases.record_releases(self.data, "2026-09-29", "999")

        entry = self.curated()["robots"][REF("angler")]
        self.assertEqual(entry["release_date"], "2026-09-15")  # hand-curated, kept
        self.assertEqual(entry["manifest_id"], "999")
        self.assertNotIn("pending_roster", entry)
        self.assertEqual(result.backfilled[0]["filled"], {"manifest_id": "999"})
        self.assertEqual(result.new_bots, [])

    def test_pending_entry_not_in_roster_is_not_orphaned(self):
        self.write_roster({"ares": "Mech"})
        self.write_curated({
            REF("ares"): {"name": "Ares"},
            REF("angler"): {"name": "Angler", "pending_roster": True},
            REF("gone"): {"name": "Gone"},
        })

        result = releases.record_releases(self.data, "2026-10-06", None, write=False)

        self.assertEqual(result.orphaned_refs, [REF("gone")])

    def test_legacy_array_file_is_rejected(self):
        self.write_roster({"ares": "Mech"})
        _write(self.data / RELEASE_DATES_REL, {"robots": [], "titans": []})
        with self.assertRaises(DataRepoError):
            releases.record_releases(self.data, "2026-10-06", None)


class TestRecordPatchManifests(DataRepoCase):
    def setUp(self):
        super().setUp()
        _write(self.data / PATCHES_REL, {"_meta": {}, "patches": {
            "222": {"version": "2026-09-29", "buildid": None, "patch_released_at_utc": None},
        }})

    def test_adds_new_and_fills_null_sorted_by_version(self):
        result = releases.record_patch_manifests(self.data, {
            "333": {"version": "2026-10-06"},
            "111": {"version": "2026-09-15", "buildid": "7"},
            "222": {"version": "2026-09-29", "buildid": "8",
                    "patch_released_at_utc": "2026-09-29T07:12:15Z"},
        })

        self.assertEqual(sorted(result.added), ["111", "333"])
        self.assertEqual(result.filled, ["222"])
        patches = self.patches()
        self.assertEqual(list(patches), ["111", "222", "333"])
        self.assertEqual(patches["222"]["buildid"], "8")
        self.assertEqual(patches["333"], {"version": "2026-10-06", "buildid": None,
                                          "patch_released_at_utc": None})

    def test_conflicting_value_keeps_recorded(self):
        result = releases.record_patch_manifests(self.data, {"222": {"version": "2026-09-30"}})

        self.assertFalse(result.changed)
        self.assertEqual(result.conflicts, [("222", "version", "2026-09-29", "2026-09-30")])
        self.assertEqual(self.patches()["222"]["version"], "2026-09-29")


if __name__ == "__main__":
    unittest.main()
