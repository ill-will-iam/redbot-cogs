"""ServerSnapshot: permission-respecting, owner-controlled Discord guild archives.

This is NOT a Discord account/selfbot backup. Historical messages cannot be
restored with original authors, IDs or dates; replay uses labelled bot posts.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
import discord
from redbot.core import Config, commands

from .storage import (checked_snapshot, file_free, finalize, private_jsonl,
                      private_write, read_json, secure_directory, verify)

PREFIX = "ServerSnapshot"
MIN_FREE = 512 * 1024 * 1024  # stop before filling a VPS's filesystem
DISCORD_CDNS = {"cdn.discordapp.com", "media.discordapp.net", "cdn.discordapp.net"}
REASON = "ServerSnapshot authorized reconstruction"


def ts(dt):
    return dt.isoformat() if dt else None


def safe_text(value, maxlen=200):
    return str(value or "").replace("\x00", "")[:maxlen]


def object_id(value):
    return str(value.id) if value is not None else None


def overwrites(channel):
    values = []
    for target, overwrite in channel.overwrites.items():
        allow, deny = overwrite.pair()
        values.append({"id": str(target.id), "kind": "role" if isinstance(target, discord.Role) else "member",
                       "allow": allow.value, "deny": deny.value})
    return values


def role_info(role):
    return {"id": str(role.id), "name": role.name, "permissions": role.permissions.value,
            "colour": role.colour.value, "hoist": role.hoist, "mentionable": role.mentionable,
            "position": role.position, "managed": role.managed, "is_default": role.is_default(),
            "icon": str(role.icon.url) if getattr(role, "icon", None) else None,
            "unicode_emoji": getattr(role, "unicode_emoji", None)}


def channel_info(ch):
    d = {"id": str(ch.id), "type": ch.type.name, "name": ch.name,
         "position": getattr(ch, "position", 0), "category_id": object_id(getattr(ch, "category", None)),
         "overwrites": overwrites(ch)}
    for key in ("topic", "nsfw", "slowmode_delay", "bitrate", "user_limit",
                "default_auto_archive_duration", "default_thread_slowmode_delay"):
        value = getattr(ch, key, None)
        if value is not None:
            d[key] = value
    if isinstance(ch, discord.ForumChannel):
        d["available_tags"] = [{"name": t.name, "moderated": t.moderated,
                                "emoji": str(t.emoji) if t.emoji else None} for t in ch.available_tags]
    return d


def thread_info(ch):
    return {"id": str(ch.id), "name": ch.name, "type": ch.type.name,
            "parent_id": str(ch.parent_id), "archived": ch.archived,
            "locked": ch.locked, "auto_archive_duration": ch.auto_archive_duration,
            "slowmode_delay": ch.slowmode_delay, "owner_id": object_id(getattr(ch, "owner", None)),
            "created_at": ts(ch.created_at), "applied_tags": [str(i) for i in getattr(ch, "applied_tags", [])]}


def message_info(message):
    author = message.author
    return {
        "id": str(message.id), "created_at": ts(message.created_at), "edited_at": ts(message.edited_at),
        "author_id": str(author.id), "author_name": str(author),
        "author_display_name": getattr(author, "display_name", str(author)),
        "author_bot": author.bot, "content": message.content,
        "pinned": message.pinned, "type": str(message.type),
        "reference_id": str(message.reference.message_id) if message.reference and message.reference.message_id else None,
        "embeds": [e.to_dict() for e in message.embeds],
        "reactions": [{"emoji": str(r.emoji), "count": r.count} for r in message.reactions],
        "stickers": [{"id": str(s.id), "name": s.name} for s in getattr(message, "stickers", [])],
        "attachments": [],
    }


class ServerSnapshot(commands.Cog):
    """Back up accessible guild metadata/history/files; recreate a new layout without deleting anything."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=67302911806295, force_registration=True)
        self.config.register_global(path="", max_gib=0)
        self._lock = asyncio.Lock()

    async def _root(self):
        value = await self.config.path()
        return secure_directory(Path(value).expanduser() if value else Path.home() / "discord-server-snapshots")

    async def cog_check(self, ctx):
        """Cog-level owner check also protects subcommands on older Red versions."""
        return await self.bot.is_owner(ctx.author)

    def _allowed(self, ctx):
        return bool(ctx.guild and (ctx.guild.owner_id == ctx.author.id or ctx.author.guild_permissions.administrator))

    async def _authorize(self, ctx):
        if not self._allowed(ctx):
            await ctx.send("Only the server owner or an administrator may operate snapshots here.")
            return False
        return True

    async def _confirm(self, ctx, action, snapshot_id):
        phrase = f"{action.upper()} {snapshot_id}"
        await ctx.send(f"**Confirmation required.** Type `{phrase}` here within 120 seconds. "
                       "This is a potentially large operation; it does not delete existing channels.")
        try:
            await self.bot.wait_for("message", timeout=120, check=lambda m: (
                m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
                and m.guild and m.guild.id == ctx.guild.id and m.content.strip() == phrase))
            return True
        except asyncio.TimeoutError:
            await ctx.send("Confirmation expired. No changes were made.")
            return False

    def _get_snapshot(self, root, src_id, snapshot_id):
        return checked_snapshot(root, str(src_id), snapshot_id)

    def _state_path(self, root, dest_id, src_id, snapshot_id):
        return root / "restore-state" / str(dest_id) / str(src_id) / (snapshot_id + ".json")

    async def _fetch_asset(self, session, url, directory, max_bytes):
        """Stream only Discord-hosted CDN media; deduplicate using content hash."""
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in DISCORD_CDNS:
            raise ValueError("Not an allowed Discord CDN URL")
        secure_directory(directory)
        if file_free(directory) < MIN_FREE:
            raise OSError("Storage reserve reached; cannot download another file")
        temp = directory / (".downloading-" + secrets.token_hex(12))
        digest = hashlib.sha256()
        size = 0
        try:
            async with session.get(url, allow_redirects=False) as response:
                if response.status != 200:
                    raise OSError(f"Discord CDN returned HTTP {response.status}")
                length = int(response.headers.get("content-length") or "0")
                if max_bytes and length > max_bytes:
                    raise OSError("Attachment exceeds configured archive quota")
                fd = os.open(str(temp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as out:
                    async for block in response.content.iter_chunked(65536):
                        size += len(block)
                        if max_bytes and size > max_bytes:
                            raise OSError("Archive quota reached while downloading")
                        if file_free(directory) < MIN_FREE:
                            raise OSError("Disk free-space reserve reached")
                        out.write(block)
                        digest.update(block)
            target = directory / digest.hexdigest()
            if target.exists():
                temp.unlink()
            else:
                os.replace(temp, target)
            return {"path": "assets/" + digest.hexdigest(), "size": size, "sha256": digest.hexdigest()}
        finally:
            temp.unlink(missing_ok=True)

    async def _media(self, session, url, directory, stats, label, quota):
        try:
            if not url:
                return None
            remaining = 0 if quota == 0 else max(0, quota - stats["bytes"])
            if quota and remaining == 0:
                raise OSError("Snapshot media quota reached")
            record = await self._fetch_asset(session, url, directory, remaining)
            stats["bytes"] += record["size"]
            stats["assets"] += 1
            return record
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as exc:
            stats["errors"].append(f"Asset {label}: {type(exc).__name__}: {safe_text(exc)}")
            return None

    async def _archive_history(self, ch, directory, session, stats, quota):
        filename = directory / "messages" / (str(ch.id) + ".jsonl")
        info = {"channel_id": str(ch.id), "messages": 0, "complete": False}
        try:
            with private_jsonl(filename) as stream:
                async for msg in ch.history(limit=None, oldest_first=True):
                    saved = message_info(msg)
                    for item in msg.attachments:
                        media = await self._media(session, item.url, directory / "assets", stats,
                                                  f"message {msg.id}/{item.filename}", quota)
                        saved["attachments"].append({
                            "filename": item.filename, "size": item.size,
                            "content_type": getattr(item, "content_type", None),
                            "description": getattr(item, "description", None),
                            "spoiler": item.is_spoiler(), "media": media})
                    stream.write(json.dumps(saved, ensure_ascii=False, separators=(",", ":")) + "\n")
                    info["messages"] += 1
                    stats["messages"] += 1
                info["complete"] = True
        except (discord.HTTPException, discord.Forbidden, OSError, TypeError) as exc:
            stats["errors"].append(f"History {ch.name} ({ch.id}): {type(exc).__name__}: {safe_text(exc)}")
        return info

    async def _threads(self, guild, stats):
        found = {t.id: t for t in guild.threads}
        for channel in guild.channels:
            if not hasattr(channel, "archived_threads"):
                continue
            for private in (False, True):
                try:
                    try:
                        iterator = channel.archived_threads(limit=None, private=private)
                    except TypeError:
                        if private:
                            continue
                        iterator = channel.archived_threads(limit=None)
                    async for thread in iterator:
                        found[thread.id] = thread
                except (discord.HTTPException, discord.Forbidden) as exc:
                    stats["errors"].append(f"Archived threads in {channel.name} ({private}): {safe_text(exc)}")
                except TypeError:
                    stats["errors"].append(f"Archived threads not available in {channel.name}")
                    break
        return sorted(found.values(), key=lambda t: t.id)

    @commands.group(name="serversnapshot", aliases=["sbackup"], invoke_without_command=True)
    @commands.is_owner()
    @commands.guild_only()
    async def serversnapshot(self, ctx):
        """Owner-only private backups: `~sbackup save`, `list`, `verify`, `plan`, `restore`, `replay`."""
        await ctx.send("ServerSnapshot: `save`, `list`, `verify <id>`, `plan <source_guild_id> <id>`, "
                       "`restore <source_guild_id> <id>`, `replay <source_guild_id> <id>`, `inspect <id>`, `path`, `setpath`. "
                       "Historical messages are replayed by Fatboy, not recreated as the original authors.")

    @serversnapshot.command(name="path")
    async def path(self, ctx):
        root = await self._root()
        await ctx.send(f"Private snapshot storage: `{root}` (VPS only, never uploaded to Discord).")

    @serversnapshot.command(name="setpath")
    async def setpath(self, ctx, *, path: str):
        requested = Path(path).expanduser()
        if not requested.is_absolute():
            return await ctx.send("Supply an absolute directory path on the VPS.")
        if self._lock.locked():
            return await ctx.send("Snapshot operation in progress.")
        try:
            secure_directory(requested)
            await self.config.path.set(str(requested))
            await ctx.send(f"Snapshot directory: `{requested}`. Older archives are not moved automatically.")
        except (OSError, ValueError) as exc:
            await ctx.send(f"Cannot use path: {safe_text(exc)}")

    @serversnapshot.command(name="save")
    async def save(self, ctx):
        """Create complete accessible-history archive, including Discord-hosted attachments."""
        if not await self._authorize(ctx):
            return
        if self._lock.locked():
            return await ctx.send("Another ServerSnapshot operation is running.")
        async with self._lock:
            root = await self._root()
            snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
            parent = secure_directory(root / "snapshots" / str(ctx.guild.id))
            staging = secure_directory(parent / ("." + snapshot_id + ".partial"))
            dest = parent / snapshot_id
            stats = {"messages": 0, "bytes": 0, "assets": 0, "errors": []}
            await ctx.send(f"Started snapshot `{snapshot_id}` for **{ctx.guild.name}**. "
                           "Scanning all accessible channel/thread history and media. "
                           "Messages or files Fatboy cannot access will be reported.")
            try:
                guild = ctx.guild
                roles = [role_info(role) for role in sorted(guild.roles, key=lambda r: r.position)]
                channels = [channel_info(ch) for ch in sorted(guild.channels, key=lambda c: (c.position, c.id))]
                threads = await self._threads(guild, stats)
                members = []
                member_coverage = "cached-only"
                if self.bot.intents.members:
                    try:
                        members = list([m async for m in guild.fetch_members(limit=None)])
                        member_coverage = "fetched"
                    except (discord.HTTPException, discord.Forbidden) as exc:
                        stats["errors"].append("Member fetch unavailable: " + safe_text(exc))
                if not members:
                    members = list(guild.members)
                member_info = [{"id": str(m.id), "name": str(m), "bot": m.bot,
                                "nick": m.nick, "role_ids": [str(r.id) for r in m.roles if not r.is_default()]}
                               for m in members]
                integrations, invites, bans, events, webhooks = [], [], [], [], []
                try:
                    integrations = [{"id": str(i.id), "name": i.name, "type": str(i.type),
                                     "enabled": getattr(i, "enabled", None), "account": str(getattr(i, "account", ""))}
                                    for i in await guild.integrations()]
                except (discord.HTTPException, discord.Forbidden):
                    stats["errors"].append("Integrations inventory unavailable")
                try:
                    invites = [{"code": i.code, "channel_id": object_id(i.channel),
                                "max_age": i.max_age, "max_uses": i.max_uses} for i in await guild.invites()]
                except (discord.HTTPException, discord.Forbidden):
                    stats["errors"].append("Invites inventory unavailable")
                try:
                    bans = [{"id": str(b.user.id), "name": str(b.user), "reason": b.reason}
                            async for b in guild.bans(limit=None)]
                except (discord.HTTPException, discord.Forbidden):
                    stats["errors"].append("Bans inventory unavailable")
                try:
                    webhooks = [{"id": str(w.id), "name": w.name, "channel_id": object_id(w.channel),
                                 "type": str(w.type)} for w in await guild.webhooks()]
                except (discord.HTTPException, discord.Forbidden):
                    stats["errors"].append("Webhook inventory unavailable")
                try:
                    events = [{"id": str(e.id), "name": e.name, "description": e.description,
                               "start": ts(e.start_time), "end": ts(e.end_time),
                               "channel_id": object_id(e.channel)} for e in await guild.fetch_scheduled_events()]
                except (AttributeError, discord.HTTPException, discord.Forbidden):
                    stats["errors"].append("Scheduled event inventory unavailable")
                metadata = {"format": "serversnapshot-v1", "snapshot_id": snapshot_id,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "guild": {"id": str(guild.id), "name": guild.name,
                                      "description": guild.description, "icon_url": str(guild.icon.url) if guild.icon else None,
                                      "banner_url": str(guild.banner.url) if guild.banner else None,
                                      "verification_level": str(guild.verification_level),
                                      "explicit_content_filter": str(guild.explicit_content_filter),
                                      "default_notifications": str(guild.default_notifications),
                                      "afk_timeout": guild.afk_timeout, "preferred_locale": str(guild.preferred_locale),
                                      "features": list(guild.features),
                                      "system_channel_id": object_id(guild.system_channel),
                                      "rules_channel_id": object_id(guild.rules_channel)},
                            "roles": roles, "channels": channels,
                            "threads": [thread_info(t) for t in threads], "members": member_info,
                            "member_coverage": member_coverage, "integrations": integrations,
                            "bots": [m for m in member_info if m["bot"]],
                            "invites": invites, "bans": bans, "events": events,
                            "webhooks": webhooks, "emojis": [], "stickers": [], "histories": [],
                            "guild_media": {}}
                quota_gib = await self.config.max_gib()
                quota = int(quota_gib * 1024 ** 3) if quota_gib else 0
                timeout = aiohttp.ClientTimeout(total=None, sock_connect=25, sock_read=90)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    for media_key, url in (("icon", metadata["guild"]["icon_url"]),
                                           ("banner", metadata["guild"]["banner_url"])):
                        metadata["guild_media"][media_key] = await self._media(
                            session, url, staging / "assets", stats, media_key, quota)
                    for emoji in guild.emojis:
                        media = await self._media(session, str(emoji.url), staging / "assets", stats,
                                                  "emoji " + emoji.name, quota)
                        metadata["emojis"].append({"id": str(emoji.id), "name": emoji.name,
                                                  "animated": emoji.animated, "media": media})
                    for sticker in guild.stickers:
                        media = await self._media(session, str(sticker.url), staging / "assets", stats,
                                                  "sticker " + sticker.name, quota)
                        metadata["stickers"].append({"id": str(sticker.id), "name": sticker.name,
                                                    "description": sticker.description, "emoji": sticker.emoji,
                                                    "media": media})
                    readable = list(guild.channels) + threads
                    for index, ch in enumerate(readable, 1):
                        if not hasattr(ch, "history"):
                            continue
                        # Some channel types expose a history() method but cannot be read by this bot.
                        info = await self._archive_history(ch, staging, session, stats, quota)
                        metadata["histories"].append(info)
                        if index % 20 == 0:
                            await ctx.send(f"Snapshot progress: {index}/{len(readable)} channels/threads; "
                                           f"{stats['messages']:,} messages, {stats['assets']:,} media items.")
                if not self.bot.intents.message_content:
                    stats["errors"].append("Message Content intent disabled; some text may be unavailable")
                if member_coverage != "fetched":
                    stats["errors"].append("Member roster was cached-only; role assignments may be incomplete")
                metadata["stats"] = stats
                private_write(staging / "metadata.json", metadata)
                await asyncio.to_thread(finalize, staging)
                os.rename(staging, dest)
                complete = sum(1 for h in metadata["histories"] if h["complete"])
                await ctx.send(f"**ServerSnapshot complete:** `{snapshot_id}`\n"
                               f"{len(roles)} roles, {len(channels)} channels, {len(threads)} threads, "
                               f"{stats['messages']:,} messages and {stats['assets']:,} media files. "
                               f"Readable histories: {complete}/{len(metadata['histories'])}. "
                               f"Issues: **{len(stats['errors'])}**.\n"
                               f"Archive saved privately under `{dest}`. "
                               f"Use `~sbackup verify {snapshot_id}` or `~sbackup plan {guild.id} {snapshot_id}`.")
            except Exception as exc:
                await ctx.send(f"Snapshot failed: `{type(exc).__name__}: {safe_text(exc, 300)}`. "
                               f"Partial files retained in `{staging}` for inspection; **not** restorable.")
                raise

    @serversnapshot.command(name="list")
    async def list_snapshots(self, ctx, source_guild_id: str = ""):
        if not await self._authorize(ctx):
            return
        src = source_guild_id or str(ctx.guild.id)
        if not src.isdecimal() or len(src) > 22:
            return await ctx.send("Supply a numeric source guild ID.")
        folder = (await self._root()) / "snapshots" / src
        if not folder.is_dir():
            return await ctx.send("No snapshots found for that server.")
        names = sorted((p.name for p in folder.iterdir() if p.is_dir() and not p.is_symlink()
                        and not p.name.startswith(".")), reverse=True)
        await ctx.send("**Snapshots for " + src + ":**\n" +
                       ("\n".join(f"`{x}`" for x in names[:15]) or "None"))

    @serversnapshot.command(name="verify")
    async def verify_snapshot(self, ctx, snapshot_id: str, source_guild_id: str = ""):
        if not await self._authorize(ctx):
            return
        if self._lock.locked():
            return await ctx.send("Another snapshot operation is running.")
        try:
            path = self._get_snapshot(await self._root(), source_guild_id or str(ctx.guild.id), snapshot_id)
            await ctx.send(f"Checking integrity of `{snapshot_id}`...")
            manifest = await asyncio.to_thread(verify, path)
            await ctx.send(f"**Verified** `{snapshot_id}`: {len(manifest['files'])} files, SHA-256 checksums match. "
                           "An archive may still be incomplete if Fatboy lacked read permissions.")
        except (ValueError, FileNotFoundError, OSError, KeyError) as exc:
            await ctx.send(f"Verification failed: {safe_text(exc)}")

    @serversnapshot.command(name="inspect")
    async def inspect(self, ctx, snapshot_id: str, source_guild_id: str = ""):
        """Inspect coverage warnings and completeness without exposing archived message text."""
        if not await self._authorize(ctx):
            return
        try:
            path = self._get_snapshot(await self._root(), source_guild_id or str(ctx.guild.id), snapshot_id)
            data = read_json(path / "metadata.json")
            incomplete = [h for h in data.get("histories", []) if not h.get("complete")]
            issues = data.get("stats", {}).get("errors", [])
            lines = [f"**Snapshot {snapshot_id}**: {data['stats']['messages']:,} messages, "
                     f"{data['stats']['assets']} media items, "
                     f"{len(incomplete)} incomplete histories, {len(issues)} issues."]
            if incomplete:
                lines.append("Incomplete channel IDs: " + ", ".join(h["channel_id"] for h in incomplete[:10]))
            lines.extend("• " + safe_text(issue, 190) for issue in issues[:7])
            if len(issues) > 7:
                lines.append(f"... {len(issues) - 7} more issues in the VPS metadata.json")
            await ctx.send("\n".join(lines)[:1950])
        except (ValueError, FileNotFoundError, OSError, KeyError) as exc:
            await ctx.send("Cannot inspect snapshot: " + safe_text(exc))

    @serversnapshot.command(name="plan")
    async def plan(self, ctx, source_guild_id: str, snapshot_id: str):
        if not await self._authorize(ctx):
            return
        try:
            archive = self._get_snapshot(await self._root(), source_guild_id, snapshot_id)
            data = read_json(archive / "metadata.json")
        except (ValueError, OSError) as exc:
            return await ctx.send(f"Snapshot unavailable: {safe_text(exc)}")
        if data.get("guild", {}).get("id") != source_guild_id:
            return await ctx.send("Snapshot source guild ID mismatch.")
        stats = data["stats"]
        existing = len(ctx.guild.channels)
        await ctx.send(
            f"**Reconstruction plan**: `{snapshot_id}`\n"
            f"Source: **{data['guild']['name']}** (`{source_guild_id}`) → "
            f"destination: **{ctx.guild.name}** (`{ctx.guild.id}`).\n"
            f"Snapshot contains {len(data['roles'])} roles, {len(data['channels'])} channels, "
            f"{len(data['threads'])} threads, {stats['messages']:,} archived messages and "
            f"{stats['assets']} saved media items; {len(stats['errors'])} capture issues. "
            f"Destination currently has {existing} channels.\n"
            "`restore` creates missing structure without deleting/overwriting existing channels. "
            "`replay` later posts labelled historical messages **only into channels created by this restore**. "
            "Messages will be sent by Fatboy, not their original authors. Managed bot roles/apps "
            "must be reinstalled manually. Verify first: `~sbackup verify " + snapshot_id + " " + source_guild_id + "`.")

    async def _restore_read(self, ctx, root, source_guild_id, snapshot_id):
        archive = self._get_snapshot(root, source_guild_id, snapshot_id)
        await ctx.send("Verifying SHA-256 archive integrity before reconstruction...")
        await asyncio.to_thread(verify, archive)
        data = read_json(archive / "metadata.json")
        if data.get("guild", {}).get("id") != source_guild_id or data.get("snapshot_id") != snapshot_id:
            raise ValueError("Snapshot identity does not match")
        return archive, data

    async def _role_map(self, guild, saved, state, warnings, save, live_roles):
        mapped = state["role_map"]
        for role in saved:
            old_id = role["id"]
            if role["is_default"]:
                mapped[old_id] = str(guild.default_role.id)
                continue
            if role["managed"]:
                # Integration/bot roles cannot be reconstructed by another bot.
                candidates = [r for r in guild.roles if r.managed and r.name == role["name"]]
                if len(candidates) == 1:
                    mapped[old_id] = str(candidates[0].id)
                else:
                    warnings.append("Managed role needs manual integration install: " + role["name"])
                continue
            previous = guild.get_role(int(mapped[old_id])) if old_id in mapped else None
            if previous:
                live_roles[str(previous.id)] = previous
                continue
            # Existing original IDs are the strongest indicator for same-guild recoveries.
            previous = guild.get_role(int(old_id))
            if not previous:
                candidates = [r for r in guild.roles if not r.managed and not r.is_default()
                              and r.name == role["name"]]
                previous = candidates[0] if len(candidates) == 1 else None
            if previous:
                mapped[old_id] = str(previous.id)
                live_roles[str(previous.id)] = previous
                await save()
                continue
            try:
                new = await guild.create_role(name=role["name"],
                                              permissions=discord.Permissions(role["permissions"]),
                                              colour=discord.Colour(role["colour"]),
                                              hoist=role["hoist"], mentionable=role["mentionable"], reason=REASON)
                mapped[old_id] = str(new.id)
                live_roles[str(new.id)] = new
                state["created_roles"].append(str(new.id))
                await save()
            except (discord.HTTPException, discord.Forbidden, ValueError) as exc:
                warnings.append(f"Role {role['name']}: {safe_text(exc)}")
        return mapped

    def _mapped_overwrites(self, guild, record, role_map, live_roles):
        result = {}
        for overwrite in record.get("overwrites", []):
            try:
                if overwrite["kind"] == "role":
                    target_id = role_map.get(overwrite["id"])
                    target = (live_roles.get(str(target_id)) or guild.get_role(int(target_id))) if target_id else None
                else:
                    # Explicit member overrides only apply if they are in the target guild.
                    target = guild.get_member(int(overwrite["id"]))
                if target:
                    result[target] = discord.PermissionOverwrite.from_pair(
                        discord.Permissions(overwrite["allow"]),
                        discord.Permissions(overwrite["deny"]))
            except (ValueError, TypeError, KeyError):
                continue
        return result

    async def _create_channel(self, guild, ch, category, overwrites, warnings):
        common = {"overwrites": overwrites, "reason": REASON}
        kind = ch["type"]
        name = ch["name"]
        if kind == "category":
            return await guild.create_category(name, **common)
        common["category"] = category
        if kind in ("text", "news"):
            options = {"topic": ch.get("topic") or "", "slowmode_delay": ch.get("slowmode_delay", 0),
                       "nsfw": ch.get("nsfw", False)}
            if kind == "news":
                options["news"] = True
            return await guild.create_text_channel(name, **common, **options)
        if kind == "voice":
            return await guild.create_voice_channel(name, **common,
                bitrate=min(ch.get("bitrate", 64000), guild.bitrate_limit),
                user_limit=ch.get("user_limit", 0))
        if kind == "stage_voice":
            return await guild.create_stage_channel(name, **common,
                bitrate=min(ch.get("bitrate", 64000), guild.bitrate_limit),
                user_limit=ch.get("user_limit", 0))
        if kind in ("forum", "media"):
            tags = []
            for tag in ch.get("available_tags", [])[:20]:
                try:
                    emoji = tag.get("emoji")
                    tags.append(discord.ForumTag(name=tag["name"], moderated=tag.get("moderated", False),
                                                emoji=emoji if emoji and not emoji.startswith("<") else None))
                except (ValueError, TypeError):
                    warnings.append("Could not rebuild forum tag: " + safe_text(tag.get("name")))
            options = dict(topic=ch.get("topic") or "", nsfw=ch.get("nsfw", False),
                           slowmode_delay=ch.get("slowmode_delay", 0), available_tags=tags)
            if kind == "media":
                options["media"] = True  # Available in discord.py 2.6+ only
            return await guild.create_forum(name, **common, **options)
        warnings.append(f"Unsupported channel type {kind}: {name}")
        return None

    @serversnapshot.command(name="restore")
    async def restore(self, ctx, source_guild_id: str, snapshot_id: str):
        """Non-destructive structure restore. Only bot owner, with target server admin access."""
        if not await self._authorize(ctx):
            return
        if self._lock.locked():
            return await ctx.send("Another snapshot operation is running.")
        guild = ctx.guild
        perms = guild.me.guild_permissions if guild.me else discord.Permissions.none()
        if not perms.manage_channels or not perms.manage_roles:
            return await ctx.send("Fatboy needs Manage Channels and Manage Roles (and a high enough role).")
        async with self._lock:
            try:
                root = await self._root()
                archive, data = await self._restore_read(ctx, root, source_guild_id, snapshot_id)
                if not await self._confirm(ctx, "RESTORE", snapshot_id):
                    return
                state_path = self._state_path(root, guild.id, source_guild_id, snapshot_id)
                state = read_json(state_path) if state_path.is_file() else {
                    "source_guild_id": source_guild_id, "snapshot_id": snapshot_id,
                    "destination_guild_id": str(guild.id), "role_map": {}, "channel_map": {},
                    "thread_map": {}, "created_roles": [], "created_channels": [],
                    "created_threads": [], "replay": {}, "warnings": []}
                if state["destination_guild_id"] != str(guild.id):
                    raise ValueError("Restore state belongs to another guild")
                warnings = state["warnings"]

                async def save():
                    private_write(state_path, state)

                live_roles, live_channels = {}, {}
                await self._role_map(guild, data["roles"], state, warnings, save, live_roles)
                # Categories before children. Existing channels remain untouched.
                items = sorted(data["channels"], key=lambda c: (c["type"] != "category", c["position"]))
                for ch in items:
                    old = ch["id"]
                    mapped_id = str(state["channel_map"].get(old, old))
                    matched = live_channels.get(mapped_id) or guild.get_channel(int(mapped_id))
                    if not matched:
                        category_id = ch.get("category_id")
                        parent_id = state["channel_map"].get(category_id) if category_id else None
                        category = (live_channels.get(str(parent_id)) or guild.get_channel(int(parent_id))) if parent_id else None
                        # Reuse a pre-existing channel only when unambiguous (type/name/category).
                        candidates = [c for c in guild.channels if c.name == ch["name"]
                                      and c.type.name == ch["type"]
                                      and object_id(c.category) == object_id(category)]
                        matched = candidates[0] if len(candidates) == 1 else None
                    if matched:
                        state["channel_map"][old] = str(matched.id)
                        await save()
                        continue
                    try:
                        category_id = ch.get("category_id")
                        target_id = state["channel_map"].get(category_id) if category_id else None
                        category = (live_channels.get(str(target_id)) or guild.get_channel(int(target_id))) if target_id else None
                        built = await self._create_channel(guild, ch, category,
                            self._mapped_overwrites(guild, ch, state["role_map"], live_roles), warnings)
                        if built:
                            state["channel_map"][old] = str(built.id)
                            state["created_channels"].append(str(built.id))
                            live_channels[str(built.id)] = built
                            await save()
                    except (discord.HTTPException, discord.Forbidden, TypeError, ValueError) as exc:
                        warnings.append(f"Channel {ch['name']}: {safe_text(exc)}")
                        await save()
                # Recreate conversation containers. Replay is a distinct opt-in step.
                for thread in data["threads"]:
                    old = thread["id"]
                    existing = guild.get_thread(int(state["thread_map"].get(old, old)))
                    if existing:
                        state["thread_map"][old] = str(existing.id)
                        continue
                    parent_target_id = state["channel_map"].get(thread["parent_id"])
                    if not parent_target_id:
                        warnings.append(f"Thread parent unavailable: {thread['name']}")
                        continue
                    parent = live_channels.get(str(parent_target_id)) or guild.get_channel(int(parent_target_id))
                    try:
                        if isinstance(parent, discord.ForumChannel):
                            created = await parent.create_thread(name=thread["name"],
                                content="Restored discussion container. Historical posts can be replayed by Fatboy.",
                                reason=REASON)
                            new_thread = created.thread
                        elif isinstance(parent, discord.TextChannel):
                            kind = (discord.ChannelType.private_thread if thread["type"] == "private_thread"
                                    else discord.ChannelType.public_thread)
                            new_thread = await parent.create_thread(name=thread["name"], type=kind, reason=REASON)
                        else:
                            warnings.append(f"Unsupported thread parent: {thread['name']}")
                            continue
                        state["thread_map"][old] = str(new_thread.id)
                        state["created_threads"].append(str(new_thread.id))
                        await save()
                    except (discord.HTTPException, discord.Forbidden, TypeError, ValueError) as exc:
                        warnings.append(f"Thread {thread['name']}: {safe_text(exc)}")
                        await save()
                await save()
                await ctx.send(f"**Structure restore finished**: {len(state['created_roles'])} new roles, "
                               f"{len(state['created_channels'])} new channels, "
                               f"{len(state['created_threads'])} threads; "
                               f"{len(warnings)} issues. Existing channels were not deleted or overwritten.\n"
                               f"Review the structure, then run `~sbackup replay {source_guild_id} {snapshot_id}` "
                               "if you want to republish the preserved message transcripts.")
            except (ValueError, FileNotFoundError, OSError, KeyError, json.JSONDecodeError) as exc:
                await ctx.send(f"Restore refused: {type(exc).__name__}: {safe_text(exc, 250)}")

    async def _replay_message(self, channel, message, archive, warnings):
        """Label and sanitize a historical post, never masquerade as original author."""
        when = (message.get("created_at") or "unknown date")[:19].replace("T", " ")
        author = safe_text(message.get("author_display_name") or message.get("author_name"), 70)
        author_id = safe_text(message.get("author_id"), 30)
        content = message.get("content") or ""
        header = f"[ARCHIVED {when} UTC] {author} (user {author_id}):\n"
        # Avoid generating mass notifications on replay, and split long messages.
        length = max(200, 1900 - len(header))
        parts = [content[i:i + length] for i in range(0, len(content), length)] or ["(attachment/embed or empty message)"]
        first = None
        attachments = message.get("attachments", [])
        files = []
        try:
            for item in attachments[:10]:
                media = item.get("media")
                if not media:
                    warnings.append(f"Unarchived attachment in message {message['id']}: {item.get('filename')}")
                    continue
                path = archive / media["path"]
                if not path.is_file():
                    warnings.append(f"Missing media: {media['path']}")
                    continue
                filename = safe_text(item.get("filename") or "attachment", 120).replace("/", "_").replace("\\", "_")
                files.append(discord.File(path, filename=filename, spoiler=bool(item.get("spoiler"))))
            first = await channel.send(header + parts[0], files=files,
                                       allowed_mentions=discord.AllowedMentions.none())
            for part in parts[1:]:
                await channel.send("[ARCHIVED continuation] " + part,
                                   allowed_mentions=discord.AllowedMentions.none())
            # Additional files, beyond the normal 10-file message cap.
            for offset in range(10, len(attachments), 10):
                batch = []
                try:
                    for item in attachments[offset:offset + 10]:
                        media = item.get("media")
                        if media and (archive / media["path"]).is_file():
                            batch.append(discord.File(archive / media["path"], filename=safe_text(
                                item.get("filename") or "attachment", 120).replace("/", "_")))
                    if batch:
                        await channel.send("[ARCHIVED additional attachments]", files=batch,
                                           allowed_mentions=discord.AllowedMentions.none())
                finally:
                    for f in batch:
                        f.close()
            if message.get("pinned") and first:
                try:
                    await first.pin(reason=REASON)
                except (discord.Forbidden, discord.HTTPException):
                    warnings.append(f"Could not pin archived message {message['id']}")
            return first
        finally:
            for f in files:
                f.close()

    @serversnapshot.command(name="replay")
    async def replay(self, ctx, source_guild_id: str, snapshot_id: str):
        """Repost full accessible transcript into ONLY channels this restore created."""
        if not await self._authorize(ctx):
            return
        if self._lock.locked():
            return await ctx.send("Another snapshot operation is running.")
        guild = ctx.guild
        async with self._lock:
            try:
                root = await self._root()
                archive, data = await self._restore_read(ctx, root, source_guild_id, snapshot_id)
                state_path = self._state_path(root, guild.id, source_guild_id, snapshot_id)
                state = read_json(state_path)
                if state["destination_guild_id"] != str(guild.id):
                    raise ValueError("Restore state belongs to another guild")
                if not await self._confirm(ctx, "REPLAY", snapshot_id):
                    return
                failures = state["warnings"]
                created = set(state["created_channels"]) | set(state["created_threads"])
                posted = 0
                skipped = 0
                for h in data["histories"]:
                    old_id = h["channel_id"]
                    mapped = state["channel_map"].get(old_id) or state["thread_map"].get(old_id)
                    if not mapped or mapped not in created:
                        skipped += 1
                        continue  # NEVER replay into a pre-existing channel
                    channel = guild.get_channel_or_thread(int(mapped))
                    if not channel:
                        try:
                            channel = await guild.fetch_channel(int(mapped))
                        except (discord.HTTPException, discord.Forbidden):
                            failures.append(f"Restored channel no longer accessible: {mapped}")
                            continue
                    historyfile = archive / "messages" / (old_id + ".jsonl")
                    if not historyfile.is_file():
                        continue
                    last = state["replay"].get(old_id, "0")
                    with historyfile.open("r", encoding="utf-8") as stream:
                        for raw in stream:
                            message = json.loads(raw)
                            if int(message["id"]) <= int(last):
                                continue
                            try:
                                await self._replay_message(channel, message, archive, failures)
                                state["replay"][old_id] = message["id"]
                                # Crash-aware checkpoint; at worst one post duplicates after a crash.
                                private_write(state_path, state)
                                posted += 1
                            except (discord.HTTPException, discord.Forbidden, OSError, ValueError) as exc:
                                failures.append(f"Replay {old_id}/{message['id']}: {safe_text(exc)}")
                                private_write(state_path, state)
                                break  # preserve order; retry safely from failed message next time
                    if posted and posted % 100 == 0:
                        await ctx.send(f"Replayed {posted:,} historical messages so far...")
                private_write(state_path, state)
                await ctx.send(f"**Replay pass finished:** {posted:,} messages posted by Fatboy; "
                               f"{skipped} pre-existing/unrestored channels skipped; "
                               f"{len(failures)} cumulative warnings. Messages keep their original "
                               "timestamps and authors in labelled text, not as Discord message metadata. "
                               "Run the same command again to resume remaining history.")
            except (ValueError, FileNotFoundError, OSError, KeyError, json.JSONDecodeError) as exc:
                await ctx.send(f"Replay refused: {type(exc).__name__}: {safe_text(exc, 250)}")

    @serversnapshot.command(name="settings")
    async def restore_settings(self, ctx, source_guild_id: str, snapshot_id: str):
        """Explicit opt-in to apply guild name, icon, and a few supported moderation settings."""
        if not await self._authorize(ctx):
            return
        if self._lock.locked():
            return await ctx.send("Another snapshot operation is running.")
        if not ctx.guild.me or not ctx.guild.me.guild_permissions.manage_guild:
            return await ctx.send("Fatboy needs Manage Server to apply guild settings.")
        async with self._lock:
            try:
                root = await self._root()
                archive, data = await self._restore_read(ctx, root, source_guild_id, snapshot_id)
                if not await self._confirm(ctx, "SETTINGS", snapshot_id):
                    return
                saved = data["guild"]
                results = []
                level = discord.VerificationLevel[saved["verification_level"].split(".")[-1]]
                content_filter = discord.ContentFilter[saved["explicit_content_filter"].split(".")[-1]]
                notifications = discord.NotificationLevel[saved["default_notifications"].split(".")[-1]]
                opts = {"name": saved["name"], "verification_level": level,
                        "explicit_content_filter": content_filter,
                        "default_notifications": notifications,
                        "afk_timeout": saved["afk_timeout"]}
                if data.get("guild_media", {}).get("icon"):
                    icon_file = archive / data["guild_media"]["icon"]["path"]
                    opts["icon"] = icon_file.read_bytes()
                try:
                    await ctx.guild.edit(reason=REASON, **opts)
                    results.append("Server name, moderation defaults, AFK timeout and available icon updated")
                except (discord.HTTPException, discord.Forbidden, ValueError) as exc:
                    results.append("Some guild settings not updated: " + safe_text(exc))
                # Restoring @everyone permissions changes security on live server:
                # intentionally leave it to a separate explicit action rather than here.
                await ctx.send("**Settings restore:** " + "; ".join(results) +
                               ". System channels, integration-specific settings and community configuration "
                               "may need manual review.")
            except (ValueError, FileNotFoundError, OSError, KeyError, json.JSONDecodeError) as exc:
                await ctx.send("Settings restore refused: " + safe_text(exc))

    @serversnapshot.command(name="assets")
    async def restore_assets(self, ctx, source_guild_id: str, snapshot_id: str):
        """Explicit opt-in to upload saved server emojis and static sticker assets."""
        if not await self._authorize(ctx):
            return
        if self._lock.locked():
            return await ctx.send("Another snapshot operation is running.")
        if not ctx.guild.me or not ctx.guild.me.guild_permissions.manage_emojis_and_stickers:
            return await ctx.send("Fatboy needs Manage Expressions / Manage Emojis and Stickers.")
        async with self._lock:
            try:
                root = await self._root()
                archive, data = await self._restore_read(ctx, root, source_guild_id, snapshot_id)
                if not await self._confirm(ctx, "ASSETS", snapshot_id):
                    return
                made_emojis, made_stickers, warnings = 0, 0, []
                existing_emoji_ids = {str(e.id) for e in ctx.guild.emojis}
                existing_emoji_names = {e.name for e in ctx.guild.emojis}
                for e in data["emojis"]:
                    if e["id"] in existing_emoji_ids or e["name"] in existing_emoji_names:
                        continue
                    media = e.get("media")
                    if not media:
                        warnings.append("Not archived: emoji " + e["name"])
                        continue
                    try:
                        raw = (archive / media["path"]).read_bytes()
                        await ctx.guild.create_custom_emoji(name=e["name"], image=raw, reason=REASON)
                        made_emojis += 1
                    except (discord.HTTPException, discord.Forbidden, OSError, ValueError) as exc:
                        warnings.append("Emoji " + e["name"] + ": " + safe_text(exc))
                stickers = {s.name for s in ctx.guild.stickers}
                for s in data["stickers"]:
                    if s["name"] in stickers:
                        continue
                    media = s.get("media")
                    if not media:
                        warnings.append("Not archived: sticker " + s["name"])
                        continue
                    try:
                        asset = archive / media["path"]
                        # Discord enforces format/size limits; inaccessible animated assets
                        # remain in archive even if re-upload is not supported.
                        with asset.open("rb") as fp:
                            sticker_file = discord.File(fp, filename=s["name"] + ".png")
                            await ctx.guild.create_sticker(name=s["name"],
                                description=s.get("description") or "Restored sticker",
                                emoji=s.get("emoji") or "📦", file=sticker_file, reason=REASON)
                        made_stickers += 1
                    except (discord.HTTPException, discord.Forbidden, OSError, ValueError, TypeError) as exc:
                        warnings.append("Sticker " + s["name"] + ": " + safe_text(exc))
                await ctx.send(f"**Asset restore:** {made_emojis} emojis, {made_stickers} stickers "
                               f"uploaded; {len(warnings)} skipped/failed. "
                               "Some asset formats and server limits require manual handling.")
            except (ValueError, FileNotFoundError, OSError, KeyError, json.JSONDecodeError) as exc:
                await ctx.send("Assets restore refused: " + safe_text(exc))

    @serversnapshot.command(name="members")
    async def restore_members(self, ctx, source_guild_id: str, snapshot_id: str):
        """Opt-in to reassign captured roles to members who are still in target server."""
        if not await self._authorize(ctx):
            return
        if self._lock.locked():
            return await ctx.send("Another snapshot operation is running.")
        if not ctx.guild.me or not ctx.guild.me.guild_permissions.manage_roles:
            return await ctx.send("Fatboy needs Manage Roles for this operation.")
        async with self._lock:
            try:
                root = await self._root()
                _, data = await self._restore_read(ctx, root, source_guild_id, snapshot_id)
                state_path = self._state_path(root, ctx.guild.id, source_guild_id, snapshot_id)
                state = read_json(state_path)
                if not await self._confirm(ctx, "MEMBERS", snapshot_id):
                    return
                if not self.bot.intents.members:
                    return await ctx.send("Enable Server Members intent for reliable member-role restoration.")
                # Fetch the complete destination roster, not just the gateway cache.
                roster = {m.id: m async for m in ctx.guild.fetch_members(limit=None)}
                updated, missing, issues = 0, 0, 0
                for saved in data["members"]:
                    member = roster.get(int(saved["id"]))
                    if not member:
                        missing += 1
                        continue
                    restored_roles = []
                    for old_id in saved["role_ids"]:
                        mapped = state["role_map"].get(old_id)
                        role = ctx.guild.get_role(int(mapped)) if mapped else None
                        if role and not role.managed and role < ctx.guild.me.top_role and role not in member.roles:
                            restored_roles.append(role)
                    if not restored_roles:
                        continue
                    try:
                        await member.add_roles(*restored_roles, reason=REASON)
                        updated += 1
                    except (discord.HTTPException, discord.Forbidden):
                        issues += 1
                await ctx.send(f"**Member-role restore:** {updated} members received missing roles, "
                               f"{missing} snapshot members absent from this server, {issues} errors. "
                               "Existing roles are never removed; nicknames and bot installations are unchanged.")
            except (ValueError, FileNotFoundError, OSError, KeyError, json.JSONDecodeError,
                    discord.HTTPException, discord.Forbidden) as exc:
                await ctx.send("Member-role restore refused: " + safe_text(exc))

    @serversnapshot.command(name="quota")
    async def quota(self, ctx, max_gib: int = -1):
        """View/set total attachment download quota in GiB; 0 = unlimited, space reserve still applies."""
        if max_gib == -1:
            value = await self.config.max_gib()
            return await ctx.send(f"Snapshot media quota: {value or 'unlimited'} GiB; "
                                  "512 MiB free-space reserve always enforced.")
        if not 0 <= max_gib <= 10000:
            return await ctx.send("Quota must be 0 (unlimited) or 1–10000 GiB.")
        await self.config.max_gib.set(max_gib)
        await ctx.send(f"Snapshot media quota updated to {max_gib or 'unlimited'} GiB.")