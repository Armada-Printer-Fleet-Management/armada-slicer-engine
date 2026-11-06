#!/usr/bin/env python3
"""Assemble the release assets from out/engine/ into dist/.

    python scripts/package.py --repository OWNER/REPO --ref REF [--release]

REF is the release tag (vX.Y.Z-rN) or, outside a release, the commit being built. --release checks
that the tag names the engine version that was built. GitHub release assets cannot hold folders, so
dist/ is flat. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "engine"
DIST = ROOT / "dist"

ASSETS = {
    "CuraEngine.js": OUT / "CuraEngine.js",
    "CuraEngine.d.ts": OUT / "CuraEngine.d.ts",
    "fdmprinter.def.json": OUT / "definitions" / "fdmprinter.def.json",
    "fdmextruder.def.json": OUT / "definitions" / "fdmextruder.def.json",
    "LICENSE-CuraEngine.txt": OUT / "licenses" / "CuraEngine-LICENSE",
    "LICENSE-Cura-definitions.txt": OUT / "licenses" / "Cura-LICENSE",
}


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def notice(buildinfo: dict, repository: str, ref: str) -> str:
    engine = buildinfo["sources"]["curaengine"]
    cura = buildinfo["sources"]["cura"]
    return f"""CuraEngine {engine["tag"]} compiled to WebAssembly by https://github.com/{repository} at {ref}.

CuraEngine.js, CuraEngine.d.ts
  CuraEngine by UltiMaker, licensed under the GNU AGPL-3.0 (LICENSE-CuraEngine.txt), built with the
  patches and bindings in the repository above. Corresponding source:
    build scripts, patches, bindings and pins: https://github.com/{repository}/tree/{ref}
    CuraEngine: https://github.com/{engine["repository"]}/tree/{engine["commit"]}

fdmprinter.def.json, fdmextruder.def.json
  Unmodified from UltiMaker Cura {cura["tag"]}, licensed under the GNU LGPL-3.0 (LICENSE-Cura-definitions.txt).
  Source: https://github.com/{cura["repository"]}/tree/{cura["commit"]}/resources/definitions
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repository", required=True, help="this repository, OWNER/REPO")
    parser.add_argument("--ref", required=True, help="the release tag, or the commit being built")
    parser.add_argument("--release", action="store_true", help="require REF to be vX.Y.Z-rN for the built engine")
    args = parser.parse_args()

    missing = [str(path.relative_to(ROOT)) for path in [*ASSETS.values(), OUT / "BUILDINFO.json"] if not path.exists()]
    if missing:
        fail(f"run `python scripts/build.py build` first; missing {', '.join(missing)}")
    buildinfo = json.loads((OUT / "BUILDINFO.json").read_text(encoding="utf-8"))
    version = buildinfo["engine"]["version"]
    if args.release and not re.fullmatch(rf"v{re.escape(version)}-r[1-9][0-9]*", args.ref):
        fail(f"release tag {args.ref!r} must be v{version}-rN for the engine that was built")

    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir()
    for name, source in ASSETS.items():
        shutil.copy2(source, DIST / name)
    buildinfo["release"] = {"repository": args.repository, "ref": args.ref}
    (DIST / "BUILDINFO.json").write_text(json.dumps(buildinfo, indent=2) + "\n", encoding="utf-8")
    (DIST / "NOTICE.txt").write_text(notice(buildinfo, args.repository, args.ref), encoding="utf-8")

    sums = "".join(f"{sha256_of(path)}  {path.name}\n" for path in sorted(DIST.iterdir()))
    (DIST / "SHA256SUMS").write_text(sums, encoding="utf-8")
    print(sums, end="")


if __name__ == "__main__":
    main()