"""Load a ChatGPT-generated JSON theme, preview, and safely apply it in Discord."""

from __future__ import annotations

import asyncio
import copy
import io
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import discord
from redbot.core import Config, commands
from redbot.core.data_manager import cog_data_path


MAX_TEMPLATE_BYTES = 256_000
MAX_CHANNELS = 100
MAX_CATEGORIES = 25
MAX_ROLES = 40
MAX_ARCHIVE_PER_CATEGORY = 45
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
ROLE_PERMS = {
    "view_channel", "send_messages", "read_message_history", "add_reactions",
    "attach_files", "embed_links", "connect", "speak", "stream",
    "use_external_emojis", "use_application_commands", "create_public_threads",
    "create_private_threads", "send_messages_in_threads", "manage_messages",
    "manage_threads", "manage_webhooks", "mute_members", "deafen_members",
    "move_members", "use_voice_activation", "priority_speaker", "manage_nicknames",
    "change_nickname", "send_tts_messages", "manage_events",
}
CHANNEL_PERMS = ROLE_PERMS | {"manage_channels"}


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def validate_template(data: Any) -> Dict[str, Any]:
    """Do not accept arbitrary Discord permissions, IDs, or unbounded structures."""
    if not isinstance(data, dict):
        raise ValueError("The theme must be a JSON object.")
    unknown = set(data) - {
        "name", "roles", "categories", "rules", "rules_channel",
        "update_existing_roles", "archive_read_roles",
    }
    if unknown:
        raise ValueError(f"Unknown theme field(s): {', '.join(sorted(unknown))}")
    if not isinstance(data.get("name"), str) or not 1 <= len(data["name"]) <= 100:
        raise ValueError("'name' must be 1–100 characters.")
    roles, categories = data.get("roles", []), data.get("categories", [])
    if not isinstance(roles, list) or len(roles) > MAX_ROLES:
        raise ValueError(f"'roles' must be a list (max {MAX_ROLES}).")
    if not isinstance(categories, list) or not 1 <= len(categories) <= MAX_CATEGORIES:
        raise ValueError(f"'categories' must contain 1–{MAX_CATEGORIES} categories.")
    role_names, category_names, paths = set(), set(), set()
    for role in roles:
        if not isinstance(role, dict):
            raise ValueError("Each role must be an object.")
        if set(role) - {"name", "color", "hoist", "mentionable", "permissions"}:
            raise ValueError(f"Unknown role field(s): {set(role) - {'name', 'color', 'hoist', 'mentionable', 'permissions'}}")
        name = role.get("name")
        if not isinstance(name, str) or not 1 <= len(name) <= 100 or name == "@everyone":
            raise ValueError("Role names must be 1–100 characters and not @everyone.")
        if name.casefold() in role_names:
            raise ValueError(f"Duplicate role: {name}")
        role_names.add(name.casefold())
        if "color" in role and (not isinstance(role["color"], str) or not COLOR.fullmatch(role["color"])):
            raise ValueError(f"Role {name}: 'color' must look like #36A1CB.")
        for key in ("hoist", "mentionable"):
            if key in role and not isinstance(role[key], bool):
                raise ValueError(f"Role {name}: {key} must be true/false.")
        validate_perms(role.get("permissions", {}), ROLE_PERMS, f"role {name}")
    channel_count = 0
    for cat in categories:
        if not isinstance(cat, dict):
            raise ValueError("Each category must be an object.")
        if set(cat) - {"name", "overwrites", "channels"}:
            raise ValueError("Unknown category field: " + ", ".join(set(cat) - {"name", "overwrites", "channels"}))
        name = cat.get("name")
        if not isinstance(name, str) or not 1 <= len(name) <= 100:
            raise ValueError("Category names must be 1–100 characters.")
        if name.casefold() in category_names:
            raise ValueError(f"Duplicate category: {name}")
        category_names.add(name.casefold())
        validate_overwrites(cat.get("overwrites", {}), f"category {name}")
        channels = cat.get("channels", [])
        if not isinstance(channels, list) or len(channels) > 50:
            raise ValueError(f"Category {name}: 'channels' must be a list with at most 50 entries.")
        names_here = set()
        for ch in channels:
            if not isinstance(ch, dict):
                raise ValueError("Each channel must be an object.")
            unexpected = set(ch) - {
                "name", "type", "topic", "nsfw", "slowmode", "user_limit", "overwrites", "messages"
            }
            if unexpected:
                raise ValueError("Unknown channel field: " + ", ".join(sorted(unexpected)))
            cname = ch.get("name")
            kind = ch.get("type", "text")
            if not isinstance(cname, str) or not 1 <= len(cname) <= 100:
                raise ValueError(f"Category {name}: channel name must be 1–100 characters.")
            if cname.casefold() in names_here:
                raise ValueError(f"Duplicate channel in {name}: {cname}")
            if kind not in ("text", "voice"):
                raise ValueError(f"{name}/{cname}: supported types are text and voice.")
            if kind == "voice" and any(k in ch for k in ("topic", "nsfw", "slowmode")):
                raise ValueError(f"{name}/{cname}: voice channels do not use topic/nsfw/slowmode here.")
            if kind == "text" and "user_limit" in ch:
                raise ValueError(f"{name}/{cname}: user_limit is voice only.")
            names_here.add(cname.casefold())
            paths.add(f"{name}/{cname}")
            channel_count += 1
            validate_overwrites(ch.get("overwrites", {}), f"channel {cname}")
            if "topic" in ch and (not isinstance(ch["topic"], str) or len(ch["topic"]) > 1024):
                raise ValueError(f"{cname}: topic may contain up to 1024 characters.")
            if "nsfw" in ch and not isinstance(ch["nsfw"], bool):
                raise ValueError(f"{cname}: nsfw must be true/false.")
            if "slowmode" in ch and (type(ch["slowmode"]) is not int or not 0 <= ch["slowmode"] <= 21600):
                raise ValueError(f"{cname}: slowmode must be 0–21600 seconds.")
            if "user_limit" in ch and (type(ch["user_limit"]) is not int or not 0 <= ch["user_limit"] <= 99):
                raise ValueError(f"{cname}: user_limit must be 0–99.")
            messages = ch.get("messages", [])
            if kind == "voice" and messages:
                raise ValueError(f"Voice channel {cname} cannot have starter messages.")
            if not isinstance(messages, list) or len(messages) > 20:
                raise ValueError(f"{cname}: messages must be an array (max 20).")
            for msg in messages:
                validate_message(msg, f"{cname} starter message")
    if channel_count > MAX_CHANNELS:
        raise ValueError(f"Theme exceeds the {MAX_CHANNELS}-channel limit.")
    if "rules_channel" in data:
        if not isinstance(data["rules_channel"], str) or data["rules_channel"] not in paths:
            raise ValueError("rules_channel must be a valid 'Category/channel' path in this theme.")
        rcat, rchan = data["rules_channel"].split("/", 1)
        rdef = next(ch for cat in categories if cat["name"] == rcat for ch in cat["channels"] if ch["name"] == rchan)
        if rdef.get("type", "text") != "text":
            raise ValueError("rules_channel must point to a text channel.")
    rules = data.get("rules", [])
    if not isinstance(rules, list) or len(rules) > 30:
        raise ValueError("'rules' must be a list (max 30).")
    for item in rules:
        if not isinstance(item, str) or not 1 <= len(item) <= 1800:
            raise ValueError("Rules must be nonempty strings of at most 1800 characters.")
    if rules and not data.get("rules_channel"):
        raise ValueError("Set 'rules_channel' to publish rules.")
    if "update_existing_roles" in data and not isinstance(data["update_existing_roles"], bool):
        raise ValueError("update_existing_roles must be true/false.")
    archive_roles = data.get("archive_read_roles", [])
    if not isinstance(archive_roles, list) or not all(isinstance(x, str) for x in archive_roles):
        raise ValueError("archive_read_roles must be an array of role names.")
    return data


