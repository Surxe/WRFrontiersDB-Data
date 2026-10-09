// The JavaScript build-code codec against the same vectors as tests/test_build_code.py.
//
// Run: node --test 'tests/js/*.test.mjs'

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import * as buildCode from '../../tools/js/build_code.js';

const root = new URL('../../', import.meta.url);
const load = (rel) => JSON.parse(readFileSync(new URL(rel, root), 'utf8'));

const suites = {
  real: ['index/build_codes.json', 'index/build_code_vectors.json'],
  synthetic: [
    'tests/fixtures/build_codes/registry.json',
    'tests/fixtures/build_codes/vectors.json',
  ],
};

for (const [suite, [registryPath, vectorsPath]] of Object.entries(suites)) {
  const codec = new buildCode.BuildCodec(load(registryPath));
  const vectors = load(vectorsPath);

  test(`${suite}: vectors encode and decode`, () => {
    assert.ok(vectors.vectors.length > 0);
    for (const v of vectors.vectors) {
      assert.equal(codec.encode(v.build), v.code, v.name ?? v.code);
      assert.deepEqual(codec.decode(v.code), v.build, v.name ?? v.code);
    }
  });

  test(`${suite}: encode errors`, () => {
    for (const v of vectors.encode_errors) {
      assert.throws(() => codec.encode(v.build), buildCode[v.error], v.name);
      assert.equal(codec.canEncode(v.build), false, v.name);
    }
  });

  test(`${suite}: decode errors`, () => {
    for (const v of vectors.decode_errors) {
      assert.throws(
        () => codec.decode(v.code),
        (err) => err instanceof buildCode.BuildCodeError && err.name === v.error,
        v.name ?? v.code
      );
    }
  });
}

test('every position round-trips through the characters', () => {
  const positions = Array.from({ length: buildCode.END }, (_, i) => i);
  const code = positions.map(buildCode.positionToChars).join('');
  assert.deepEqual(buildCode.codeToPositions(code), positions);
  assert.throws(() => buildCode.positionToChars(buildCode.END), buildCode.BuildCodeError);
});

test('slot keys match the Site', () => {
  assert.equal(buildCode.slotKey([]), 'chassis');
  assert.equal(buildCode.slotKey(['Root']), 'torso');
  assert.equal(buildCode.slotKey(['Root', 'Shoulder_L']), 'Shoulder_L');
  assert.equal(
    buildCode.slotKey(['Root', 'Shoulder_L', 'Shoulder_Weapon_0']),
    'Shoulder_L.Shoulder_Weapon_0'
  );
});
