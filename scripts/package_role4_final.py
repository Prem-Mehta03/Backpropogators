"""Build a local ZIP of scoped working-tree source and one final evidence run."""

import argparse
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "evaluation/logs/role4"
MANIFEST = "MANIFEST.json"
EVIDENCE_SUFFIXES = {".csv", ".json", ".jsonl"}
EXCLUDED_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pem", ".key", ".db", ".sqlite", ".sqlite3", ".zip"}
CREDENTIAL = re.compile(
    rb"(?:gsk_|gh[pousr]_|github_pat_|sk-(?:proj-|svcacct-)?)[A-Za-z0-9_-]{20,}"
    rb"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)


def _git(*arguments: str) -> bytes:
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def _git_paths(*arguments: str) -> set[str]:
    return set(_git(*arguments).decode("utf-8").rstrip("\0").split("\0")) - {""}


def _safe_relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not path.parts
        or path.as_posix() != name
        or path.is_absolute()
        or "\\" in name
        or ":" in name
        or ".." in path.parts
        or any(ord(char) < 32 for char in name)
    ):
        raise ValueError(f"Unsafe package path: {name}")
    if any(part.casefold() in EXCLUDED_PARTS for part in path.parts):
        raise ValueError(f"Metadata, cache or environment path: {name}")
    if path.name.casefold().startswith(".env") and name != ".env.example":
        raise ValueError(f"Secret or private dotenv path: {name}")
    if path.suffix.casefold() in EXCLUDED_SUFFIXES:
        raise ValueError(f"Private or generated file type: {name}")
    return path


def _read_file(base: Path, name: str) -> bytes:
    relative = _safe_relative(name)
    path = base.joinpath(*relative.parts)
    # Reject links and junctions, including linked ancestor directories.
    if not path.is_file() or path.resolve(strict=True) != path:
        raise ValueError(f"Package entry must be a regular, unlinked file: {name}")
    data = path.read_bytes()
    if CREDENTIAL.search(data):
        raise ValueError(f"Possible credential in package entry: {name}")
    if path.suffix in {".pptx", ".docx"}:
        with ZipFile(io.BytesIO(data)) as embedded:
            for item in embedded.namelist():
                if item.endswith((".xml", ".rels")) and CREDENTIAL.search(embedded.read(item)):
                    raise ValueError(f"Possible credential in Office package entry: {name}")
    if name == ".env.example":
        for line in data.decode("utf-8").splitlines():
            key, _, value = line.strip().partition("=")
            if key.endswith(("API_KEY", "TOKEN", "SECRET", "PASSWORD")) and value.strip():
                raise ValueError("Credential fields in .env.example must be empty")
    return data


