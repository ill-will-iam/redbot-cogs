"""Owner-only, VPS-local recovery points for Red-DiscordBot 3.5.x."""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
from importlib import metadata as package_metadata
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from redbot import __version__ as RED_VERSION
from redbot.core import Config, commands
from redbot.core.data_manager import data_path, instance_name, metadata_file, storage_type

from .engine import (build_archive, is_inside, list_archives, prepare_destination,
                     trim_archives, validate_destination, verify_archive)


class RedBackup(commands.Cog):
    """Create local recovery points of a running Red instance (owner only)."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=937628401554, force_registration=True)
        self.config.register_global(target_path="", keep=10)
        self._lock = asyncio.Lock()

    @property
    def _prefix(self) -> str:
        slug = re.sub(r"[^A-Za-z0-9_-]", "_", instance_name())
        return "redbackup-" + slug + "-"

    async def _location(self) -> Path:
        configured = await self.config.target_path()
        if configured:
            return Path(configured).expanduser()
        return Path.home() / "redbot-backups" / instance_name()

    async def _roots(self) -> Dict[str, Path]:
        data = data_path().resolve()
        roots = {"instance-data": data}
        cog_mgr = getattr(self.bot, "_cog_mgr", None)
        if cog_mgr is None:
            raise RuntimeError("Red cog manager not available; cannot discover installed cog code")
        install = (await cog_mgr.install_path()).resolve()
        if not install.is_dir():
            raise FileNotFoundError("Installed cog source path missing: " + str(install))
        if not is_inside(install, data):
            roots["installed-cogs"] = install
        for idx, user_path in enumerate(await cog_mgr.user_defined_paths(), start=1):
            custom = user_path.resolve()
            if not custom.is_dir():
                raise FileNotFoundError("Custom cog path missing: " + str(custom))
            if not is_inside(custom, data) and not is_inside(custom, install):
                roots["custom-cogs-" + str(idx)] = custom
        return roots

    def _registration(self) -> dict:
        with metadata_file().open("r", encoding="utf-8") as configfile:
            registered = json.load(configfile)
        if instance_name() not in registered:
            raise RuntimeError("Current instance has no registration metadata")
        return {instance_name(): registered[instance_name()]}

    @commands.group(name="backup", aliases=["redbackup"], invoke_without_command=True)
    @commands.is_owner()
    @commands.bot_has_permissions(send_messages=True)
    async def backup(self, ctx):
        """Create a VPS-local, timestamped recovery point. `$backup`"""
        if storage_type().upper() != "JSON":
            await ctx.send("Backup refused: Red is using a non-JSON storage backend. "
                           "Use that database's consistent backup tool first (e.g. pg_dump).")
            return
        if self._lock.locked():
            await ctx.send("A backup is already running.")
            return
        async with self._lock:
            try:
                roots = await self._roots()
                outputdir = await self._location()
                # Before any work, enforce no source/destination overlap.
                validate_destination(outputdir, roots.values())
                prepare_destination(outputdir, roots.values())
                registration = self._registration()
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                identifier = secrets.token_hex(3)
                filename = self._prefix + timestamp + "-" + identifier + ".zip"
                target = outputdir / filename
                partial = outputdir / (filename + ".partial")
                base = {
                    "instance": instance_name(),
                    "red_version": str(RED_VERSION),
                    "python_version": sys.version.split()[0],
                    "python_packages": sorted(
                        f"{dist.metadata.get('Name', 'unknown')}=={dist.version}"
                        for dist in package_metadata.distributions()
                    ),
                    "loaded_extensions": sorted(self.bot.extensions.keys()),
                    "source_code_included": True,
                    "storage_type": storage_type(),
                }
                await ctx.send("Starting a **local** recovery snapshot. I’ll verify it before marking it complete.")
                # Worker thread prevents large archives from blocking Discord heartbeats.
                try:
                    result = await asyncio.to_thread(
                        build_archive, partial, roots=roots, instance_config=registration,
                        manifest_base=base,
                    )
                    os.chmod(partial, 0o600)
                    os.replace(partial, target)
                    digest_path = target.with_name(target.name + ".sha256")
                    descriptor = os.open(str(digest_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(descriptor, "w", encoding="utf-8") as checksum_file:
                        checksum_file.write(result["sha256"] + "  " + filename + "\n")
                except Exception:
                    partial.unlink(missing_ok=True)
                    raise
                keep = await self.config.keep()
                try:
                    pruned = await asyncio.to_thread(trim_archives, outputdir, self._prefix, keep)
                except Exception as exc:
                    pruned = []
                    prune_warning = f" (Retention cleanup failed: {type(exc).__name__}.)"
                else:
                    prune_warning = ""
                size_mb = result["size_bytes"] / (1024 * 1024)
                await ctx.send(
                    "**Red backup complete and verified.**\n"
                    f"File: `{filename}`\n"
                    f"Saved on VPS: `{outputdir}`\n"
                    f"Size: **{size_mb:.2f} MiB**, files: **{result['files']}**, "
                    f"SQLite snapshots: **{result['sqlite_snapshots']}**\n"
                    f"Retention: **{keep}** (cleaned up {len(pruned)} old backups).{prune_warning}\n"
                    "This is a **live** snapshot, not an offline guarantee. "
                    "Keep the bot stopped when restoring, and keep an off-VPS copy for disaster recovery."
                )
            except Exception as exc:
                await ctx.send(f"**Backup failed:** `{type(exc).__name__}: {str(exc)[:500]}`. "
                               "No backup has been marked complete. See VPS logs for details.")
                import logging
                logging.getLogger("red.redbackup").exception("RedBackup error")

    @backup.command(name="create", aliases=["now", "save"])
    @commands.is_owner()
    async def backup_create(self, ctx):
        """Explicit alias for `$backup`."""
        await ctx.invoke(self.backup)

    @backup.command(name="list", aliases=["ls"])
    @commands.is_owner()
    async def backup_list(self, ctx):
        """List recent local restore points."""
        directory = await self._location()
        files = list_archives(directory, self._prefix)
        if not files:
            await ctx.send("No RedBackup archives saved yet. Run `$backup`.")
            return
        lines = [f"**Local Red backups** (showing {min(10, len(files))} of {len(files)}):"]
        for file in files[:10]:
            lines.append(f"`{file.name}` — {file.stat().st_size / 1048576:.2f} MiB")
        await ctx.send("\n".join(lines))

    @backup.command(name="verify")
    @commands.is_owner()
    async def backup_verify(self, ctx, filename: str = "latest"):
        """Verify latest backup, or a filename from `$backup list`."""
        directory = await self._location()
        files = list_archives(directory, self._prefix)
        if filename == "latest":
            if not files:
                await ctx.send("No backup archives to verify.")
                return
            path = files[0]
        else:
            if filename != Path(filename).name or not filename.startswith(self._prefix) or not filename.endswith(".zip"):
                await ctx.send("Invalid archive name. Use the exact filename from `$backup list`.")
                return
            path = directory / filename
            if path not in files:
                await ctx.send("Backup archive not found.")
                return
        if self._lock.locked():
            await ctx.send("Please verify after the running backup finishes.")
            return
        async with self._lock:
            await ctx.send("Checking archive CRCs and all SHA-256 file checksums…")
            try:
                result = await asyncio.to_thread(verify_archive, path)
                digest_file = path.with_name(path.name + ".sha256")
                if digest_file.is_file() and not digest_file.is_symlink():
                    expected = digest_file.read_text(encoding="utf-8").split()[0]
                    if result["sha256"] != expected:
                        raise ValueError("Overall archive checksum mismatch")
            except Exception as exc:
                await ctx.send(f"**Verification failed:** `{type(exc).__name__}: {str(exc)[:400]}`")
                return
            await ctx.send(f"**Verified:** `{path.name}` — {result['size_bytes']/1048576:.2f} MiB. "
                           "Archive integrity passed; this does not prove a live multi-file snapshot "
                           "is transactionally consistent.")

    @backup.command(name="path")
    @commands.is_owner()
    async def backup_path(self, ctx):
        """Display destination and source layout (owner-only)."""
        directory = await self._location()
        roots = await self._roots()
        lines = ["**RedBackup location**", f"`{directory}`", "**Captured paths**"]
        lines += [f"`{name}`: `{folder}`" for name, folder in roots.items()]
        await ctx.send("\n".join(lines)[:1950])

    @backup.command(name="setpath")
    @commands.is_owner()
    async def backup_setpath(self, ctx, *, directory: str):
        """Configure an absolute backup directory. `$backup setpath /some/private/path`"""
        requested = Path(os.path.expandvars(directory)).expanduser()
        if not requested.is_absolute():
            await ctx.send("Use an absolute Linux path (e.g. `/home/redbot/backups`).")
            return
        roots = await self._roots()
        try:
            prepare_destination(requested, roots.values())
        except Exception as exc:
            await ctx.send(f"Cannot use that path: `{type(exc).__name__}: {str(exc)[:350]}`")
            return
        await self.config.target_path.set(str(requested.resolve()))
        await ctx.send(f"Backup destination set to `{requested.resolve()}`.")

    @backup.command(name="keep")
    @commands.is_owner()
    async def backup_keep(self, ctx, count: int):
        """Retain the latest 1-100 backups; older backups trimmed after success."""
        if not 1 <= count <= 100:
            await ctx.send("Retention must be between 1 and 100 backups.")
            return
        await self.config.keep.set(count)
        await ctx.send(f"Will retain the latest **{count}** RedBackup snapshots.")

    @backup.command(name="prune")
    @commands.is_owner()
    async def backup_prune(self, ctx):
        """Remove old RedBackup archives exceeding the retention limit."""
        if self._lock.locked():
            await ctx.send("Backup operation in progress.")
            return
        async with self._lock:
            directory = await self._location()
            keep = await self.config.keep()
            removed = await asyncio.to_thread(trim_archives, directory, self._prefix, keep)
        await ctx.send(f"Removed **{len(removed)}** old backups; kept newest **{keep}**.")
