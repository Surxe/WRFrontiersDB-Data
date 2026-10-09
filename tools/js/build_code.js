/**
 * Build codes: a robot build <-> a short string, for `/models?a=<code>` links.
 *
 * The JavaScript codec. It mirrors `tools/wrfdb_data/build_code.py` (the
 * reference) line for line; both are tested against the same vectors. The
 * format is specified in `docs/build-codes.md`. No dependencies: it runs in
 * Node and in the browser.
 *
 * A build is `{slot key: Module id}` for every filled slot of a resolved build
 * (defaults filled in), keyed like the Site's slot keys: `chassis`, `torso`,
 * `Shoulder_L`, `Shoulder_L.Shoulder_Weapon_0`, ... Walking the slot tree depth
 * first from the chassis, each slot writes one position:
 *
 * - the chosen module's position in that socket type's candidate list in
 *   `index/build_codes.json`; an optional slot reserves position 0 for
 *   "empty", so its modules start at 1;
 * - positions 0-61 are one character (`0-9A-Za-z`), 62-125 are `-` plus one
 *   character, 126-4221 are `_` plus two characters (any of the 64 symbols
 *   `0-9A-Za-z-_` after a marker).
 *
 * Trailing empty optional slots are dropped, so reading past the end of a code
 * means "empty"; required slots are always written. The lists are
 * append-only, so a code never changes meaning: a code made with newer data
 * than the decoder has points past the end of a list and throws `TooNew`.
 */

/**
 * The stable API for apps (`docs/build-codes.md`, "Using build codes in your
 * app") is `FORMAT`, `BuildCodec` (`encode`, `decode`, `canEncode`),
 * `BuildCodeError`, `TooNew` and `slotKey`. The other exports are internal and
 * may change.
 */

/** The `format` of `index/build_codes.json` this codec reads. */
export const FORMAT = 1;

/** The 62 one-character positions. */
export const DIRECT =
  '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
/** The 64 symbols allowed after a width marker. */
export const FULL = DIRECT + '-_';
export const TIER2_MARKER = '-';
export const TIER3_MARKER = '_';
/** First position of the two- and three-character tiers, and one past the last. */
export const TIER2 = 62;
export const TIER3 = 62 + 64;
export const END = 62 + 64 + 64 * 64;

export const CHASSIS_KEY = 'chassis';
export const TORSO_KEY = 'torso';
/** The chassis socket holding the torso; implied in slot keys. */
export const TORSO_SOCKET = 'Root';

/**
 * @typedef {Record<string, string>} Build  slot key -> Module id
 * @typedef {{ required: boolean, candidates: string[] }} SocketEntry
 * @typedef {{ sockets: [string, string][] }} ModuleEntry  [socket name, socket type id]
 * @typedef {{
 *   format: number,
 *   root_socket: string,
 *   sockets: Record<string, SocketEntry>,
 *   modules: Record<string, ModuleEntry>,
 * }} BuildCodesDoc  the contents of `index/build_codes.json`
 */

/** A build that can't be encoded, or a string that isn't a build code. */
export class BuildCodeError extends Error {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = 'BuildCodeError';
  }
}

/** The code uses a module this copy of the data doesn't have yet. */
export class TooNew extends BuildCodeError {
  /** @param {string} message */
  constructor(message) {
    super(message);
    this.name = 'TooNew';
  }
}

/**
 * Slot key for a socket path from the chassis (the Site's `slotKeyForPath`).
 * @param {readonly string[]} path
 * @returns {string}
 */
export function slotKey(path) {
  if (path.length === 0) return CHASSIS_KEY;
  if (path[0] === TORSO_SOCKET) {
    return path.length === 1 ? TORSO_KEY : path.slice(1).join('.');
  }
  return path.join('.');
}

/**
 * @param {number} position
 * @returns {string}
 */
export function positionToChars(position) {
  if (position < 0) throw new BuildCodeError(`negative position ${position}`);
  if (position < TIER2) return DIRECT[position];
  if (position < TIER3) return TIER2_MARKER + FULL[position - TIER2];
  if (position < END) {
    const rest = position - TIER3;
    return TIER3_MARKER + FULL[Math.floor(rest / 64)] + FULL[rest % 64];
  }
  throw new BuildCodeError(
    `position ${position} is past the last three-character position (${END - 1})`
  );
}

/**
 * @param {string} code
 * @returns {number[]}
 */
export function codeToPositions(code) {
  const positions = [];
  let i = 0;
  const at = (/** @type {number} */ j) => {
    if (j >= code.length) {
      throw new BuildCodeError(`build code ${JSON.stringify(code)} ends inside a position`);
    }
    return code[j];
  };
  while (i < code.length) {
    const char = code[i];
    if (char === TIER2_MARKER) {
      positions.push(TIER2 + fullIndex(at(i + 1)));
      i += 2;
    } else if (char === TIER3_MARKER) {
      positions.push(TIER3 + fullIndex(at(i + 1)) * 64 + fullIndex(at(i + 2)));
      i += 3;
    } else {
      positions.push(directIndex(char));
      i += 1;
    }
  }
  return positions;
}