def _source_entries(include_from: Path) -> dict[str, bytes]:
    explicit = {
        line.strip()
        for line in include_from.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    tracked = _git_paths("ls-files", "-z", "--cached")
    modified = _git_paths("diff", "--name-only", "-z", "HEAD", "--")
    if modified - explicit:
        raise ValueError(f"Tracked changes outside contribution manifest: {sorted(modified - explicit)}")
    untracked = _git_paths("ls-files", "-z", "--others", "--exclude-standard")
    if explicit - (tracked | untracked):
        raise ValueError(f"Missing or ignored manifest paths: {sorted(explicit - tracked - untracked)}")
    entries = {}
    for name in sorted(tracked | explicit):
        if name.casefold() == MANIFEST.casefold() or name.casefold().startswith(("evidence/", "evaluation/logs/")):
            raise ValueError(f"Reserved package path: {name}")
        entries[name] = _read_file(ROOT, name)
    return entries


def _evidence_entries(evidence: Path) -> dict[str, bytes]:
    evidence = evidence.resolve(strict=True)
    if EVIDENCE_ROOT not in evidence.parents or not evidence.is_dir():
        raise ValueError("Evidence must be a single run directory under evaluation/logs/role4")
    if not all((evidence / name).is_file() for name in ("summary.json", "metrics.csv")):
        raise ValueError("Expected the final runner's summary.json and metrics.csv")
    entries = {}
    for path in sorted(evidence.rglob("*")):
        if path.resolve(strict=True) != path:
            raise ValueError(f"Linked item in evidence directory: {path.name}")
        if path.is_dir():
            continue
        relative = path.relative_to(evidence).as_posix()
        suffix = path.suffix.lower()
        if suffix not in EVIDENCE_SUFFIXES:
            raise ValueError(f"Unrecognized evidence file: {relative}")
        data = _read_file(evidence, relative)
        if suffix == ".json":
            json.loads(data)
        elif suffix == ".jsonl":
            for line in data.decode("utf-8").splitlines():
                json.loads(line)
        entries[f"evidence/{relative}"] = data
    return entries


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_archive(output: Path, entries: dict[str, bytes]) -> None:
    with output.open("xb") as file:
        try:
            with ZipFile(file, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
                for name, data in sorted(entries.items()):
                    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)
        except BaseException:
            file.close()
            output.unlink()
            raise


def verify_package(path: Path) -> dict:
    """Return a verified manifest or raise if the ZIP disagrees with its file hashes."""
    with ZipFile(path) as archive:
        manifest = json.loads(archive.read(MANIFEST))
        files = manifest["files"]
        by_name = {entry["path"]: entry for entry in files}
        names = archive.namelist()
        if (
            len(files) != len(by_name)
            or len({name.casefold() for name in names}) != len(files) + 1
            or len(names) != len(files) + 1
            or set(names) != {*by_name, MANIFEST}
        ):
            raise ValueError("ZIP entry names do not match its manifest")
        for name, entry in by_name.items():
            _safe_relative(name)
            data = archive.read(name)
            if len(data) != entry["bytes"] or _digest(data) != entry["sha256"]:
                raise ValueError(f"Manifest verification failed: {name}")
    return manifest


def build_package(evidence: Path, include_from: Path, output: Path) -> dict:
    """Create and verify a non-overwriting ZIP with source, evidence and SHA-256 hashes."""
    sources = _source_entries(include_from)
    logs = _evidence_entries(evidence)
    entries = {**sources, **logs}
    if len({name.casefold() for name in entries}) != len(entries):
        raise ValueError("Case-insensitive ZIP filename collision")
    manifest = {
        "format_version": 1,
        "project": "I, Agent",
        "base_head": _git("rev-parse", "HEAD").decode("ascii").strip(),
        "evidence_kind": "offline simulated-world rehearsal",
        "source_file_count": len(sources),
        "evidence_file_count": len(logs),
        "files": [
            {"path": name, "bytes": len(data), "sha256": _digest(data)}
            for name, data in sorted(entries.items())
        ],
    }
    entries[MANIFEST] = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    _write_archive(output, entries)
    if verify_package(output) != manifest:
        raise ValueError("Read-back manifest differs from generated manifest")
    return manifest


def main() -> int:
    """Parse input paths, create or verify the ZIP, and report verified counts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, help="One final rehearsal output directory")
    parser.add_argument("--include-from", type=Path, help="Explicit Role 4 contribution file list")
    parser.add_argument("--output", type=Path, help="New destination ZIP")
    parser.add_argument("--verify", type=Path, help="Check an existing ZIP against its manifest")
    args = parser.parse_args()
    if args.verify and any((args.evidence, args.include_from, args.output)):
        parser.error("--verify is a separate operation")
    if not args.verify and not all((args.evidence, args.include_from, args.output)):
        parser.error("Provide --evidence, --include-from and --output, or use --verify")
    try:
        manifest = (
            verify_package(args.verify)
            if args.verify
            else build_package(args.evidence, args.include_from, args.output)
        )
    except (ValueError, OSError, KeyError, BadZipFile, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Package error: {exc}\n")
    print(
        f"Verified {manifest['source_file_count']} source files and "
        f"{manifest['evidence_file_count']} evidence files in {args.verify or args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
