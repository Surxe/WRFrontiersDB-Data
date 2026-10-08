# Build codes

A build code is a short string that stands for one robot build: every module in
every slot, from the chassis down to the weapons and gear. The Site's 3D viewer
links to builds with them (`https://wrf-db.info/models?a=<code>`), and the
Discord bot reads them back. A full build is about 11 characters.

This page is the format, for anyone writing or changing a codec. The two codecs
are `tools/wrfdb_data/build_code.py` (the reference) and `tools/js/build_code.js`.
They must agree on every vector in `index/build_code_vectors.json` and
`tests/fixtures/build_codes/vectors.json`.

## The registry: `index/build_codes.json`

```jsonc
{
  "format": 1,
  "root_socket": "chassis",
  "sockets": {
    "chassis": { "required": true, "candidates": ["DA_Module_ChassisAlpha.1", "..."] },
    "DA_ModuleSocketType_Weapon.0": { "required": false, "candidates": ["DA_Module_Weapon_Ares.0", "..."] }
  },
  "modules": {
    "DA_Module_TorsoAres.1": {
      "sockets": [["Shoulder_L", "DA_ModuleSocketType_ShoulderL.0"], ["Ability", "DA_ModuleSocketType_Ability3.0"]]
    }
  }
}
```

- `sockets`: for each socket type (plus the `chassis` pseudo socket for the
  root slot), whether a build must fill it and every released module that fits
  it, in a fixed order.
- `modules`: every released module, with its sockets as `[socket name, socket
  type id]` in a fixed order. A module with no sockets has an empty list.

## Slots and slot keys

A build is a map from slot key to Module id, with every slot of a resolved build
filled: required slots always hold a module (the Site fills a chassis's own parts
first), optional slots may be left out.

The slots are found by walking from the chassis: a filled slot's module's
`sockets` are its child slots, visited in that order, each one's whole subtree
before the next sibling (depth first). A slot's key is its socket-name path from
the chassis, joined with `.`, with the chassis's torso socket (`Root`) implied:

| Path | Key |
| --- | --- |
| (none) | `chassis` |
| `Root` | `torso` |
| `Root`, `Shoulder_L` | `Shoulder_L` |
| `Root`, `Shoulder_L`, `Shoulder_Weapon_0` | `Shoulder_L.Shoulder_Weapon_0` |

These are the Site's slot keys (`slotKeyForPath`).

## Positions

Each slot visited writes one position:

- **Required slot:** the module's index in its socket type's `candidates`.
- **Optional slot:** 0 when empty, otherwise the module's index plus 1.

Positions are written as characters, in three tiers:

| Positions | Written as | Characters |
| --- | --- | --- |
| 0-61 | one of `0-9A-Za-z` (in that order) | 1 |
| 62-125 | `-` then one symbol: 62 + its value | 2 |
| 126-4221 | `_` then two symbols: 126 + 64 x first + second | 3 |

After a marker, a symbol's value is its index in `0-9A-Za-z-_` (64 symbols).
Position 4222 and above can't be written; the encoder raises an error.

Trailing empty optional slots are not written. While decoding, a slot past the
end of the code is empty if it is optional; a required slot past the end is an
error, as are characters left over once the tree is complete.

### Example

A chassis at index 70 (`-8`), its torso at 0, a left shoulder at 0 with two empty
weapon slots, a right shoulder at 0 with two empty weapon slots, supply gear at
index 140 (position 141, `_0F`), and no cycle gear or torso weapon:

```text
-8 0 0 0 0 0 0 0 _0F      ->  -80000000_0F
```

The two empty gear slots at the end are dropped.

## Changes over time

Codes stay valid forever because the registry only grows at the end. The
generator (`tools/wrfdb_data/build_codes.py`, run by the Orchestrator's INDEX
stage) applies these rules on every data update:

| The game data | The registry |
| --- | --- |
| A module is released | Appended to `modules` and to the end of every list it fits |
| A module newly fits a socket type | Appended to the end of that list |
| A module gains an optional socket | Appended to the end of its `sockets` |
| The game reorders a module's sockets | Unchanged; the registry's order wins |
| A module gains a required socket | Error: nothing is written and the INDEX stage fails |
| A module loses a socket, or a socket changes type | Error |
| A module stops fitting a list it is in, or disappears | Error |
| A socket type changes between required and optional | Error |

Unreleased modules are left out until they are released. Several additions in
one run are appended sorted by id; the first registry sorted every list by id.

## Newer codes, older data

A code made with a newer registry than the decoder has points past the end of
one of the decoder's lists. Both codecs raise `TooNew` for this rather than
reading a different build. An older code always decodes with newer data.

## Codec API

Both codecs take the parsed registry and expose the same operations:

| Python (`build_code.py`) | JavaScript (`build_code.js`) |
| --- | --- |
| `BuildCodec(doc).encode(build)` | `new BuildCodec(doc).encode(build)` |
| `.decode(code)` | `.decode(code)` |
| `.can_encode(build)` | `.canEncode(build)` |
| `BuildCodeError`, `TooNew` (a subclass) | the same, as `Error` subclasses |

`encode` raises `BuildCodeError` for a build it can't encode: an empty required
slot, a module that isn't in a slot's list (an unreleased one, or data newer than
the registry), a slot outside the build's tree, or a position past 4221.

## Vectors

- `index/build_code_vectors.json`: seeded random builds over the real registry,
  rewritten with it.
- `tests/fixtures/build_codes/`: a padded synthetic registry that reaches every
  tier (`make_synthetic.py` writes both files): tier boundaries, full builds in
  the two- and three-character tiers (33 characters), mixed tiers, and the error
  cases.

Each vectors file has `vectors` (`code` + `build`, both directions must match),
`encode_errors` (`build` + error class) and `decode_errors` (`code` + error
class).