/** @param {string} char */
function directIndex(char) {
  const index = DIRECT.indexOf(char);
  if (index < 0) throw new BuildCodeError(`invalid build code character ${JSON.stringify(char)}`);
  return index;
}

/** @param {string} char */
function fullIndex(char) {
  const index = FULL.indexOf(char);
  if (index < 0) throw new BuildCodeError(`invalid build code character ${JSON.stringify(char)}`);
  return index;
}

/** Encode and decode builds against one `index/build_codes.json` document. */
export class BuildCodec {
  /** @param {BuildCodesDoc} doc */
  constructor(doc) {
    if (doc.format !== FORMAT) {
      throw new BuildCodeError(
        `build codes format ${JSON.stringify(doc.format)} is not ${FORMAT}; use a matching codec`
      );
    }
    this.root = doc.root_socket;
    this.sockets = doc.sockets;
    this.modules = doc.modules;
    /** @type {Map<string, Map<string, number>>} */
    this.positions = new Map(
      Object.entries(doc.sockets).map(([socket, st]) => [
        socket,
        new Map(st.candidates.map((moduleId, i) => [moduleId, i])),
      ])
    );
  }

  /**
   * @param {Build} build
   * @returns {boolean}
   */
  canEncode(build) {
    try {
      this.encode(build);
    } catch (err) {
      if (err instanceof BuildCodeError) return false;
      throw err;
    }
    return true;
  }

  /**
   * The code for a resolved build. Throws BuildCodeError if it can't be encoded.
   * @param {Build} build
   * @returns {string}
   */
  encode(build) {
    /** @type {number[]} */
    const positions = [];
    /** @type {boolean[]} */
    const required = [];
    /** @type {Set<string>} */
    const visited = new Set();

    /**
     * @param {string} socket
     * @param {string[]} path
     */
    const walk = (socket, path) => {
      const key = slotKey(path);
      const st = this.sockets[socket];
      const moduleId = Object.hasOwn(build, key) ? build[key] : undefined;
      visited.add(key);
      required.push(st.required);
      if (moduleId === undefined) {
        if (st.required) {
          throw new BuildCodeError(
            `required slot ${key} is empty; resolve the build before encoding`
          );
        }
        positions.push(0);
        return;
      }
      const position = this.positions.get(socket)?.get(moduleId);
      if (position === undefined) {
        throw new BuildCodeError(`${moduleId} is not a build-code option for slot ${key}`);
      }
      positions.push(position + (st.required ? 0 : 1));
      for (const [name, sub] of this.modules[moduleId].sockets) {
        walk(sub, [...path, name]);
      }
    };

    walk(this.root, []);
    const stray = Object.keys(build)
      .filter((key) => !visited.has(key))
      .sort();
    if (stray.length > 0) {
      throw new BuildCodeError(`slots not in the build's tree: ${stray.join(', ')}`);
    }
    while (
      positions.length > 0 &&
      positions[positions.length - 1] === 0 &&
      !required[positions.length - 1]
    ) {
      positions.pop();
    }
    return positions.map(positionToChars).join('');
  }

  /**
   * The build a code stands for. Throws TooNew or BuildCodeError.
   * @param {string} code
   * @returns {Build}
   */
  decode(code) {
    const positions = codeToPositions(code);
    /** @type {Build} */
    const build = {};
    let cursor = 0;

    /**
     * @param {string} socket
     * @param {string[]} path
     */
    const walk = (socket, path) => {
      const key = slotKey(path);
      const st = this.sockets[socket];
      let position;
      if (cursor < positions.length) {
        position = positions[cursor];
        cursor += 1;
      } else if (st.required) {
        throw new BuildCodeError(
          `build code ${JSON.stringify(code)} ends before required slot ${key}`
        );
      } else {
        return;
      }
      if (!st.required) {
        if (position === 0) return;
        position -= 1;
      }
      const candidates = st.candidates;
      if (position >= candidates.length) {
        throw new TooNew(
          `build code ${JSON.stringify(code)} uses a newer option for slot ${key} than this data has`
        );
      }
      const moduleId = candidates[position];
      build[key] = moduleId;
      for (const [name, sub] of this.modules[moduleId].sockets) {
        walk(sub, [...path, name]);
      }
    };

    walk(this.root, []);
    if (cursor < positions.length) {
      throw new BuildCodeError(
        `build code ${JSON.stringify(code)} has characters past the end of the build`
      );
    }
    return build;
  }
}
