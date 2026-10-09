"""Write the synthetic build-code fixture: `registry.json` + `vectors.json`.

Real data won't reach the two- and three-character tiers for years, so this
registry pads every list far enough to: a chassis list of 4223 (positions up to
4222, one past the last encodable one) and 200-long torso, shoulder, weapon and
gear lists. The vectors cover each tier boundary, full builds entirely in the
two- and three-character tiers (the 33-character worst case), interleaved tiers,
a long last slot followed by dropped empty slots, and the encode / decode errors.
Every codec's tests run these next to the real `index/build_code_vectors.json`.

Run from the repo root after changing the codec or this file:
    python3 tests/fixtures/build_codes/make_synthetic.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "tools"))

from wrfdb_data.build_code import BuildCodec, BuildCodeError  # noqa: E402

CHASSIS_COUNT = 4223
LIST_COUNT = 200
SOCKETED_CHASSIS = (5, 70, 200)
"""Chassis positions that hold a torso; the others have no sockets."""
TORSO_SOCKETS = [["Shoulder_L", "ShoulderL"], ["Shoulder_R", "ShoulderR"], ["Ability", "Ability"],
                 ["UltAbility", "Ult"], ["Torso_Weapon_0", "Weapon"]]
SHOULDER_SOCKETS = [["Shoulder_Weapon_0", "Weapon"], ["Shoulder_Weapon_1", "Weapon"]]


def ids(prefix: str, count: int) -> list[str]:
    width = len(str(count - 1))
    return [f"{prefix}{i:0{width}d}" for i in range(count)]


def registry() -> dict:
    chassis, torsos, shoulders = ids("C", CHASSIS_COUNT), ids("T", LIST_COUNT), ids("S", LIST_COUNT)
    weapons, abilities, ults = ids("W", LIST_COUNT), ids("A", LIST_COUNT), ids("U", LIST_COUNT)
    modules = {}
    for i, c in enumerate(chassis):
        modules[c] = {"sockets": [["Root", "Torso"]] if i in SOCKETED_CHASSIS else []}
    modules.update({t: {"sockets": TORSO_SOCKETS} for t in torsos})
    modules.update({s: {"sockets": SHOULDER_SOCKETS} for s in shoulders})
    modules.update({m: {"sockets": []} for m in weapons + abilities + ults})
    required = lambda candidates: {"required": True, "candidates": candidates}  # noqa: E731
    optional = lambda candidates: {"required": False, "candidates": candidates}  # noqa: E731
    return {
        "format": 1,
        "root_socket": "chassis",
        "sockets": {
            "chassis": required(chassis), "Torso": required(torsos),
            "ShoulderL": required(shoulders), "ShoulderR": required(shoulders),
            "Weapon": optional(weapons), "Ability": optional(abilities), "Ult": optional(ults),
        },
        "modules": modules,
    }


def full(chassis: int, torso: int, sl: int, slw: tuple, sr: int, srw: tuple,
         ability: int | None, ult: int | None, tw: int | None) -> dict:
    """A full build from list indexes (None = empty optional slot)."""
    build = {"chassis": f"C{chassis:04d}", "torso": f"T{torso:03d}",
             "Shoulder_L": f"S{sl:03d}", "Shoulder_R": f"S{sr:03d}"}
    for side, weapons in (("Shoulder_L", slw), ("Shoulder_R", srw)):
        for slot, w in enumerate(weapons):
            if w is not None:
                build[f"{side}.Shoulder_Weapon_{slot}"] = f"W{w:03d}"
    for key, prefix, value in (("Ability", "A", ability), ("UltAbility", "U", ult), ("Torso_Weapon_0", "W", tw)):
        if value is not None:
            build[key] = f"{prefix}{value:03d}"
    return build


# (name, build, expected code or None to take the codec's). Optional slots: index i is position i + 1.
CASES = [
    ("tier 1 first", {"chassis": "C0000"}, "0"),
    ("tier 1 last", {"chassis": "C0061"}, "z"),
    ("tier 2 first", {"chassis": "C0062"}, "-0"),
    ("tier 2 last", {"chassis": "C0125"}, "-_"),
    ("tier 3 first", {"chassis": "C0126"}, "_00"),
    ("tier 3 last", {"chassis": "C4221"}, "___"),
    ("optional slot boundaries", full(5, 0, 0, (60, 61), 0, (124, 125), None, None, None), None),
    ("all two-character", full(70, 62, 63, (61, 100), 125, (124, 70), 80, 90, 110), None),
    ("all three-character", full(200, 126, 150, (125, 199), 199, (130, 140), 150, 160, 199), None),
    ("interleaved tiers", full(5, 70, 3, (150, None), 199, (0, 61), 9, 130, 62), None),
    ("long last slot, empties dropped", full(70, 0, 0, (None, None), 0, (None, None), 140, None, None), None),
    ("empty slots mid-code", full(5, 1, 2, (None, 3), 4, (None, None), None, 5, None), None),
]

ENCODE_ERRORS = [
    ("past the last position", {"chassis": "C4222"}),
    ("required slot empty", {"chassis": "C0005"}),
    ("module not in the slot's list", {"chassis": "C0005", "torso": "W000", "Shoulder_L": "S000", "Shoulder_R": "S000"}),
    ("slot outside the tree", {"chassis": "C0000", "torso": "T000"}),
]

DECODE_ERRORS = [
    ("too new: weapon past its list", "500_1B", "TooNew"),
    ("ends before a required slot", "5", "BuildCodeError"),
    ("characters past the end", "00", "BuildCodeError"),
    ("ends inside a two-character position", "-", "BuildCodeError"),
    ("ends inside a three-character position", "_0", "BuildCodeError"),
    ("invalid character", "*", "BuildCodeError"),
]


def vectors(reg: dict) -> dict:
    codec = BuildCodec(reg)
    out = {"vectors": [], "encode_errors": [], "decode_errors": []}
    for name, build, expected in CASES:
        code = codec.encode(build)
        if expected is not None and code != expected:
            raise AssertionError(f"{name}: {code!r} != {expected!r}")
        if codec.decode(code) != build:
            raise AssertionError(f"{name}: round-trip failed")
        out["vectors"].append({"name": name, "code": code, "build": build})
    for name, build in ENCODE_ERRORS:
        try:
            codec.encode(build)
        except BuildCodeError:
            out["encode_errors"].append({"name": name, "build": build, "error": "BuildCodeError"})
            continue
        raise AssertionError(f"{name}: encoded without an error")
    for name, code, error in DECODE_ERRORS:
        try:
            codec.decode(code)
        except BuildCodeError as exc:
            if type(exc).__name__ != error:
                raise AssertionError(f"{name}: {type(exc).__name__} != {error}") from exc
            out["decode_errors"].append({"name": name, "code": code, "error": error})
            continue
        raise AssertionError(f"{name}: decoded without an error")
    return out


def main() -> None:
    reg = registry()
    (HERE / "registry.json").write_text(json.dumps(reg, separators=(",", ":")) + "\n", encoding="utf-8")
    (HERE / "vectors.json").write_text(json.dumps(vectors(reg), indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
