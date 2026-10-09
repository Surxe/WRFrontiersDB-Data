# Build codes

A build code is a short string that stands for one robot build: every module in
every slot, from the chassis down to the weapons and gear. The Site's 3D viewer
links to builds with them (`https://wrf-db.info/models?a=<code>`), and the
Discord bot reads them back. A full build is about 11 characters.

Other sites and apps can make and read the same codes: start with
[Using build codes in your app](#using-build-codes-in-your-app). The rest of the
page is the format, for anyone writing or changing a codec. The two codecs are
`tools/wrfdb_data/build_code.py` (the reference) and `tools/js/build_code.js`.
They must agree on every vector in `index/build_code_vectors.json` and
`tests/fixtures/build_codes/vectors.json`.

## Using build codes in your app

A builder on another site can give its builds the same codes the Site uses, so a
build made there opens in the Site's 3D viewer and shows in Discord through the
WRFrontiersDB bot.

### The files

| URL | What |
| --- | --- |
| `https://wrf-db.info/build-code.js` | The codec, an ES module with no dependencies (browser or Node) |
| `https://wrf-db.info/build_codes.json` | The registry the codec reads |

Both come from the same Site deploy, so they always match the data the Site
decodes with. Fetch the registry at runtime rather than bundling a copy: it grows
with every game update, and a stale copy can't encode new modules (GitHub Pages
caches both for 10 minutes). Both are served with
`Access-Control-Allow-Origin: *`.

### JavaScript

```js
import { BuildCodec, BuildCodeError, TooNew } from 'https://wrf-db.info/build-code.js';

const codec = new BuildCodec(await (await fetch('https://wrf-db.info/build_codes.json')).json());

const build = {
  chassis: 'DA_Module_ChassisTyr.2',
  torso: 'DA_Module_TorsoHeike.1',
  Shoulder_L: 'DA_Module_ShoulderScorpion.0',
  'Shoulder_L.Shoulder_Weapon_0': 'DA_Module_Weapon_Scatter.0',
  Shoulder_R: 'DA_Module_ShoulderInquisitor.0',
  Ability: 'DA_Module_Ability_AmmoGenerator.1',
};
const code = codec.encode(build); // 'eDZHG01'
codec.decode(code); // the same build back
codec.canEncode(build); // true; false instead of throwing
```

- **Link to the viewer:** `https://wrf-db.info/models?a=<code>`, or
  `?a=<code>&b=<code>` to compare two builds.
- **Share in Discord:** post that link, or give people the string
  `/wrf-build build:<code>` (`/wrf-build build:<A> <B>` to compare). The bot
  answers with each build's parts.

### Making a build

A build is `{slot key: Module id}` for every filled slot: see
[Slots and slot keys](#slots-and-slot-keys). The registry has everything needed
to build a valid one: start at `root_socket`, pick one of that socket type's
`candidates`, then fill the picked module's `sockets` the same way. A slot whose
socket type is `required` must be filled. Module names, stats and icons are in
this repo's `current/Objects/Module.json` (and the Site's pages, at
`https://wrf-db.info/modules/<slug>/` from `index/slug_map.json`).

### Errors

- `TooNew` (a `BuildCodeError`): the code was made with newer data than your
  registry. Refetch the registry; if it's still too new, the Site hasn't been
  deployed with that data yet.
- `BuildCodeError`: the string isn't a build code, or the build can't be
  encoded (an empty required slot, a module that isn't released or that doesn't
  fit the slot).
- An incompatible registry (a future `format`) is a `BuildCodeError` from the
  constructor.

### Python

Python can't import from a URL, so copy
[`tools/wrfdb_data/build_code.py`](../tools/wrfdb_data/build_code.py) into your
project. It is a single file using only the standard library. Fetch the registry
the same way:

```python
import json
from urllib.request import urlopen

from build_code import BuildCodec, BuildCodeError, TooNew

codec = BuildCodec(json.load(urlopen("https://wrf-db.info/build_codes.json")))
codec.decode("eDZHG01")  # {'chassis': 'DA_Module_ChassisTyr.2', ...}
```

The API is the same in snake_case (`can_encode`, `slot_key`).

### What stays stable

- A code means the same build forever.
- The two URLs stay.
- Registry `format` 1 only ever gains fields; the existing ones keep their
  meaning.
- The stable API keeps its behaviour: `FORMAT`, `BuildCodec` (`encode`,
  `decode`, `canEncode` / `can_encode`), `BuildCodeError`, `TooNew` and
  `slotKey` / `slot_key`. The codecs' other exports are internal.

An incompatible change would be a new `format` under new URLs, while these keep
serving format 1.

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
| `FORMAT` | `FORMAT` |

The constructor raises `BuildCodeError` when the registry's `format` isn't
`FORMAT`.

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
