"""Build codes: a robot build <-> a short string, for `/models?a=<code>` links.

The reference codec. `tools/js/build_code.js` is the same codec for JavaScript and
must stay line-for-line equivalent; both are tested against the same vectors.
The format is specified in `docs/build-codes.md`.

A build is `{slot key: Module id}` for every filled slot of a resolved build
(defaults filled in), keyed like the Site's slot keys: `chassis`, `torso`,
`Shoulder_L`, `Shoulder_L.Shoulder_Weapon_0`, ... Walking the slot tree depth
first from the chassis, each slot writes one position:

* the chosen module's position in that socket type's candidate list in
  `index/build_codes.json`; an optional slot reserves position 0 for "empty",
  so its modules start at 1;
* positions 0-61 are one character (`0-9A-Za-z`), 62-125 are `-` plus one
  character, 126-4221 are `_` plus two characters (any of the 64 symbols
  `0-9A-Za-z-_` after a marker).

Trailing empty optional slots are dropped, so reading past the end of a code
means "empty"; required slots are always written. The lists are append-only
(`build_codes.py`), so a code never changes meaning: a code made with newer data
than the decoder has points past the end of a list and raises `TooNew`.
"""

from __future__ import annotations

DIRECT = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
"""The 62 one-character positions."""
FULL = DIRECT + "-_"
"""The 64 symbols allowed after a width marker."""
TIER2_MARKER, TIER3_MARKER = "-", "_"
TIER2, TIER3, END = 62, 62 + 64, 62 + 64 + 64 * 64
"""First position of the two- and three-character tiers, and one past the last."""

CHASSIS_KEY = "chassis"
TORSO_KEY = "torso"
TORSO_SOCKET = "Root"
"""The chassis socket holding the torso; implied in slot keys (`Shoulder_L`, not `Root.Shoulder_L`)."""

Build = dict[str, str]


class BuildCodeError(ValueError):
    """A build that can't be encoded, or a string that isn't a build code."""


class TooNew(BuildCodeError):
    """The code uses a module this copy of the data doesn't have yet."""


def slot_key(path: tuple[str, ...]) -> str:
    """Slot key for a socket path from the chassis (the Site's `slotKeyForPath`)."""
    if not path:
        return CHASSIS_KEY
    if path[0] == TORSO_SOCKET:
        return TORSO_KEY if len(path) == 1 else ".".join(path[1:])
    return ".".join(path)


def position_to_chars(position: int) -> str:
    if position < 0:
        raise BuildCodeError(f"negative position {position}")
    if position < TIER2:
        return DIRECT[position]
    if position < TIER3:
        return TIER2_MARKER + FULL[position - TIER2]
    if position < END:
        rest = position - TIER3
        return TIER3_MARKER + FULL[rest // 64] + FULL[rest % 64]
    raise BuildCodeError(f"position {position} is past the last three-character position ({END - 1})")


def code_to_positions(code: str) -> list[int]:
    positions, i = [], 0
    try:
        while i < len(code):
            char = code[i]
            if char == TIER2_MARKER:
                positions.append(TIER2 + _full_index(code[i + 1]))
                i += 2
            elif char == TIER3_MARKER:
                positions.append(TIER3 + _full_index(code[i + 1]) * 64 + _full_index(code[i + 2]))
                i += 3
            else:
                positions.append(_direct_index(char))
                i += 1
    except IndexError:
        raise BuildCodeError(f"build code {code!r} ends inside a position") from None
    return positions


def _direct_index(char: str) -> int:
    index = DIRECT.find(char)
    if index < 0:
        raise BuildCodeError(f"invalid build code character {char!r}")
    return index


def _full_index(char: str) -> int:
    index = FULL.find(char)
    if index < 0:
        raise BuildCodeError(f"invalid build code character {char!r}")
    return index


class BuildCodec:
    """Encode and decode builds against one `index/build_codes.json` document."""

    def __init__(self, doc: dict):
        self.root = doc["root_socket"]
        self.sockets: dict[str, dict] = doc["sockets"]
        self.modules: dict[str, dict] = doc["modules"]
        self.positions = {
            socket: {module_id: i for i, module_id in enumerate(st["candidates"])}
            for socket, st in self.sockets.items()
        }

    def can_encode(self, build: Build) -> bool:
        try:
            self.encode(build)
        except BuildCodeError:
            return False
        return True

    def encode(self, build: Build) -> str:
        """The code for a resolved build. Raises BuildCodeError if it can't be encoded."""
        positions: list[int] = []
        required: list[bool] = []
        visited: set[str] = set()

        def walk(socket: str, path: tuple[str, ...]) -> None:
            key = slot_key(path)
            st = self.sockets[socket]
            module_id = build.get(key)
            visited.add(key)
            required.append(st["required"])
            if module_id is None:
                if st["required"]:
                    raise BuildCodeError(f"required slot {key} is empty; resolve the build before encoding")
                positions.append(0)
                return
            position = self.positions[socket].get(module_id)
            if position is None:
                raise BuildCodeError(f"{module_id} is not a build-code option for slot {key}")
            positions.append(position + (0 if st["required"] else 1))
            for name, sub in self.modules[module_id]["sockets"]:
                walk(sub, path + (name,))

        walk(self.root, ())
        stray = sorted(set(build) - visited)
        if stray:
            raise BuildCodeError(f"slots not in the build's tree: {', '.join(stray)}")
        while positions and positions[-1] == 0 and not required[len(positions) - 1]:
            positions.pop()
        return "".join(position_to_chars(p) for p in positions)

    def decode(self, code: str) -> Build:
        """The build a code stands for. Raises TooNew or BuildCodeError."""
        positions = code_to_positions(code)
        build: Build = {}
        cursor = 0

        def walk(socket: str, path: tuple[str, ...]) -> None:
            nonlocal cursor
            key = slot_key(path)
            st = self.sockets[socket]
            if cursor < len(positions):
                position = positions[cursor]
                cursor += 1
            elif st["required"]:
                raise BuildCodeError(f"build code {code!r} ends before required slot {key}")
            else:
                return
            if not st["required"]:
                if position == 0:
                    return
                position -= 1
            candidates = st["candidates"]
            if position >= len(candidates):
                raise TooNew(f"build code {code!r} uses a newer option for slot {key} than this data has")
            module_id = candidates[position]
            build[key] = module_id
            for name, sub in self.modules[module_id]["sockets"]:
                walk(sub, path + (name,))

        walk(self.root, ())
        if cursor < len(positions):
            raise BuildCodeError(f"build code {code!r} has characters past the end of the build")
        return build