def validate_message(msg: Any, label: str) -> None:
    if isinstance(msg, str):
        content = msg
    elif (isinstance(msg, dict) and set(msg) <= {"content", "pin"}
          and isinstance(msg.get("content"), str) and isinstance(msg.get("pin", False), bool)):
        content = msg["content"]
    else:
        raise ValueError(f"{label} must be text or {{'content': text, 'pin': bool}}.")
    if not 1 <= len(content) <= 2000:
        raise ValueError(f"{label} must be 1–2000 characters.")


def validate_perms(items: Any, allowed: set, context: str) -> None:
    if not isinstance(items, dict):
        raise ValueError(f"{context}: permissions must be an object.")
    for name, value in items.items():
        if name not in allowed or not isinstance(value, bool):
            raise ValueError(f"{context}: invalid permission {name!r}; allowed values are true/false.")


def validate_overwrites(items: Any, context: str) -> None:
    if not isinstance(items, dict):
        raise ValueError(f"{context}: overwrites must be an object.")
    for role_name, permissions in items.items():
        if not isinstance(role_name, str) or not role_name:
            raise ValueError(f"{context}: invalid overwrite role.")
        validate_perms(permissions, CHANNEL_PERMS, f"{context} overwrite for {role_name}")


def snapshot_overwrites(channel: discord.abc.GuildChannel) -> list:
    values = []
    for target, overwrite in channel.overwrites.items():
        if isinstance(target, discord.Role):
            kind = "role"
        elif isinstance(target, discord.Member):
            kind = "member"
        elif isinstance(target, discord.Object):
            kind = "role" if target.type is discord.Role else "member"
        else:
            continue
        allow, deny = overwrite.pair()
        values.append([kind, target.id, allow.value, deny.value])
    return values


def restore_overwrites(guild: discord.Guild, values: list) -> dict:
    result = {}
    for kind, obj_id, allow, deny in values:
        target = guild.get_role(obj_id) if kind == "role" else guild.get_member(obj_id)
        # Missing members in cache still need their explicit overwrite restored.
        if target is None:
            target = discord.Object(id=obj_id, type=discord.Role if kind == "role" else discord.User)
        result[target] = discord.PermissionOverwrite.from_pair(
            discord.Permissions(allow), discord.Permissions(deny)
        )
    return result


def _matching_starter_channel(guild: discord.Guild, definition: dict):
    """A starter channel with this name/type anywhere is retained as-is."""
    wanted = definition["name"].casefold()
    channel_type = discord.VoiceChannel if definition.get("type", "text") == "voice" else discord.TextChannel
    return next((ch for ch in guild.channels
                 if isinstance(ch, channel_type) and ch.name.casefold() == wanted), None)


