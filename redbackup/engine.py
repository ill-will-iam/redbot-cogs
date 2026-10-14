"""Local, non-destructive snapshot helper for the RedBackup cog.

Backup archives never contain files from outside the selected, explicit roots.
No archive extraction or bot modification is performed by this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Tuple

SQLITE_SUFFIXES = {".sqlite", ".sqlite3", ".db"}
SQLITE_SIDECARS = ("-wal", "-shm", "-journal")
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_destination(directory: Path, sources: Iterable[Path]) -> None:
    """Refuse writing backups inside or around backed-up source directories."""
    if directory.is_symlink():
        raise ValueError("The backup directory may not be a symbolic link.")
    target = directory.resolve()
    if target == Path(target.anchor):
        raise ValueError("Refusing to use a filesystem root as a backup directory.")
    for source in sources:
        src = source.resolve()
        if is_inside(target, src) or is_inside(src, target):
            raise ValueError("The backup directory must not overlap a backed-up source: " + str(src))


def prepare_destination(directory: Path, sources: Iterable[Path]) -> Path:
    validate_destination(directory, sources)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Backup location must be a normal directory.")
    # Do not broaden an existing directory's permissions. Refuse insecure ones.
    mode = stat.S_IMODE(directory.stat().st_mode)
    if mode & 0o077:
        raise PermissionError("Backup directory has group/other permissions. Run: chmod 700 " + str(directory))
    return directory


def source_files(folder: Path) -> Iterable[Tuple[Path, Path]]:
    """Yield (absolute path, relative path), excluding symlinks and runtime caches."""
    for root, dirs, files in os.walk(folder, topdown=True, followlinks=False):
        rootpath = Path(root)
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (rootpath / d).is_symlink())
        for name in sorted(files):
            path = rootpath / name
            if path.is_symlink() or not path.is_file():
                continue
            # SQLite snapshot incorporates uncheckpointed WAL changes.
            if name.endswith(SQLITE_SIDECARS):
                continue
            yield path, path.relative_to(folder)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def _sqlite_snapshot(src: Path, tmpdir: Path) -> Path:
    # A temporary copy is required: VACUUM INTO isn't supported everywhere.
    import uuid
    dst_file = tmpdir / (uuid.uuid4().hex + ".sqlite")
    # Read-only connection honors WAL and makes SQLite's online backup safe.
    with sqlite3.connect(src.as_uri() + "?mode=ro", uri=True, timeout=30) as from_db:
        with sqlite3.connect(str(dst_file), timeout=30) as to_db:
            from_db.backup(to_db, pages=256, sleep=0.25)
    return dst_file


def build_archive(
    output: Path,
    *,
    roots: Mapping[str, Path],
    instance_config: Mapping[str, object],
    manifest_base: Mapping[str, object],
) -> Dict[str, object]:
    """Create+CRC-verify a zip at `output`, which must be a private *.partial path.

    Fail rather than silently omit missing sources or unreadable data. The caller
    must ensure its destination doesn't overlap any root.
    """
    file_count = 0
    sqlite_count = 0
    raw_bytes = 0
    file_hashes: Dict[str, str] = {}
    source_locations = {name: str(p.resolve()) for name, p in roots.items()}
    # Create before opening ZIP to avoid briefly exposing sensitive data
    # with the service's default umask (often 022).
    fd = os.open(str(output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    with tempfile.TemporaryDirectory(prefix="redbackup-sqlite-", dir=str(output.parent)) as temp:
        tmpdir = Path(temp)
        with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
                             allowZip64=True) as archive:
            for prefix, directory in roots.items():
                if not directory.is_dir():
                    raise FileNotFoundError("Backup source not found: " + str(directory))
                if not prefix or prefix.startswith("/") or ".." in Path(prefix).parts:
                    raise ValueError("Unsafe archive prefix")
                for file, relative in source_files(directory):
                    arcname = prefix + "/" + relative.as_posix()
                    if arcname in file_hashes:
                        raise ValueError("Duplicate archive name: " + arcname)
                    snapshot = file
                    # Distinguish SQLite databases from other .db file formats.
                    if file.suffix.lower() in SQLITE_SUFFIXES:
                        with file.open("rb") as header_reader:
                            is_sqlite = header_reader.read(16) == b"SQLite format 3\x00"
                        if is_sqlite:
                            snapshot = _sqlite_snapshot(file, tmpdir)
                            sqlite_count += 1
                    try:
                        # Hash EXACTLY the bytes written to ZIP, even if a live
                        # non-SQLite file changes between open() and close().
                        info = zipfile.ZipInfo.from_file(snapshot, arcname=arcname)
                        info.compress_type = zipfile.ZIP_DEFLATED
                        h = hashlib.sha256()
                        nbytes = 0
                        with snapshot.open("rb") as original, archive.open(info, mode="w", force_zip64=True) as zipped:
                            for chunk in iter(lambda: original.read(1024 * 1024), b""):
                                zipped.write(chunk)
                                h.update(chunk)
                                nbytes += len(chunk)
                        file_hashes[arcname] = h.hexdigest()
                        raw_bytes += nbytes
                    finally:
                        if snapshot != file:
                            snapshot.unlink(missing_ok=True)
                    file_count += 1
            registration = json.dumps(instance_config, indent=2, sort_keys=True).encode("utf-8")
            archive.writestr("metadata/instance-registration.json", registration)
            file_hashes["metadata/instance-registration.json"] = hashlib.sha256(registration).hexdigest()
            manifest = dict(manifest_base)
            manifest.update({
                "format": "redbackup-live-v1",
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "note": "LIVE backup: SQLite databases snapshotted online; other files may change while copying. Restore offline.",
                "source_paths": source_locations,
                "files": file_count + 1,
                "sqlite_snapshots": sqlite_count,
                "uncompressed_bytes": raw_bytes + len(registration),
                "sha256_by_file": file_hashes,
            })
            archive.writestr("metadata/manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    result = verify_archive(output, strict=True)
    result.update({"files": file_count + 1, "sqlite_snapshots": sqlite_count})
    return result


def verify_archive(filename: Path, strict: bool = True) -> Dict[str, object]:
    """Check ZIP member CRCs and, for our own archives, each manifest digest."""
    with zipfile.ZipFile(filename, mode="r") as zf:
        bad = zf.testzip()
        if bad:
            raise ValueError("Corrupt ZIP member: " + bad)
        names = set(zf.namelist())
        if "metadata/manifest.json" not in names:
            raise ValueError("Missing RedBackup manifest")
        manifest = json.loads(zf.read("metadata/manifest.json"))
        if manifest.get("format") != "redbackup-live-v1":
            raise ValueError("Unrecognized RedBackup archive format")
        expected = manifest.get("sha256_by_file")
        if not isinstance(expected, dict) or not expected:
            raise ValueError("Missing checksum manifest")
        if strict and (names - {"metadata/manifest.json"}) != set(expected):
            raise ValueError("Archive contents differ from checksum manifest")
        for name, digest in expected.items():
            if name not in names:
                raise ValueError("Missing archived item: " + name)
            with zf.open(name, "r") as reader:
                h = hashlib.sha256()
                for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                    h.update(chunk)
            if h.hexdigest() != digest:
                raise ValueError("Checksum mismatch: " + name)
    return {"size_bytes": filename.stat().st_size, "sha256": sha256_file(filename), "manifest": manifest}


def list_archives(directory: Path, prefix: str) -> List[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        (p for p in directory.iterdir()
         if p.is_file() and not p.is_symlink() and p.name.startswith(prefix) and p.suffix == ".zip"),
        key=lambda p: p.name, reverse=True,
    )


def trim_archives(directory: Path, prefix: str, keep: int) -> List[str]:
    if keep < 1:
        raise ValueError("At least one backup must be retained")
    removed = []
    for old in list_archives(directory, prefix)[keep:]:
        old.unlink()
        digest = old.with_name(old.name + ".sha256")
        if digest.exists() and not digest.is_symlink():
            digest.unlink()
        removed.append(old.name)
    return removed
