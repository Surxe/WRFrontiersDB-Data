"""Build `index/build_codes.json` (the build-code registry) and its test vectors.

The registry holds everything the codecs (`build_code.py`, `tools/js/build_code.js`)
need: each released module's sockets, and for each socket type the modules that
fit it, in a fixed order. A build code is a list of positions in those lists, so
the order is frozen once published: the generator only ever appends.

* First run (no registry yet): every released module, every list sorted by id.
* Later runs compare `current/Objects` against the published registry:
  - a newly released module is appended to the modules and to the list of every
    socket type it fits; a module that newly fits a socket type is appended to
    that list (several at once: by id);
  - a module that gains an optional socket gets it appended to its socket list,
    and the registry keeps its own socket order when the game reorders them;
  - anything that would change what an existing code means is an error and
    nothing is written: a module that disappears, loses a socket, changes a
    socket's type or gains a required socket; a module that stops fitting a
    list it is in; a socket type that changes between required and optional.

`index/build_code_vectors.json` is rewritten with the registry: seeded random
real builds and their codes, which every codec's tests must reproduce.

Console-I/O free: problems come back in the result for the caller to report.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from .build_code import FORMAT, BuildCodec, TooNew, position_to_chars, slot_key
from .paths import BUILD_CODE_VECTORS_REL, BUILD_CODES_REL, DataRepoError, load_json, objects_file, save_json
from .slug_map import ref_to_id

ROOT_SOCKET = "chassis"
"""Pseudo socket type for the root slot: every released chassis."""
READY = "Ready"
VECTOR_COUNT = 200
VECTOR_SEED = 0


@dataclass
class BuildCodesResult:
    registry: dict
    vectors: dict
    appended: list[str] = field(default_factory=list)
    """What this run added, e.g. `module DA_Module_X.0` or `DA_Module_X.0 -> DA_ModuleSocketType_Y.0`."""
    errors: list[str] = field(default_factory=list)
    """Changes that would break published codes; when present nothing is written."""
    changed: bool = False
    """The files on disk were different (or missing) and have been rewritten."""


class _GameData:
    """The parts of `current/Objects` the registry is derived from."""

    def __init__(self, data_dir: Path):
        self.modules = load_json(objects_file(data_dir, "Module"), "Module objects")
        self.module_types = load_json(objects_file(data_dir, "ModuleType"), "ModuleType objects")
        self.socket_types = load_json(objects_file(data_dir, "ModuleSocketType"), "ModuleSocketType objects")
        self.released = sorted(m for m, module in self.modules.items() if module.get("production_status") == READY)
        self._accepted: dict[str, set[str]] = {}

    def type_of(self, module_id: str) -> str | None:
        ref = self.modules.get(module_id, {}).get("module_type_ref")
        return ref_to_id(ref) if ref else None

    def is_root(self, module_id: str) -> bool:
        return self.module_types.get(self.type_of(module_id), {}).get("is_root_module") is True

    def required(self, socket: str) -> bool:
        return socket == ROOT_SOCKET or self.socket_types.get(socket, {}).get("required") is True

    def fits(self, module_id: str, socket: str) -> bool:
        """The Site's rule (`compatibility.ts`): the module's type is accepted by the socket type."""
        if socket == ROOT_SOCKET:
            return self.is_root(module_id)
        if socket not in self._accepted:
            st = self.socket_types.get(socket, {})
            accepted = {ref_to_id(r) for r in st.get("compatible_module_types_refs") or []}
            if st.get("exclusive_module_type_ref"):
                accepted.add(ref_to_id(st["exclusive_module_type_ref"]))
            self._accepted[socket] = accepted
        return self.type_of(module_id) in self._accepted[socket]

    def sockets(self, module_id: str) -> list[list[str]]:
        """[[socket name, socket type id], ...] in the game's order."""
        return [[s["name"], ref_to_id(s["socket_type_ref"])] for s in self.modules[module_id].get("sockets") or []]


def build_build_codes(data_dir: Path) -> BuildCodesResult:
    """Compute the registry from `current/Objects` and the published registry.

    Raises DataRepoError if a file is unreadable.
    """
    game = _GameData(data_dir)
    path = Path(data_dir) / BUILD_CODES_REL
    previous = load_json(path, "build codes") if path.exists() else None
    if previous is None:
        result = _bootstrap(game)
    else:
        if previous.get("format") != FORMAT:
            raise DataRepoError(f"build codes format {previous.get('format')!r} is not {FORMAT}: {path}")
        result = _update(game, previous)
    if not result.errors:
        result.vectors = build_vectors(result.registry)
    return result


def write_build_codes(data_dir: Path) -> BuildCodesResult:
    """Build the registry and vectors, and write them if they changed and nothing broke."""
    result = build_build_codes(data_dir)
    if result.errors:
        return result
    for rel, doc in ((BUILD_CODES_REL, result.registry), (BUILD_CODE_VECTORS_REL, result.vectors)):
        path = Path(data_dir) / rel
        try:
            current = load_json(path, "build codes")
        except DataRepoError:
            current = None
        if current != doc:
            save_json(path, doc)
            result.changed = True
    return result


