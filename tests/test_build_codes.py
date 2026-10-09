"""The build-code registry: first build, append-only updates, and the changes that break codes.

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

from wrfdb_data import build_codes  # noqa: E402
from wrfdb_data.build_code import BuildCodec  # noqa: E402
from wrfdb_data.paths import BUILD_CODE_VECTORS_REL, BUILD_CODES_REL, OBJECTS_REL  # noqa: E402


def ref(cls: str, object_id: str) -> str:
    return f"OBJID_{cls}::{object_id}"


def module(type_id: str, sockets=(), status: str = "Ready") -> dict:
    return {
        "module_type_ref": ref("ModuleType", type_id),
        "production_status": status,
        "sockets": [{"name": name, "socket_type_ref": ref("ModuleSocketType", st)} for name, st in sockets],
    }


def socket_type(accepts: list[str], required: bool) -> dict:
    return {"required": required, "compatible_module_types_refs": [ref("ModuleType", t) for t in accepts]}


TORSO_SOCKETS = [("Shoulder_L", "SL"), ("Ability", "AB")]


def game() -> dict:
    """A small robot: chassis -> torso -> left shoulder (+ weapon) and optional gear."""
    return {
        "ModuleType": {
            "Chassis": {"is_root_module": True}, "Torso": {}, "Shoulder": {}, "Weapon": {}, "Ability": {},
        },
        "ModuleSocketType": {
            "TS": socket_type(["Torso"], True),
            "SL": socket_type(["Shoulder"], True),
            "W": socket_type(["Weapon"], False),
            "AB": socket_type(["Ability"], False),
        },
        "Module": {
            "C2": module("Chassis", [("Root", "TS")]),
            "C1": module("Chassis", [("Root", "TS")]),
            "T1": module("Torso", TORSO_SOCKETS),
            "S1": module("Shoulder", [("Shoulder_Weapon_0", "W")]),
            "W2": module("Weapon"),
            "W1": module("Weapon"),
            "A1": module("Ability"),
            "Wx": module("Weapon", status="Hidden"),
        },
    }


class BuildCodesCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.game = game()

    def write_game(self) -> None:
        for object_type, objects in self.game.items():
            path = self.data / OBJECTS_REL / f"{object_type}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(objects), encoding="utf-8")

    def run_tool(self) -> build_codes.BuildCodesResult:
        self.write_game()
        return build_codes.write_build_codes(self.data)

    def registry(self) -> dict:
        return json.loads((self.data / BUILD_CODES_REL).read_text(encoding="utf-8"))

    def candidates(self, socket: str) -> list[str]:
        return self.registry()["sockets"][socket]["candidates"]

    # --- first run ------------------------------------------------------------

    def test_bootstrap_sorts_released_modules_by_id(self):
        result = self.run_tool()
        self.assertEqual(result.errors, [])
        self.assertTrue(result.changed)
        self.assertEqual(self.candidates("chassis"), ["C1", "C2"])
        self.assertEqual(self.candidates("W"), ["W1", "W2"])
        self.assertNotIn("Wx", self.registry()["modules"])  # unreleased
        self.assertEqual(self.registry()["sockets"]["W"]["required"], False)
        self.assertTrue((self.data / BUILD_CODE_VECTORS_REL).exists())

    def test_vectors_round_trip(self):
        self.run_tool()
        codec = BuildCodec(self.registry())
        vectors = json.loads((self.data / BUILD_CODE_VECTORS_REL).read_text(encoding="utf-8"))
        for v in vectors["vectors"]:
            self.assertEqual(codec.decode(v["code"]), v["build"])

    def test_rerun_changes_nothing(self):
        self.run_tool()
        result = self.run_tool()
        self.assertEqual((result.errors, result.appended, result.changed), ([], [], False))

    # --- appended -------------------------------------------------------------

    def test_released_module_is_appended(self):
        self.run_tool()
        codes_before = BuildCodec(self.registry()).encode(
            {"chassis": "C2", "torso": "T1", "Shoulder_L": "S1", "Shoulder_L.Shoulder_Weapon_0": "W2"})
        self.game["Module"]["W0"] = module("Weapon")
        self.game["Module"]["Wx"]["production_status"] = "Ready"
        result = self.run_tool()
        self.assertEqual(result.errors, [])
        self.assertEqual(self.candidates("W"), ["W1", "W2", "W0", "Wx"])
        self.assertIn("module W0", result.appended)
        codes_after = BuildCodec(self.registry()).encode(
            {"chassis": "C2", "torso": "T1", "Shoulder_L": "S1", "Shoulder_L.Shoulder_Weapon_0": "W2"})
        self.assertEqual(codes_before, codes_after)

    def test_new_fit_is_appended(self):
        self.run_tool()
        self.game["ModuleSocketType"]["AB"]["compatible_module_types_refs"].append(ref("ModuleType", "Weapon"))
        result = self.run_tool()
        self.assertEqual(result.errors, [])
        self.assertEqual(self.candidates("AB"), ["A1", "W1", "W2"])

    def test_new_optional_socket_is_appended_to_the_module(self):
        self.run_tool()
        self.game["Module"]["T1"] = module("Torso", [("Torso_Weapon_0", "W")] + TORSO_SOCKETS)
        result = self.run_tool()
        self.assertEqual(result.errors, [])
        self.assertEqual(self.registry()["modules"]["T1"]["sockets"],
                         [["Shoulder_L", "SL"], ["Ability", "AB"], ["Torso_Weapon_0", "W"]])

    def test_socket_reorder_is_ignored(self):
        self.run_tool()
        self.game["Module"]["T1"] = module("Torso", list(reversed(TORSO_SOCKETS)))
        result = self.run_tool()
        self.assertEqual((result.errors, result.changed), ([], False))
        self.assertEqual(self.registry()["modules"]["T1"]["sockets"], [["Shoulder_L", "SL"], ["Ability", "AB"]])

    # --- errors: nothing written ------------------------------------------------

    def assert_breaks(self, fragment: str) -> None:
        before = self.registry()
        result = self.run_tool()
        self.assertTrue(any(fragment in e for e in result.errors), result.errors)
        self.assertFalse(result.changed)
        self.assertEqual(self.registry(), before)

    def test_new_required_socket_is_an_error(self):
        self.run_tool()
        self.game["Module"]["T1"] = module("Torso", TORSO_SOCKETS + [("Shoulder_R", "SL")])
        self.assert_breaks("gained a required socket")

    def test_lost_socket_is_an_error(self):
        self.run_tool()
        self.game["Module"]["T1"] = module("Torso", TORSO_SOCKETS[:1])
        self.assert_breaks("lost its Ability socket")

    def test_socket_type_change_is_an_error(self):
        self.run_tool()
        self.game["Module"]["T1"] = module("Torso", [("Shoulder_L", "SL"), ("Ability", "W")])
        self.assert_breaks("changed type")

    def test_lost_fit_is_an_error(self):
        self.run_tool()
        self.game["Module"]["W1"]["module_type_ref"] = ref("ModuleType", "Ability")
        self.assert_breaks("W1 no longer fits W")

    def test_removed_module_is_an_error(self):
        self.run_tool()
        del self.game["Module"]["W1"]
        self.assert_breaks("no longer in the data")

    def test_required_flag_change_is_an_error(self):
        self.run_tool()
        self.game["ModuleSocketType"]["W"]["required"] = True
        self.assert_breaks("changed required")


if __name__ == "__main__":
    unittest.main()
