#!/usr/bin/env python3
"""Build CuraEngine to WebAssembly from pinned, verified source.

Run from anywhere on a machine with Docker:

    python scripts/build.py verify   download the pinned sources and check them (no Docker)
    python scripts/build.py lock     regenerate conan.lock; review its diff before committing it
    python scripts/build.py build    verify, patch, build, and collect the engine into out/engine/

On the host, `lock` and `build` build build/Dockerfile and re-run this script inside it, so a local
build and CI run exactly the same steps. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINS = ROOT / "pins.json"
LOCK = ROOT / "conan.lock"
DOCKERFILE = ROOT / "build" / "Dockerfile"
PATCHES = ROOT / "patches"
BINDINGS = ROOT / "bindings" / "armada_bindings.cpp"
SOURCES = ROOT / ".cache" / "sources"
OUT = ROOT / "out" / "engine"

IMAGE = "armada-slicer-engine-builder"
CONAN_VOLUME = "armada-slicer-engine-conan"
IN_CONTAINER = os.environ.get("ARMADA_ENGINE_BUILDER") == "1"
# Inside the container the scratch tree stays off the bind mount: faster, and no host file-system quirks.
WORK = Path("/tmp/armada-work") if IN_CONTAINER else ROOT / ".cache" / "work"

RECIPE_USER = "armada"
RECIPE_CHANNEL = "wasm"
PROFILE_HOST = "cura_wasm.jinja"
PROFILE_BUILD = "cura_build.jinja"
DEFINITIONS = ("fdmprinter.def.json", "fdmextruder.def.json")
# The profile turns these off; a build with either on would pull in gRPC/protobuf networking code.
REQUIRED_OPTIONS = {"enable_arcus": "False", "enable_plugins": "False"}

COMMIT = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def step(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def run(command: list[str], **kwargs: object) -> None:
    print("$ " + " ".join(command), flush=True)
    subprocess.run(command, check=True, **kwargs)  # type: ignore[arg-type]


@dataclass(frozen=True)
class Source:
    name: str
    repository: str
    tag: str | None
    commit: str
    sha256: str

    @property
    def url(self) -> str:
        ref = f"refs/tags/{self.tag}" if self.tag else self.commit
        return f"https://github.com/{self.repository}/archive/{ref}.tar.gz"

    @property
    def archive(self) -> Path:
        return SOURCES / f"{self.name}-{self.commit}.tar.gz"


def load_sources() -> dict[str, Source]:
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    if pins.get("targets") != ["wasm"]:
        fail(f"pins.json targets {pins.get('targets')!r}: only ['wasm'] is implemented")
    sources = {name: Source(name=name, **fields) for name, fields in pins["sources"].items()}
    bad = [
        name
        for name, source in sources.items()
        if not COMMIT.fullmatch(source.commit) or not SHA256.fullmatch(source.sha256)
    ]
    if bad:
        fail(f"pins.json has no valid commit/sha256 for: {', '.join(bad)}")
    return sources


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def embedded_commit(archive: Path) -> str | None:
    # GitHub builds archives with `git archive`, which records the commit in the pax global header.
    with tarfile.open(archive, "r:gz") as tar:
        return tar.pax_headers.get("comment")


def fetch(source: Source) -> Path:
    """Download a pinned archive once, and check its bytes and its commit every time it is used."""
    SOURCES.mkdir(parents=True, exist_ok=True)
    if not source.archive.exists():
        print(f"downloading {source.url}", flush=True)
        partial = source.archive.with_suffix(".partial")
        request = urllib.request.Request(source.url, headers={"User-Agent": "armada-slicer-engine-build"})
        with urllib.request.urlopen(request, timeout=300) as response, partial.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        partial.replace(source.archive)

    actual = sha256_of(source.archive)
    if actual != source.sha256:
        source.archive.unlink()
        fail(f"{source.name}: SHA-256 {actual} does not match the pin {source.sha256}; the download was deleted")
    commit = embedded_commit(source.archive)
    if commit != source.commit:
        fail(f"{source.name}: archive was made from commit {commit}, not the pinned {source.commit}")
    print(f"verified {source.name} {source.tag or source.commit} (sha256 {actual[:12]}..., commit {commit[:12]}...)")
    return source.archive


def extract(archive: Path, destination: Path, only: tuple[str, ...] = ()) -> Path:
    """Extract an archive into an empty folder and return its single top-level directory."""
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as tar:
        members = [m for m in tar.getmembers() if not only or any(p in m.name for p in only)]
        tar.extractall(destination, members=members, filter="data")
    (top,) = destination.iterdir()
    return top


def prepare_engine(source: Source) -> Path:
    step("Preparing the CuraEngine source")
    engine = extract(source.archive, WORK / "curaengine")
    bindings = engine / "src" / "armada" / BINDINGS.name
    bindings.parent.mkdir(parents=True)
    shutil.copy2(BINDINGS, bindings)
    for patch in sorted(PATCHES.glob("*.patch")):
        run(["patch", "-p1", "--forward", "--batch", "--input", str(patch)], cwd=engine)

    # The recipe normally asks git for the commit; the patch makes it trust this pinned value instead.
    conandata = engine / "conandata.yml"
    text = conandata.read_text(encoding="utf-8")
    if text.count('commit: "unknown"') != 1:
        fail("conandata.yml no longer has exactly one 'commit: \"unknown\"' line; update build.py for this engine version")
    conandata.write_text(text.replace('commit: "unknown"', f'commit: "{source.commit}"'), encoding="utf-8")
    return engine


def configure_conan(source: Source) -> None:
    step("Configuring Conan from the pinned conan-config")
    config = extract(source.archive, WORK / "conan-config")
    run(["conan", "config", "install", str(config)])
    run(["conan", "profile", "detect", "--exist-ok"])


def conan_command(verb: list[str], engine: Path, version: str) -> list[str]:
    return [
        "conan", *verb, str(engine),
        "--version", version, "--user", RECIPE_USER, "--channel", RECIPE_CHANNEL,
        "-pr:h", PROFILE_HOST, "-pr:b", PROFILE_BUILD,
    ]  # fmt: skip


def lock(sources: dict[str, Source]) -> None:
    for source in sources.values():
        fetch(source)
    configure_conan(sources["conan-config"])
    engine_source = sources["curaengine"]
    engine = prepare_engine(engine_source)
    step("Resolving every dependency into conan.lock")
    run([*conan_command(["lock", "create"], engine, str(engine_source.tag)), "--lockfile-out", str(LOCK)])


def build(sources: dict[str, Source], jobs: int) -> None:
    if not LOCK.exists():
        fail("conan.lock is missing; run `python scripts/build.py lock` and commit the result")
    for source in sources.values():
        fetch(source)
    configure_conan(sources["conan-config"])
    engine_source = sources["curaengine"]
    engine = prepare_engine(engine_source)
    if not os.environ.get("SOURCE_DATE_EPOCH", "").isdigit():
        fail("SOURCE_DATE_EPOCH is not set; run this script on the host, which sets it from the commit being built")

    step(f"Building every dependency and the engine from source ({jobs} parallel jobs)")
    graph_file = WORK / "graph.json"
    with graph_file.open("w", encoding="utf-8") as graph_out:
        run(
            [
                *conan_command(["create"], engine, str(engine_source.tag)),
                "--build=*", "--lockfile", str(LOCK),
                "-c", f"tools.build:jobs={jobs}", "--format=json",
            ],
            stdout=graph_out,
        )  # fmt: skip
    graph = json.loads(graph_file.read_text(encoding="utf-8"))
    collect(graph, sources)


def find_node(graph: dict[str, object], name: str) -> dict[str, object] | None:
    nodes = graph["graph"]["nodes"]  # type: ignore[index]
    for node in nodes.values():  # type: ignore[union-attr]
        if str(node.get("ref", "")).startswith(f"{name}/"):
            return node
    return None


def collect(graph: dict[str, object], sources: dict[str, Source]) -> None:
    step("Collecting the engine, its definitions and licences")
    engine_node = find_node(graph, "curaengine")
    if engine_node is None or not engine_node.get("package_folder"):
        fail("the Conan graph has no built curaengine package")
    options = engine_node.get("options", {})
    wrong = {k: options.get(k) for k, v in REQUIRED_OPTIONS.items() if options.get(k) != v}
    if wrong:
        fail(f"curaengine was built with {wrong}; expected {REQUIRED_OPTIONS}")

    package = Path(str(engine_node["package_folder"]))
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "definitions").mkdir(parents=True)
    (OUT / "licenses").mkdir()
    for name in ("CuraEngine.js", "CuraEngine.d.ts"):
        if not (package / "bin" / name).exists():
            fail(f"the curaengine package has no bin/{name}")
        shutil.copy2(package / "bin" / name, OUT / name)
    shutil.copy2(package / "license" / "LICENSE", OUT / "licenses" / "CuraEngine-LICENSE")

    cura = extract(sources["cura"].archive, WORK / "cura", only=("/resources/definitions/fdm", "/LICENSE"))
    for name in DEFINITIONS:
        shutil.copy2(cura / "resources" / "definitions" / name, OUT / "definitions" / name)
    shutil.copy2(cura / "LICENSE", OUT / "licenses" / "Cura-LICENSE")

    emsdk = find_node(graph, "emsdk")
    conan_version = subprocess.run(["conan", "--version"], check=True, capture_output=True, text=True)
    buildinfo = {
        "engine": {"version": sources["curaengine"].tag, "reference": engine_node["ref"], "options": options},
        "sources": {name: vars(source) for name, source in sources.items()},
        "toolchain": {
            "base_image": base_image(),
            "conan": conan_version.stdout.strip(),
            "emsdk": emsdk["ref"] if emsdk else None,
            "profiles": {"host": PROFILE_HOST, "build": PROFILE_BUILD},
        },
        "source": {
            "commit": os.environ.get("ARMADA_SOURCE_COMMIT"),
            "source_date_epoch": int(os.environ["SOURCE_DATE_EPOCH"]),
        },
        "inputs_sha256": {
            "conan.lock": sha256_of(LOCK),
            "bindings/armada_bindings.cpp": sha256_of(BINDINGS),
            **{f"patches/{p.name}": sha256_of(p) for p in sorted(PATCHES.glob("*.patch"))},
        },
    }
    (OUT / "BUILDINFO.json").write_text(json.dumps(buildinfo, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"engine collected in {OUT.relative_to(ROOT)}")


def source_commit() -> tuple[str, str]:
    """The commit being built and its author time, which becomes SOURCE_DATE_EPOCH.

    Author time, not committer time: a rebase merge rewrites the committer time, and the build of a pull
    request should match the release later built from the same change on main.
    """

    def git(*arguments: str) -> str:
        return subprocess.run(["git", "-C", str(ROOT), *arguments], check=True, capture_output=True, text=True).stdout

    commit, epoch = git("log", "-1", "--format=%H %at").split()
    if git("status", "--porcelain", "--untracked-files=no").strip():
        print(
            "warning: uncommitted changes; the build is stamped with the last commit's time but will not match it",
            file=sys.stderr,
        )
    return commit, epoch


def base_image() -> str:
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("FROM "):
            return line.split()[1]
    fail("build/Dockerfile has no FROM line")
    return ""


def run_in_container(args: argparse.Namespace, forwarded: list[str]) -> None:
    if shutil.which("docker") is None:
        fail("Docker is required for `lock` and `build`")
    step("Building the build container")
    run(["docker", "build", "-f", str(DOCKERFILE), "-t", IMAGE, str(ROOT)])

    # The engine compiles __DATE__ in; stamping it with the commit's time makes every rebuild byte-identical.
    commit, epoch = source_commit()
    command = [
        "docker", "run", "--rm", "-v", f"{ROOT}:/work",
        "-e", f"SOURCE_DATE_EPOCH={epoch}", "-e", f"ARMADA_SOURCE_COMMIT={commit}",
    ]  # fmt: skip
    if args.conan_cache:
        # CI mounts a host folder it caches; run as the host user so the files stay writable there.
        cache = Path(args.conan_cache).resolve()
        cache.mkdir(parents=True, exist_ok=True)
        command += ["-v", f"{cache}:/conan"]
        if hasattr(os, "getuid"):
            command += ["--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp"]
    else:
        command += ["-v", f"{CONAN_VOLUME}:/conan"]
    step("Running inside the build container")
    result = subprocess.run([*command, IMAGE, "python", "scripts/build.py", *forwarded])
    sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("verify", "lock", "build"))
    parser.add_argument("--jobs", type=int, default=4, help="parallel compile jobs; Boost under emcc needs ~2 GiB each")
    parser.add_argument("--conan-cache", help="host folder for the Conan cache (CI); default is a Docker volume")
    args = parser.parse_args()
    sources = load_sources()

    if args.command == "verify":
        for source in sources.values():
            fetch(source)
        return
    if not IN_CONTAINER:
        run_in_container(args, [args.command, "--jobs", str(args.jobs)])

    try:
        if args.command == "lock":
            lock(sources)
        else:
            build(sources, args.jobs)
    except subprocess.CalledProcessError as error:
        fail(f"command failed with exit code {error.returncode}: {' '.join(map(str, error.cmd))}")


if __name__ == "__main__":
    main()
