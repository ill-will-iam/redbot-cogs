"""Private on-disk snapshots for ServerSnapshot. No Discord calls in this module."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from pathlib import Path

ID_PATTERN = re.compile(r"^[0-9]{10,22}$")
SNAP_PATTERN = re.compile(r"^\d{8}T\d{6}Z-[a-f0-9]{8}$")


def secure_directory(path: Path) -> Path:
    path = path.expanduser().absolute()
    if path.is_symlink():
        raise ValueError("Snapshot directory cannot be a symlink")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Snapshot destination must be a directory")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError(f"Directory must not be group/world accessible: {path} (chmod 700)")
    return path


def private_write(path: Path, payload: dict) -> None:
    secure_directory(path.parent)
    temp = path.with_name("." + path.name + ".tmp")
    descriptor = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def private_jsonl(path: Path):
    secure_directory(path.parent)
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(descriptor, "w", encoding="utf-8")


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def checked_snapshot(root: Path, guild_id: str, snapshot_id: str) -> Path:
    if not ID_PATTERN.fullmatch(guild_id) or not SNAP_PATTERN.fullmatch(snapshot_id):
        raise ValueError("Invalid guild or snapshot ID")
    path = root / "snapshots" / guild_id / snapshot_id
    if path.is_symlink() or not path.is_dir():
        raise FileNotFoundError("Snapshot not found")
    return path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def finalize(snapshot: Path) -> dict:
    """Hash everything except integrity manifest; refuse links and nonregular files."""
    files = {}
    for path in sorted(snapshot.rglob("*")):
        if path.is_symlink():
            raise ValueError("No symlinks allowed in snapshots")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Unexpected special file")
        name = path.relative_to(snapshot).as_posix()
        if name == "integrity.json":
            continue
        files[name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    manifest = {"format": "serversnapshot-v1", "files": files}
    private_write(snapshot / "integrity.json", manifest)
    return manifest


def verify(snapshot: Path) -> dict:
    manifest = read_json(snapshot / "integrity.json")
    if manifest.get("format") != "serversnapshot-v1":
        raise ValueError("Unrecognized snapshot format")
    entries = manifest.get("files")
    if not isinstance(entries, dict) or "metadata.json" not in entries:
        raise ValueError("Missing files or metadata")
    actual = set()
    for path in snapshot.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlink found in snapshot")
        if not path.is_file():
            continue
        rel = path.relative_to(snapshot).as_posix()
        if rel != "integrity.json":
            actual.add(rel)
    if actual != set(entries):
        raise ValueError("Unexpected or missing snapshot files")
    for name, record in entries.items():
        p = Path(name)
        if p.is_absolute() or ".." in p.parts or p.as_posix() != name:
            raise ValueError("Unsafe snapshot path")
        target = snapshot / p
        if not target.is_file() or target.is_symlink():
            raise ValueError(f"Missing/invalid file: {name}")
        if target.stat().st_size != record["bytes"] or sha256_file(target) != record["sha256"]:
            raise ValueError(f"Checksum mismatch: {name}")
    return manifest


def file_free(path: Path) -> int:
    return shutil.disk_usage(path).free
