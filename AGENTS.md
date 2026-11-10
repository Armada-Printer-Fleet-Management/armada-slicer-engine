# Agent Instructions

> **Stop. Before doing anything in this repository, read these from the main Armada repository**
> (`Armada-Printer-Fleet-Management/armada-printer-fleet-management`, cloned beside this one; see `README.md`):
>
> - `AGENTS.md`: at least the _Slicer engine_, _Commit contract_, _Branching_ and _Academic integrity_ sections
> - `.integrity/POLICY.md` and `.integrity/AI-USE-STATEMENT.md`
> - `.claude/skills/commit-message/SKILL.md`: compose every commit here with it
>
> **Do not continue until you have read them.** They govern this repository too, and are not repeated here.

This repository builds CuraEngine to WebAssembly for the main Armada repository. This file holds only what is
specific to the build.

## Scope

- **Toolchain only.** The container, pins, Conan lock, patches, embind bindings and the scripts that build,
  smoke-test and package the engine. No Armada logic, UI, settings or validation lives here; those belong in
  the monorepo.
- **Bindings stay boilerplate.** `bindings/armada_bindings.cpp` exposes engine capabilities to JavaScript and
  nothing more. Getters are named `x()`, never `get_x()`.

## Integrity rules

- **Every input is pinned by hash**:
  - sources: `pins.json`, commit + SHA-256
  - Conan recipes: `conan.lock`
  - base image: `build/Dockerfile`, by digest
  - Python packages: `build/requirements.txt`, `--require-hashes`
  - actions: workflows, by commit
  Never loosen a pin, add an unpinned download, or pull a prebuilt engine.
- **Never edit `build/requirements.txt` or `conan.lock` by hand.** Regenerate the first with
  `uv pip compile build/requirements.in --generate-hashes --python-version 3.13 --python-platform x86_64-unknown-linux-gnu --no-header -o build/requirements.txt`
  and the second with `python scripts/build.py lock`.
- **Release assets are produced only by `release.yml` on a tag.** Pull requests build and smoke-test only.
- **Release builds never restore a cache.**
- **Builds are byte-reproducible.** `SOURCE_DATE_EPOCH` is the built commit's author time, set by
  `scripts/build.py` on the host. Never add an input that varies between runs (time, paths, randomness).
  Check a release by building its tag and comparing against its `SHA256SUMS`.

## Changing the engine source

- Patches are LF-only unified diffs, applied in name order with `patch -p1`. Make one by extracting the pinned
  tarball, `git init`-ing it with `core.autocrlf=false`, editing, and saving `git diff` into `patches/`.
- Keep patches minimal, each with a comment in the changed code saying why it exists. Current ones:
  - link for `web,worker,node`;
  - raise the memory ceiling to 4 GB, the WebAssembly maximum (Emscripten's default is 2 GB);
  - put the bindings on the executable (static-archive registrations can be dropped);
  - take the pinned commit instead of asking git (a tarball has no `.git`).

## Commands

See `README.md`. `python scripts/build.py build` followed by `node scripts/smoke.mjs` is the check for any
change. Scripts are standard-library Python and plain Node.