def _empty_registry() -> dict:
    return {"format": FORMAT, "root_socket": ROOT_SOCKET, "sockets": {}, "modules": {}}


def _bootstrap(game: _GameData) -> BuildCodesResult:
    registry = _empty_registry()
    result = BuildCodesResult(registry=registry, vectors={})
    _add_new(game, registry, result, record=False)
    return result


def _update(game: _GameData, previous: dict) -> BuildCodesResult:
    registry = {
        "format": FORMAT,
        "root_socket": previous["root_socket"],
        "sockets": {k: {"required": v["required"], "candidates": list(v["candidates"])}
                    for k, v in previous["sockets"].items()},
        "modules": {k: {"sockets": [list(s) for s in v["sockets"]]} for k, v in previous["modules"].items()},
    }
    result = BuildCodesResult(registry=registry, vectors={})

    for module_id, entry in registry["modules"].items():
        if module_id not in game.modules:
            result.errors.append(f"{module_id} is in the registry but no longer in the data")
            continue
        game_sockets = dict((name, socket) for name, socket in game.sockets(module_id))
        known = {name for name, _ in entry["sockets"]}
        for name, socket in entry["sockets"]:
            if name not in game_sockets:
                result.errors.append(f"{module_id} lost its {name} socket")
            elif game_sockets[name] != socket:
                result.errors.append(f"{module_id} socket {name} changed type {socket} -> {game_sockets[name]}")
        for name, socket in game.sockets(module_id):
            if name in known:
                continue
            if game.required(socket):
                result.errors.append(f"{module_id} gained a required socket {name} ({socket})")
            else:
                entry["sockets"].append([name, socket])
                result.appended.append(f"{module_id} socket {name}")

    for socket, st in registry["sockets"].items():
        if socket != ROOT_SOCKET and socket not in game.socket_types:
            result.errors.append(f"socket type {socket} is in the registry but no longer in the data")
            continue
        if game.required(socket) != st["required"]:
            result.errors.append(f"socket type {socket} changed required {st['required']} -> {game.required(socket)}")
        for module_id in st["candidates"]:
            if module_id in game.modules and not game.fits(module_id, socket):
                result.errors.append(f"{module_id} no longer fits {socket}")

    if not result.errors:
        _add_new(game, registry, result, record=True)
    return result


def _add_new(game: _GameData, registry: dict, result: BuildCodesResult, *, record: bool) -> None:
    """Append newly released modules, new socket types and new fits (each batch by id)."""
    modules, sockets = registry["modules"], registry["sockets"]
    for module_id in game.released:
        if module_id not in modules:
            modules[module_id] = {"sockets": game.sockets(module_id)}
            if record:
                result.appended.append(f"module {module_id}")

    used = [ROOT_SOCKET] + sorted({socket for entry in modules.values() for _, socket in entry["sockets"]})
    for socket in used:
        if socket not in sockets:
            sockets[socket] = {"required": game.required(socket), "candidates": []}
        listed = set(sockets[socket]["candidates"])
        for module_id in sorted(modules):
            if module_id not in listed and game.fits(module_id, socket):
                sockets[socket]["candidates"].append(module_id)
                if record:
                    result.appended.append(f"{module_id} -> {socket}")

    # Stable key order: root first, then socket types by id; modules keep append order.
    registry["sockets"] = {k: sockets[k] for k in [ROOT_SOCKET] + sorted(k for k in sockets if k != ROOT_SOCKET)}


def build_vectors(registry: dict, count: int = VECTOR_COUNT, seed: int = VECTOR_SEED) -> dict:
    """Seeded random builds over the registry, with their codes, plus one too-new code."""
    codec = BuildCodec(registry)
    rng = random.Random(seed)
    vectors = []
    for _ in range(count):
        build = random_build(registry, rng)
        code = codec.encode(build)
        if codec.decode(code) != build:
            raise AssertionError(f"build code round-trip failed for {build}")
        vectors.append({"code": code, "build": build})
    too_new = _too_new_code(registry)
    return {"vectors": vectors, "encode_errors": [], "decode_errors": [{"code": too_new, "error": TooNew.__name__}]}


def random_build(registry: dict, rng: random.Random) -> dict[str, str]:
    """A random resolved build: every required slot filled, optional slots empty one time in five."""
    build: dict[str, str] = {}

    def walk(socket: str, path: tuple[str, ...]) -> None:
        st = registry["sockets"][socket]
        if not st["candidates"] or (not st["required"] and rng.random() < 0.2):
            return
        module_id = rng.choice(st["candidates"])
        build[slot_key(path)] = module_id
        for name, sub in registry["modules"][module_id]["sockets"]:
            walk(sub, path + (name,))

    walk(registry["root_socket"], ())
    return build


def _too_new_code(registry: dict) -> str:
    """A chassis one past the end of the root list: what a newer registry could produce."""
    return position_to_chars(len(registry["sockets"][registry["root_socket"]]["candidates"]))
