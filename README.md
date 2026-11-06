# armada-slicer-engine

Builds [CuraEngine](https://github.com/Ultimaker/CuraEngine) to WebAssembly for the
[Armada printer fleet software](https://github.com/Armada-Printer-Fleet-Management/armada-printer-fleet-management),
from pinned, verified source, in a pinned container. It holds the toolchain and nothing else: every line of
Armada logic, and the explanation of how the engine is used, lives in the main repository
(`docs/slicer-engine.html` there).

Why build it ourselves: trusting a prebuilt `.wasm` would let anyone who could change that file change what
runs in our users' browsers. Here every input is pinned by hash, and every published file is attested to the
workflow run that built it.

## Setup

This repository depends on the main Armada repository: its commit contract, AI use policy and commit hook
live there. Clone both side by side:

```bash
git clone https://github.com/Armada-Printer-Fleet-Management/armada-printer-fleet-management.git
git clone https://github.com/Armada-Printer-Fleet-Management/armada-slicer-engine.git
cd armada-slicer-engine
git config core.hooksPath .githooks
# Only if the main repository is not at ../armada-printer-fleet-management:
git config armada.mainRepo <path to the main repository>
```

Then install Docker, Python 3.13 and Node, and read `AGENTS.md`.

## How a build works

1. `pins.json` names the CuraEngine and Cura tags and a conan-config commit, each with its commit ID and the
   SHA-256 of its GitHub archive. The build checks both, and refuses on any mismatch.
2. `build/Dockerfile` is the only build environment: a base image pinned by digest, and Conan pinned by hash.
3. The engine source gets our embind bindings (`bindings/`) and `patches/`, then Conan builds it and every
   dependency from source with Ultimaker's `cura_wasm` profile, held to the recipe revisions in `conan.lock`.
4. A tag `vX.Y.Z-rN` runs `release.yml`. It builds on a fresh runner, smoke-tests the result, attests every
   file, and publishes the release:
   - `CuraEngine.js`: an ES module with the WASM embedded
   - `CuraEngine.d.ts`
   - the two Cura definitions
   - the licences, `NOTICE.txt`, `BUILDINFO.json` and `SHA256SUMS`

Pull requests build and smoke-test only.

## Commands

Docker is required for `lock` and `build`; the script builds the container and runs itself inside it.

| Task | Command |
| --- | --- |
| Check the pinned sources only | `python scripts/build.py verify` |
| Build into `out/engine/` | `python scripts/build.py build [--jobs N]` |
| Smoke test the build | `node scripts/smoke.mjs` |
| Assemble release assets into `dist/` | `python scripts/package.py --repository OWNER/REPO --ref REF` |
| Regenerate `conan.lock` | `python scripts/build.py lock` |
| Check a published asset | `gh attestation verify CuraEngine.js --repo Armada-Printer-Fleet-Management/armada-slicer-engine` |

Docker needs about 8 GiB of memory at the default `--jobs 4`. A first build takes about 35 minutes.

## Upgrading the engine

1. Set the new tag, commit and archive SHA-256 for `curaengine` and `cura` in `pins.json`.
2. `python scripts/build.py build`. If a patch no longer applies, rebase it against the new source.
3. `python scripts/build.py lock`, and review the lock's diff: every changed recipe is a changed input.
4. Build and run `node scripts/smoke.mjs`, then open a pull request.
5. After merging, tag `vX.Y.Z-r1` (increase `rN` for a rebuild of the same engine version).
6. In the main repository, pin the new release's SHA-256s.

## Licences

CuraEngine is AGPL-3.0, and so is this repository (`LICENSE`). Cura's definition files are LGPL-3.0. Each
release carries both licences and a `NOTICE.txt` pointing to the exact source it was built from.

---

## AI Use Statement

This project uses AI coding assistants under the main Armada repository's written policy,
[`.integrity/POLICY.md`](https://github.com/Armada-Printer-Fleet-Management/armada-printer-fleet-management/blob/main/.integrity/POLICY.md),
which governs this repository too.

- **Tool:** Claude Code, GitHub Copilot CLI, and locally-run open-source models.
- **Mode:** Local.
- **Output:** the build container, pins, Conan lock, patches, embind bindings, the build, package and smoke
  scripts, CI workflows and documentation.
- **Data:** none. No sponsor or personal data is placed in prompts. Hosted tooling here is consumer-tier, so
  prompts sent to it are treated as leaving the organisation permanently.
- **Verified:** _[each developer records their own verification per commit; see the AI Use Statement in
  individual commit messages]_

Each commit produced with agent assistance carries its own statement naming the tool, model, mode, what was
generated, and how the developer checked it. Developers remain the authors of what they commit and are
accountable for understanding it.

## Reference

> _Policy on the Use of Generative AI._ ENEL 500 — Computer, Electrical, and Software
> Engineering Team Design, Fall 2026. Department of Software and Electrical Engineering,
> University of Calgary. Hamidreza Zareipour. Accessed via D2L.
