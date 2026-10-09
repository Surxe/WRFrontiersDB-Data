"""The build-code codec against the published vectors and the synthetic tier fixture.

`tests/js/build_code.test.mjs` runs the same vectors through the JavaScript codec.

Run: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "tools"))

from wrfdb_data import build_code  # noqa: E402
from wrfdb_data.build_code import BuildCodec  # noqa: E402
from wrfdb_data.paths import BUILD_CODE_VECTORS_REL, BUILD_CODES_REL  # noqa: E402

FIXTURE_DIR = ROOT_DIR / "tests" / "fixtures" / "build_codes"
SUITES = {
    "real": (ROOT_DIR / BUILD_CODES_REL, ROOT_DIR / BUILD_CODE_VECTORS_REL),
    "synthetic": (FIXTURE_DIR / "registry.json", FIXTURE_DIR / "vectors.json"),
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class VectorsCase(unittest.TestCase):
    def test_vectors(self):
        for suite, (registry_path, vectors_path) in SUITES.items():
            codec = BuildCodec(load(registry_path))
            vectors = load(vectors_path)
            self.assertTrue(vectors["vectors"], suite)
            for v in vectors["vectors"]:
                with self.subTest(suite=suite, code=v["code"]):
                    self.assertEqual(codec.encode(v["build"]), v["code"])
                    self.assertEqual(codec.decode(v["code"]), v["build"])
            for v in vectors["encode_errors"]:
                with self.subTest(suite=suite, encode_error=v.get("name")):
                    with self.assertRaises(getattr(build_code, v["error"])):
                        codec.encode(v["build"])
                    self.assertFalse(codec.can_encode(v["build"]))
            for v in vectors["decode_errors"]:
                with self.subTest(suite=suite, decode_error=v.get("name")):
                    with self.assertRaises(build_code.BuildCodeError) as caught:
                        codec.decode(v["code"])
                    self.assertEqual(type(caught.exception).__name__, v["error"])


class PublicApiCase(unittest.TestCase):
    """docs/build-codes.md promises these names to apps; removing one is a breaking change."""

    def test_stable_names(self):
        self.assertEqual(set(build_code.__all__), {"FORMAT", "Build", "BuildCodec", "BuildCodeError", "TooNew", "slot_key"})
        for name in build_code.__all__:
            self.assertTrue(hasattr(build_code, name), name)
        for method in ("encode", "decode", "can_encode"):
            self.assertTrue(callable(getattr(BuildCodec, method)), method)
        self.assertTrue(issubclass(build_code.TooNew, build_code.BuildCodeError))

    def test_rejects_another_format(self):
        doc = load(ROOT_DIR / BUILD_CODES_REL)
        self.assertEqual(doc["format"], build_code.FORMAT)
        for other in (build_code.FORMAT + 1, None):
            with self.subTest(format=other), self.assertRaises(build_code.BuildCodeError):
                BuildCodec({**doc, "format": other})


class CharactersCase(unittest.TestCase):
    def test_every_position_round_trips(self):
        positions = list(range(build_code.END))
        code = "".join(build_code.position_to_chars(p) for p in positions)
        self.assertEqual(build_code.code_to_positions(code), positions)

    def test_tier_widths(self):
        widths = {0: 1, 61: 1, 62: 2, 125: 2, 126: 3, build_code.END - 1: 3}
        for position, width in widths.items():
            self.assertEqual(len(build_code.position_to_chars(position)), width, position)

    def test_past_the_last_position(self):
        with self.assertRaises(build_code.BuildCodeError):
            build_code.position_to_chars(build_code.END)


class SlotKeyCase(unittest.TestCase):
    def test_matches_the_site(self):
        self.assertEqual(build_code.slot_key(()), "chassis")
        self.assertEqual(build_code.slot_key(("Root",)), "torso")
        self.assertEqual(build_code.slot_key(("Root", "Shoulder_L")), "Shoulder_L")
        self.assertEqual(build_code.slot_key(("Root", "Shoulder_L", "Shoulder_Weapon_0")),
                         "Shoulder_L.Shoulder_Weapon_0")


if __name__ == "__main__":
    unittest.main()