def starter_changes(guild: discord.Guild, theme: dict) -> dict:
    """Non-mutating inventory. Existing channels are never moved or edited."""
    categories_to_create = []
    channels_to_create = []
    existing_channels = []
    reused_categories = []
    for cat in theme["categories"]:
        existing_category = next(
            (c for c in guild.categories if c.name.casefold() == cat["name"].casefold()), None
        )
        missing = []
        for channel in cat["channels"]:
            match = _matching_starter_channel(guild, channel)
            if match:
                existing_channels.append((cat["name"], channel["name"], match))
            else:
                missing.append(channel)
                channels_to_create.append((cat["name"], channel["name"]))
        if missing:
            if existing_category is None:
                categories_to_create.append(cat["name"])
            else:
                reused_categories.append(cat["name"])
    return {
        "new_categories": categories_to_create,
        "new_channels": channels_to_create,
        "existing_channels": existing_channels,
        "reused_categories": reused_categories,
    }


class Revamp(commands.Cog):
    """Apply a theme file designed externally, preserving old channel messages."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=912800556321778401, force_registration=True)
        self.config.register_guild(history=[], protected_channels=[], selected_mode="custom")
        self._locks: Dict[int, asyncio.Lock] = {}

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    def _root(self, guild_id: int) -> Path:
        folder = cog_data_path(self) / "themes" / str(guild_id)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _shared_root(self) -> Path:
        folder = cog_data_path(self) / "shared_themes"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _path(self, guild_id: int, slug: str) -> Path:
        if not SLUG.fullmatch(slug):
            raise ValueError("Theme IDs: 2–40 lowercase letters, digits, _ or -, starting with a letter/digit.")
        return self._root(guild_id) / f"{slug}.json"

    def _locate(self, guild_id: int, slug: str) -> Path:
        local = self._path(guild_id, slug)
        if local.is_file():
            return local
        shared = self._shared_root() / f"{slug}.json"
        if shared.is_file():
            return shared
        raise ValueError(f"Theme {slug!r} not found. Use `revamp themes` or `revamp import`.")

    def _load(self, guild_id: int, slug: str) -> dict:
        return validate_template(json.loads(self._locate(guild_id, slug).read_text(encoding="utf-8")))

    async def _append_history(self, guild: discord.Guild, record: dict) -> None:
        async with self.config.guild(guild).history() as history:
            history.append(copy.deepcopy(record))

    async def _patch(self, guild: discord.Guild, op_id: str, **changes) -> None:
        async with self.config.guild(guild).history() as history:
            for op in history:
                if op["id"] == op_id:
                    op.update(copy.deepcopy(changes))
                    return
        raise RuntimeError("Revamp history entry not found.")

    async def _get_record(self, guild: discord.Guild, op_id: str) -> dict:
        for entry in reversed(await self.config.guild(guild).history()):
            if entry["id"] == op_id:
                return entry
        raise ValueError("Revamp history entry not found.")

    async def _latest_active(self, guild: discord.Guild) -> Optional[dict]:
        for entry in reversed(await self.config.guild(guild).history()):
            if entry.get("status") in ("running", "done", "failed", "rollback_failed"):
                return entry
        return None

    def _role_lookup(self, guild: discord.Guild, theme: dict) -> dict:
        lookup = {"@everyone": guild.default_role}
        for role in guild.roles:
            lookup[role.name] = role
        for r in theme.get("roles", []):
            lookup.setdefault(r["name"], None)
        for cat in theme["categories"]:
            for items in [cat.get("overwrites", {})] + [ch.get("overwrites", {}) for ch in cat["channels"]]:
                for key in items:
                    if key not in lookup:
                        raise ValueError(f"Missing role {key!r}. Declare it in the theme or create it first.")
        for key in theme.get("archive_read_roles", []):
            if key not in lookup or key == "@everyone":
                raise ValueError(f"Unknown archive_read_role {key!r}; it may not be @everyone.")
        return lookup

    def _overwrites(self, spec: dict, lookup: dict) -> dict:
        result = {}
        for name, values in spec.items():
            role = lookup.get(name)
            if role is None:
                raise RuntimeError(f"Role {name!r} was not created.")
            result[role] = discord.PermissionOverwrite(**values)
        return result

    def _bot_post_overwrite(self, guild: discord.Guild, overwrites: dict) -> dict:
        # Keep the bot able to post rules and access its own newly created channels.
        result = dict(overwrites)
        if guild.me:
            result[guild.me] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                manage_messages=True,
            )
        return result

    async def _archive_candidates(self, ctx) -> tuple:
        guild = ctx.guild
        protected = set(await self.config.guild(guild).protected_channels())
        protected.add(ctx.channel.id)
        for special in (guild.system_channel, guild.rules_channel, guild.public_updates_channel, guild.afk_channel):
            if special:
                protected.add(special.id)
        candidates = []
        skipped = []
        for ch in guild.channels:
            if ch.id in protected:
                skipped.append(f"#{ch.name} (protected)")
            elif isinstance(ch, (discord.TextChannel, discord.VoiceChannel)):
                if isinstance(ch, discord.TextChannel) and ch.is_news():
                    continue
                # Keep private staff, moderation, bot and restricted channels intact.
                if not ch.permissions_for(guild.default_role).view_channel:
                    skipped.append(f"#{ch.name} (private/restricted)")
                else:
                    candidates.append(ch)
            # Deliberately leave forums, stages, announcements, categories untouched.
        return candidates, skipped

    def _check_bot(self, guild: discord.Guild, theme: dict, archive: bool, *, reuse_existing: bool = False) -> None:
        me = guild.me
        if me is None:
            raise ValueError("Bot member not available in the guild cache.")
        perms = me.guild_permissions
        if not perms.manage_channels:
            raise ValueError("Bot needs Manage Channels.")
        if theme.get("roles") and not perms.manage_roles:
            raise ValueError("Bot needs Manage Roles to create/edit role definitions.")
        if not perms.send_messages:
            raise ValueError("Bot needs Send Messages to write welcome/rules posts.")
        needs_pins = bool(theme.get("rules")) or any(
            isinstance(msg, dict) and msg.get("pin")
            for cat in theme["categories"] for ch in cat["channels"]
            for msg in ch.get("messages", [])
        )
        if needs_pins and not perms.manage_messages:
            raise ValueError("Bot needs Manage Messages to pin rules and welcome posts.")
        if archive and not perms.view_channel:
            raise ValueError("Bot needs View Channels to archive existing channels.")
        highest = me.top_role.position
        if theme.get("update_existing_roles", False):
            for r in theme.get("roles", []):
                match = discord.utils.get(guild.roles, name=r["name"])
                if match and (match.managed or match.position >= highest):
                    raise ValueError(f"Cannot edit existing role {r['name']}: managed or above the bot.")
        if reuse_existing:
            changes = starter_changes(guild, theme)
            new_count = len(changes["new_categories"]) + len(changes["new_channels"])
        else:
            new_count = len(theme["categories"]) + sum(len(c["channels"]) for c in theme["categories"])
        if len(guild.channels) + new_count > 500:
            raise ValueError("New layout exceeds Discord's 500-channel server limit.")
        if len(guild.roles) + sum(discord.utils.get(guild.roles, name=r["name"]) is None for r in theme.get("roles", [])) > 250:
            raise ValueError("New roles exceed Discord's role limit.")

    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.group(name="revamp", invoke_without_command=True)
    async def revamp(self, ctx):
        """Three steps: upload North's theme, preview, apply."""
        await ctx.send(
            f"**Revamp:** Use `{ctx.clean_prefix}revamp starter` to review a new server and select a "
            f"non-destructive starter layout, OR attach a JSON theme with `{ctx.clean_prefix}revamp load`. "
            f"Then use `{ctx.clean_prefix}revamp preview` and `{ctx.clean_prefix}revamp apply`. "
            f"Use `{ctx.clean_prefix}revamp undo` to reverse the previous revamp. "
            "Custom revamps archive eligible old public channels; starter mode never archives "
            "or edits existing channels."
        )

    @revamp.command(name="load")
    async def load_theme(self, ctx):
        """Attach the JSON theme produced in chat; one pending theme per guild."""
        if self._lock(ctx.guild.id).locked():
            return await ctx.send("A revamp is running. Please retry when it has finished.")
        try:
            if not ctx.message.attachments:
                return await ctx.send(f"Attach the JSON theme file to the same message as `{ctx.clean_prefix}revamp load`.")
            attachment = ctx.message.attachments[0]
            if not attachment.filename.lower().endswith(".json") or attachment.size > MAX_TEMPLATE_BYTES:
                raise ValueError("Theme must be a .json file of at most 256 KB.")
            data = await attachment.read()
            if len(data) > MAX_TEMPLATE_BYTES:
                raise ValueError("Theme file exceeds the 256 KB limit.")
            theme = validate_template(json.loads(data.decode("utf-8-sig")))
            self._role_lookup(ctx.guild, theme)
            dest = self._path(ctx.guild.id, "selected")
            dest.write_text(json.dumps(theme, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            await self.config.guild(ctx.guild).selected_mode.set("custom")
            await ctx.send(
                f"Loaded **{theme['name']}** for **{ctx.guild.name}**. "
                f"No Discord settings have changed. Run `{ctx.clean_prefix}revamp preview`."
            )
        except (ValueError, UnicodeError, OSError, json.JSONDecodeError) as exc:
            await ctx.send(f"Theme not loaded: {exc}")

    @revamp.command(name="starter")
    async def starter(self, ctx):
        """Review a server and select a safe starter layout, without changing Discord."""
        if self._lock(ctx.guild.id).locked():
            return await ctx.send("A revamp is already running. Please retry after it finishes.")
        try:
            theme = validate_template(json.loads(
                Path(__file__).with_name("starter-theme.json").read_text(encoding="utf-8")
            ))
            self._role_lookup(ctx.guild, theme)
            self._check_bot(ctx.guild, theme, False, reuse_existing=True)
            changes = starter_changes(ctx.guild, theme)
            dest = self._path(ctx.guild.id, "selected")
            dest.write_text(json.dumps(theme, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            await self.config.guild(ctx.guild).selected_mode.set("starter")
            overview = (
                f"**Server review: {ctx.guild.name}**\n"
                f"Currently: **{len(ctx.guild.categories)} categories**, "
                f"**{sum(isinstance(c, (discord.TextChannel, discord.VoiceChannel)) for c in ctx.guild.channels)} text/voice channels**, "
                f"**{len(ctx.guild.roles)-1} non-default roles**.\n"
                f"Starter would add **{len(changes['new_categories'])} categories** and "
                f"**{len(changes['new_channels'])} channels**; "
                f"reuse **{len(changes['reused_categories'])} categories** and leave "
                f"**{len(changes['existing_channels'])} matching channels unchanged**.\n"
                "Nothing on Discord has changed. Old channels stay where they are, with their messages and permissions. "
                f"Run `{ctx.clean_prefix}revamp preview` to see the plan, then `{ctx.clean_prefix}revamp apply` to confirm. "
                f"Upload one of our own themes with `{ctx.clean_prefix}revamp load` whenever you want instead."
            )
            await ctx.send(overview)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            await ctx.send(f"Cannot prepare starter layout: {exc}")

    async def _plan_text(self, ctx, slug: str, archive: bool, *, reuse_existing: bool = False) -> str:
        theme = self._load(ctx.guild.id, slug)
        self._role_lookup(ctx.guild, theme)
        self._check_bot(ctx.guild, theme, archive, reuse_existing=reuse_existing)
        candidates, skipped = await self._archive_candidates(ctx) if archive else ([], [])
        existing_roles = sum(discord.utils.get(ctx.guild.roles, name=r["name"]) is not None
                             for r in theme.get("roles", []))
        if reuse_existing:
            changes = starter_changes(ctx.guild, theme)
            cat_count = len(changes["new_categories"])
            new_channels = len(changes["new_channels"])
            preserved = len(changes["existing_channels"])
            rule_will_be_posted = any(
                f"{category}/{channel}" == theme.get("rules_channel")
                for category, channel in changes["new_channels"]
            )
            return (
                f"**Starter preview: {theme['name']}**\n"
                f"• Add **{cat_count} categories**, **{new_channels} text/voice channels**, "
                f"and **{len(theme.get('roles', []))-existing_roles} roles** "
                f"({existing_roles} existing roles kept as-is).\n"
                f"• Keep **{preserved} matching channels** without editing, moving, or posting into them.\n"
                f"• Rules: **{'post and pin in a new #rules channel' if rule_will_be_posted else 'existing #rules will be left alone'}**.\n"
                "• **No archiving, deleting, renaming, or changing existing channel permissions.**\n"
                "• New channels: "
                + (", ".join(f"#{name}" for _, name in changes["new_channels"][:15]) or "none")
                + (f" (+{new_channels-15} more)" if new_channels > 15 else "")
                + "\n• Review existing channels and staff access after deployment; no users are assigned new roles automatically."
            )
        total = sum(len(cat["channels"]) for cat in theme["categories"])
        n_archive = len(candidates) if archive else 0
        extra_archives = (n_archive + MAX_ARCHIVE_PER_CATEGORY - 1) // MAX_ARCHIVE_PER_CATEGORY
        if len(ctx.guild.channels) + len(theme["categories"]) + total + extra_archives > 500:
            raise ValueError("Layout + archives exceed Discord's 500-channel limit.")
        return (
            f"**Preview: {theme['name']}** (`{slug}`)\n"
            f"• Create **{len(theme['categories'])}** categories and **{total}** channels.\n"
            f"• Define **{len(theme.get('roles', []))}** roles ({existing_roles} already exist); "
            f"update existing roles: **{'yes' if theme.get('update_existing_roles') else 'no'}**.\n"
            f"• Publish **{len(theme.get('rules', []))}** rule entries and starter messages.\n"
            f"• Archive existing standard text/voice channels: **{'yes' if archive else 'no'}** "
            f"({n_archive} eligible; {len(skipped)} protected; forums/stages/announcements ignored).\n"
            "• Preserve old channel history and record original positions/overwrites for restoration.\n"
            "• **Never deletes old channels or messages.** New posts and roles may require manual cleanup on rollback.\n"
            + "• Eligible old channels: " + (", ".join(f"#{c.name}" for c in candidates[:12]) or "none")
            + (f" … and {len(candidates)-12} more" if len(candidates) > 12 else "")
        )

    @revamp.command(name="preview")
    async def preview_theme(self, ctx):
        """Show exactly what happens; makes no server changes."""
        try:
            starter = await self.config.guild(ctx.guild).selected_mode() == "starter"
            await ctx.send(await self._plan_text(ctx, "selected", not starter, reuse_existing=starter))
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            await ctx.send(f"Cannot preview: {exc}. Use `{ctx.clean_prefix}revamp starter` or `{ctx.clean_prefix}revamp load` first.")

    @revamp.command(name="apply")
    async def apply_theme(self, ctx):
        """Apply the selected theme after preview and typed confirmation."""
        slug = "selected"
        mode = await self.config.guild(ctx.guild).selected_mode()
        reuse_existing = mode == "starter"
        archive_old = not reuse_existing
        lock = self._lock(ctx.guild.id)
        if lock.locked():
            return await ctx.send("A revamp operation is already running for this server.")
        try:
            plan = await self._plan_text(ctx, slug, archive_old, reuse_existing=reuse_existing)
            selected_theme_before = self._load(ctx.guild.id, slug)
            latest = await self._latest_active(ctx.guild)
            # Finished layouts can be revved again later (e.g. starter -> custom).
            # Each operation has its own rollback record. Block failed/in-progress runs.
            if latest and latest.get("status") != "done":
                return await ctx.send(f"A previous revamp needs attention. Use `{ctx.clean_prefix}revamp undo` to recover it before applying another theme.")
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            return await ctx.send(f"Cannot apply: {exc}")
        phrase = f"REVAMP {slug} {ctx.guild.id}"
        await ctx.send(plan + f"\n**To proceed, type exactly:** `{phrase}` within 90 seconds. Otherwise nothing happens.")
        try:
            await self.bot.wait_for(
                "message", timeout=90,
                check=lambda m: m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and m.content == phrase,
            )
        except asyncio.TimeoutError:
            return await ctx.send("No confirmation received; server unchanged.")
        async with lock:
            try:
                # Re-check when the confirmation is received, not just when previewed.
                if await self.config.guild(ctx.guild).selected_mode() != mode:
                    return await ctx.send("Selected theme changed during confirmation. Preview again.")
                theme = self._load(ctx.guild.id, slug)
                if theme != selected_theme_before:
                    return await ctx.send("Selected theme changed during confirmation. Preview again.")
                self._role_lookup(ctx.guild, theme)
                self._check_bot(ctx.guild, theme, archive_old, reuse_existing=reuse_existing)
                candidates, _ = await self._archive_candidates(ctx)
                op_id = uuid.uuid4().hex[:10]
                record = {
                    "id": op_id, "slug": slug, "name": theme["name"], "mode": mode, "date": stamp(),
                    "status": "running", "archive_requested": archive_old,
                    "created_roles": [], "edited_roles": [], "created_categories": [],
                    "created_channels": [], "archived": [], "rollback_categories": [],
                }
                await self._append_history(ctx.guild, record)
                await ctx.send(f"Revamp `{op_id}` started. Recording every change for review.")
                lookup = self._role_lookup(ctx.guild, theme)
                # Step 1: roles. Existing roles are unchanged unless opted in by theme.
                for role_def in theme.get("roles", []):
                    name = role_def["name"]
                    existing = discord.utils.get(ctx.guild.roles, name=name)
                    role_props = {}
                    if "color" in role_def:
                        role_props["colour"] = discord.Colour(int(role_def["color"][1:], 16))
                    if "hoist" in role_def:
                        role_props["hoist"] = role_def["hoist"]
                    if "mentionable" in role_def:
                        role_props["mentionable"] = role_def["mentionable"]
                    if existing is None:
                        perms = discord.Permissions.none()
                        perms.update(**role_def.get("permissions", {}))
                        role = await ctx.guild.create_role(
                            name=name, permissions=perms, **role_props,
                            reason=f"Revamp {op_id}: create role",
                        )
                        record["created_roles"].append(role.id)
                        await self._patch(ctx.guild, op_id, created_roles=record["created_roles"])
                    else:
                        role = existing
                        if theme.get("update_existing_roles", False):
                            record["edited_roles"].append({
                                "id": role.id, "colour": role.colour.value,
                                "hoist": role.hoist, "mentionable": role.mentionable,
                                "permissions": role.permissions.value,
                            })
                            await self._patch(ctx.guild, op_id, edited_roles=record["edited_roles"])
                            perms = role.permissions
                            perms.update(**role_def.get("permissions", {}))
                            await role.edit(permissions=perms, **role_props, reason=f"Revamp {op_id}: update role")
                    lookup[name] = role
                # Step 2: create missing starter items, or entire custom-theme layout.
                created_map = {}
                for category_def in theme["categories"]:
                    existing_category = None
                    if reuse_existing:
                        existing_category = next(
                            (cat for cat in ctx.guild.categories
                             if cat.name.casefold() == category_def["name"].casefold()), None
                        )
                    if reuse_existing and all(
                        _matching_starter_channel(ctx.guild, ch) is not None
                        for ch in category_def["channels"]
                    ):
                        continue
                    if existing_category is not None:
                        category = existing_category
                    else:
                        category = await ctx.guild.create_category(
                            category_def["name"],
                            overwrites=self._bot_post_overwrite(
                                ctx.guild, self._overwrites(category_def.get("overwrites", {}), lookup)
                            ),
                            reason=f"Revamp {op_id}: new category",
                        )
                        record["created_categories"].append(category.id)
                        await self._patch(ctx.guild, op_id, created_categories=record["created_categories"])
                    for channel_def in category_def["channels"]:
                        if reuse_existing and _matching_starter_channel(ctx.guild, channel_def):
                            continue
                        kind = channel_def.get("type", "text")
                        common = {
                            "name": channel_def["name"], "category": category,
                            "reason": f"Revamp {op_id}: new channel",
                        }
                        if "overwrites" in channel_def:
                            common["overwrites"] = self._bot_post_overwrite(
                                ctx.guild, self._overwrites(channel_def["overwrites"], lookup)
                            )
                        elif reuse_existing and existing_category is not None:
                            # A pre-existing STAFF category might be public: apply our intended
                            # restrictions to the NEW channel without editing the category.
                            common["overwrites"] = self._bot_post_overwrite(
                                ctx.guild, self._overwrites(category_def.get("overwrites", {}), lookup)
                            )
                        # Otherwise inherit the category permission overwrites.
                        if kind == "text":
                            channel = await ctx.guild.create_text_channel(
                                **common,
                                topic=channel_def.get("topic"),
                                nsfw=channel_def.get("nsfw", False),
                                slowmode_delay=channel_def.get("slowmode", 0),
                            )
                        else:
                            channel = await ctx.guild.create_voice_channel(
                                **common, user_limit=channel_def.get("user_limit", 0)
                            )
                        record["created_channels"].append(channel.id)
                        await self._patch(ctx.guild, op_id, created_channels=record["created_channels"])
                        path = f"{category_def['name']}/{channel_def['name']}"
                        created_map[path] = channel
                        if kind == "text":
                            for msg in channel_def.get("messages", []):
                                content = msg if isinstance(msg, str) else msg["content"]
                                posted = await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
                                if isinstance(msg, dict) and msg.get("pin"):
                                    await posted.pin(reason=f"Revamp {op_id}: pin intro")
                # Step 3: only post starter rules in a channel that this run created.
                # This never writes to an existing server's rules channel.
                if theme.get("rules") and theme["rules_channel"] in created_map:
                    rule_channel = created_map[theme["rules_channel"]]
                    for index, rule in enumerate(theme["rules"], start=1):
                        msg = await rule_channel.send(
                            f"**{index}.** {rule}", allowed_mentions=discord.AllowedMentions.none()
                        )
                        await msg.pin(reason=f"Revamp {op_id}: pin rule")
                # Step 4: archive existing text/voice channels only if explicitly requested.
                if archive_old and candidates:
                    archived_roles = self._overwrites(
                        {"@everyone": {"view_channel": False}, **{
                            role_name: {"view_channel": True, "read_message_history": True}
                            for role_name in theme.get("archive_read_roles", [])
                        }}, lookup,
                    )
                    for batch_num in range(0, len(candidates), MAX_ARCHIVE_PER_CATEGORY):
                        batch = candidates[batch_num:batch_num + MAX_ARCHIVE_PER_CATEGORY]
                        archive_cat = await ctx.guild.create_category(
                            f"REVAMP ARCHIVE {op_id} {batch_num // MAX_ARCHIVE_PER_CATEGORY + 1}",
                            overwrites=self._bot_post_overwrite(ctx.guild, archived_roles),
                            reason=f"Revamp {op_id}: reviewable old channels",
                        )
                        record["created_categories"].append(archive_cat.id)
                        await self._patch(ctx.guild, op_id, created_categories=record["created_categories"])
                        for original in batch:
                            # Record FIRST so failed moves are recoverable too.
                            saved = {
                                "id": original.id, "category": original.category_id,
                                "position": original.position,
                                "overwrites": snapshot_overwrites(original),
                                "restored": False,
                            }
                            record["archived"].append(saved)
                            await self._patch(ctx.guild, op_id, archived=record["archived"])
                            await original.edit(
                                category=archive_cat, sync_permissions=True,
                                reason=f"Revamp {op_id}: archive old channel",
                            )
                await self._patch(ctx.guild, op_id, status="done")
                await ctx.send(
                    f"Revamp `{op_id}` complete: **{theme['name']}**. "
                    f"Moved {len(record['archived'])} old channels to review archives. "
                    f"Use `{ctx.clean_prefix}revamp old` to inspect or `{ctx.clean_prefix}revamp undo` to reverse the layout."
                )
            except Exception as exc:
                if 'op_id' in locals():
                    await self._patch(ctx.guild, op_id, status="failed", error=f"{type(exc).__name__}: {exc}"[:300])
                await ctx.send(
                    f"Revamp stopped: `{type(exc).__name__}: {exc}`. "
                    f"Previous channels were not deleted. `{ctx.clean_prefix}revamp undo` can attempt to recover recorded changes."
                )


    @revamp.command(name="keep")
    async def keep_channel(self, ctx, channel: discord.abc.GuildChannel):
        """Exclude a specific channel from archiving (optional)."""
        async with self.config.guild(ctx.guild).protected_channels() as ids:
            if channel.id not in ids:
                ids.append(channel.id)
        await ctx.send(f"Will keep **{channel.name}** in place during the revamp.")

    @revamp.command(name="unkeep")
    async def unkeep_channel(self, ctx, channel: discord.abc.GuildChannel):
        """Allow a previously protected public channel to be archived next time."""
        async with self.config.guild(ctx.guild).protected_channels() as ids:
            if channel.id in ids:
                ids.remove(channel.id)
        await ctx.send(f"Removed the extra protection from **{channel.name}**. Special/command channels remain protected.")

    @revamp.command(name="old")
    async def old_channels(self, ctx):
        latest = await self._latest_active(ctx.guild)
        if not latest:
            return await ctx.send("No active revamp.")
        items = []
        for saved in latest.get("archived", []):
            ch = ctx.guild.get_channel(saved["id"])
            if ch and not saved.get("restored"):
                items.append(f"{ch.mention} (`{ch.id}`)")
        if not items:
            return await ctx.send("No archived channels remain in this revamp.")
        output = "**Archived old channels**\n" + "\n".join(items)
        for offset in range(0, len(output), 1850):
            await ctx.send(output[offset:offset + 1850], allowed_mentions=discord.AllowedMentions.none())


    @revamp.command(name="restore")
    async def restore_channel(self, ctx, channel: discord.abc.GuildChannel, category: Optional[discord.CategoryChannel] = None):
        """Return one archived channel to its previous category, or choose a new one."""
        async with self._lock(ctx.guild.id):
            entry = await self._latest_active(ctx.guild)
            if not entry:
                return await ctx.send("No active revamp.")
            saved = next((x for x in entry.get("archived", []) if x["id"] == channel.id), None)
            if not saved:
                return await ctx.send("That channel is not a tracked archived channel.")
            if saved.get("restored"):
                return await ctx.send("This channel has already been restored.")
            target_cat = category or ctx.guild.get_channel(saved["category"])
            try:
                await channel.edit(
                    category=target_cat if isinstance(target_cat, discord.CategoryChannel) else None,
                    overwrites=restore_overwrites(ctx.guild, saved["overwrites"]),
                    position=saved["position"],
                    reason=f"Revamp {entry['id']}: individually restore channel",
                )
                saved["restored"] = True
                await self._patch(ctx.guild, entry["id"], archived=entry["archived"])
                await ctx.send(f"Restored {channel.mention}. Original messages remain intact.")
            except (discord.HTTPException, discord.Forbidden) as exc:
                await ctx.send(f"Cannot restore: {exc}")


    @revamp.command(name="undo")
    async def undo(self, ctx):
        """Restore archived old channels; quarantine new ones without deleting messages."""
        lock = self._lock(ctx.guild.id)
        if lock.locked():
            return await ctx.send("Another revamp action is running.")
        entry = await self._latest_active(ctx.guild)
        if not entry:
            return await ctx.send("No active revamp to roll back.")
        phrase = f"ROLLBACK {entry['id']}"
        await ctx.send(
            f"This will restore old channels, move *new* channels into a hidden review category, "
            f"and restore edited role settings. New roles/categories remain for manual review.\n"
            f"Type `{phrase}` within 90 seconds to confirm."
        )
        try:
            await self.bot.wait_for(
                "message", timeout=90,
                check=lambda m: m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and m.content == phrase,
            )
        except asyncio.TimeoutError:
            return await ctx.send("Rollback cancelled.")
        if ctx.channel.id in entry.get("created_channels", []):
            return await ctx.send("Run rollback in a pre-existing admin channel, not a channel this revamp created.")
        async with lock:
            errors = []
            # Restore old channels before quarantining the replacement layout.
            for saved in reversed(entry.get("archived", [])):
                if saved.get("restored"):
                    continue
                channel = ctx.guild.get_channel(saved["id"])
                if channel is None:
                    errors.append(f"Old channel {saved['id']} was deleted outside the cog")
                    continue
                try:
                    original_cat = ctx.guild.get_channel(saved["category"])
                    await channel.edit(
                        category=original_cat if isinstance(original_cat, discord.CategoryChannel) else None,
                        overwrites=restore_overwrites(ctx.guild, saved["overwrites"]),
                        position=saved["position"],
                        reason=f"Revamp {entry['id']}: rollback old layout",
                    )
                    saved["restored"] = True
                    await self._patch(ctx.guild, entry["id"], archived=entry["archived"])
                except (discord.HTTPException, discord.Forbidden) as exc:
                    errors.append(f"Old channel {channel.id}: {exc}")
            # Never delete new channels: they may already have conversations in them.
            new_channels = [ctx.guild.get_channel(cid) for cid in entry.get("created_channels", [])]
            new_channels = [ch for ch in new_channels if ch is not None and not isinstance(ch, discord.CategoryChannel)]
            if new_channels:
                review_ids = list(entry.get("rollback_categories", []))
                for batch_num in range(0, len(new_channels), MAX_ARCHIVE_PER_CATEGORY):
                    batch = new_channels[batch_num:batch_num + MAX_ARCHIVE_PER_CATEGORY]
                    idx = batch_num // MAX_ARCHIVE_PER_CATEGORY
                    try:
                        review = ctx.guild.get_channel(review_ids[idx]) if len(review_ids) > idx else None
                        if not isinstance(review, discord.CategoryChannel):
                            review = await ctx.guild.create_category(
                                f"REVAMP ROLLBACK {entry['id']} {idx + 1}",
                                overwrites=self._bot_post_overwrite(ctx.guild, {
                                    ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False)
                                }),
                                reason=f"Revamp {entry['id']}: preserve replacement channels",
                            )
                            if len(review_ids) > idx:
                                review_ids[idx] = review.id
                            else:
                                review_ids.append(review.id)
                            await self._patch(ctx.guild, entry['id'], rollback_categories=review_ids)
                        for channel in batch:
                            try:
                                await channel.edit(
                                    category=review, sync_permissions=True,
                                    reason=f"Revamp {entry['id']}: keep new messages for review",
                                )
                            except (discord.HTTPException, discord.Forbidden) as exc:
                                errors.append(f"New channel {channel.id}: {exc}")
                    except (discord.HTTPException, discord.Forbidden) as exc:
                        errors.append(f"Cannot create rollback review category: {exc}")
            for saved in reversed(entry.get("edited_roles", [])):
                role = ctx.guild.get_role(saved["id"])
                if role is not None:
                    try:
                        await role.edit(
                            colour=discord.Colour(saved["colour"]),
                            permissions=discord.Permissions(saved["permissions"]),
                            hoist=saved["hoist"], mentionable=saved["mentionable"],
                            reason=f"Revamp {entry['id']}: rollback role edits",
                        )
                    except (discord.HTTPException, discord.Forbidden) as exc:
                        errors.append(f"Role {role.id}: {exc}")
            await self._patch(
                ctx.guild, entry["id"],
                status="rollback_failed" if errors else "rolled_back",
                rollback_errors=errors[:40],
            )
            await ctx.send(
                f"Rollback {'completed' if not errors else 'completed with issues'} for `{entry['id']}`. "
                "No channels or messages were deleted. "
                + ("Problems: " + "; ".join(errors[:6]) if errors else "Review new roles and now-empty categories manually.")
            )


async def setup(bot):
    await bot.add_cog(Revamp(bot))
