// Loads the built engine in Node and checks that it answers, without slicing anything:
// version() matches pins.json, and one instance survives running main twice.
//
//   node scripts/smoke.mjs [folder holding CuraEngine.js]   (default: out/engine)

import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const folder = path.resolve(process.argv[2] ?? path.join(root, 'out', 'engine'));
const pins = JSON.parse(await readFile(path.join(root, 'pins.json'), 'utf8'));
const expected = pins.sources.curaengine.tag;

const { default: createEngine } = await import(pathToFileURL(path.join(folder, 'CuraEngine.js')).href);
const engine = await createEngine({ print() {}, printErr() {} });

assert.equal(engine.version(), expected, 'version() does not report the pinned engine version');

// `help` prints usage and calls exit(0). Running it twice proves main and exit leave the instance usable.
for (let run = 1; run <= 2; run += 1) {
  try {
    engine.callMain(['help']);
  } catch (error) {
    if (error?.name !== 'ExitStatus' || error.status !== 0) throw error;
  }
}
assert.equal(engine.version(), expected, 'the instance stopped answering after running main twice');

console.log(`ok: CuraEngine ${expected} loads in Node; one instance ran main twice and still answers`);