"""On-demand, read-only audit of a Discord guild for Red-DiscordBot."""
from __future__ import annotations

import asyncio
import io
import json
from collections import Counter
from datetime import datetime, timezone

import discord
from redbot.core import commands

SEVERITY = ("HIGH", "MEDIUM", "LOW", "INFO")
SENSITIVE = (
    "administrator", "manage_guild", "manage_roles", "manage_channels",
    "manage_webhooks", "ban_members", "kick_members", "moderate_members",
    "manage_messages", "manage_threads", "mention_everyone",
)
CRITICAL = SENSITIVE[:7]


def perms_enabled(p):
    return sorted(k for k, v in p if v)


def sensitive(p):
    return [k for k in SENSITIVE if getattr(p, k, False)]


def enum_label(v):
    return str(getattr(v, "name", v))


def clean(v):
    return str(v).replace("\r", " ").replace("\n", " ").replace(chr(96), "'")


def add_flag(flags, severity, section, title, evidence, action):
    flags.append({
        "severity": severity, "section": section, "title": title,
        "evidence": evidence, "recommendation": action,
    })


def report_md(data, scope):
    g = data["guild"]
    relevant = [f for f in data["findings"] if scope == "all" or f["section"] == scope]
    relevant.sort(key=lambda x: SEVERITY.index(x["severity"]))
    summary = Counter(f["severity"] for f in relevant)
    lines = [
        "# Server audit",
        "",
        "Server: {} ({})".format(clean(g["name"]), g["id"]),
        "Generated UTC: " + data["generated_at"],
        "Section: " + scope,
        "Read-only: no settings changed.",
        "",
        "## Snapshot",
        "- Discord-reported member count: " + str(g["member_count"]),
        "- Inspected members: " + str(data["coverage"]["members_inspected"]),
        "- Complete member inventory: " + str(data["coverage"]["members_complete"]),
        "- Bots visible: " + str(len(data["bots"])),
        "- Roles: " + str(len(data["roles"])),
        "- Channels: " + str(len(data["channels"])),
        "- Findings: " + ", ".join("{} {}".format(s, summary[s]) for s in SEVERITY),
        "",
        "## Prioritized findings and suggested fixes",
    ]
    if not relevant:
        lines.append("No rule-based flags found. This is not a security certification.")
    for i, f in enumerate(relevant, 1):
        lines.extend([
            "",
            "### {}. [{}] {}".format(i, f["severity"], clean(f["title"])),
            "Observed: " + clean(f["evidence"]),
            "Suggestion: " + clean(f["recommendation"]),
        ])
    if scope in ("all", "settings"):
        lines.extend(["", "## Server settings"])
        lines.extend("- {}: {}".format(k, clean(v)) for k, v in data["settings"].items())
        lines.extend(["", "## AutoMod rules"])
        if data["automod"] is None:
            lines.append("Not inspected; see coverage notes.")
        else:
            lines.extend(
                "- {}: enabled={}, trigger={}".format(clean(r["name"]), r["enabled"], r["trigger"])
                for r in data["automod"]
            )
            if not data["automod"]:
                lines.append("No rules returned.")
        lines.extend(["", "## Invites"])
        if data["invites"] is None:
            lines.append("Not inspected; see coverage notes.")
        else:
            lines.extend(
                "- #{}: uses={}, max_age={}, max_uses={}".format(
                    clean(i["channel"]), i["uses"], i["max_age"], i["max_uses"])
                for i in data["invites"]
            )
            if not data["invites"]:
                lines.append("No invite objects returned.")
    if scope in ("all", "roles"):
        lines.extend(["", "## Role inventory"])
        for r in data["roles"]:
            lines.append(
                "- {} [{}] pos={} managed={} members={} elevated={} ALL_PERMISSIONS={}".format(
                    clean(r["name"]), r["id"], r["position"], r["managed"],
                    r["members"], ", ".join(r["sensitive"]) or "none",
                    ", ".join(r["permissions"]) or "none"
                )
            )
    if scope in ("all", "bots"):
        lines.extend(["", "## Bot inventory"])
        for b in data["bots"]:
            lines.append(
                "- {} [{}] top_role={} roles={} elevated={} ALL_PERMISSIONS={}".format(
                    clean(b["name"]), b["id"], clean(b["top_role"]),
                    ", ".join(clean(v) for v in b["roles"]) or "none",
                    ", ".join(b["sensitive"]) or "none",
                    ", ".join(b["permissions"]) or "none"
                )
            )
        if not data["bots"]:
            lines.append("No bot members in the visible inventory.")
    if scope in ("all", "channels"):
        lines.extend(["", "## Channels: @everyone effective permission snapshot"])
        for c in data["channels"]:
            lines.append(
                "- {} [{}] type={} category={} everyone_view={} everyone_post={} "
                "everyone_webhooks={} category_synced={} bot_view={}".format(
                    clean(c["name"]), c["id"], c["type"], clean(c["category"]),
                    c["everyone_view"], c["everyone_post"], c["everyone_webhooks"],
                    c["category_synced"], c["bot_view"]
                )
            )
    lines.extend(["", "## Coverage"])
    lines.extend("- {}: {}".format(k, clean(v)) for k, v in data["coverage"].items())
    lines.extend(["", "## Limits"])
    lines.extend("- " + v for v in data["limitations"])
    return "\n".join(lines) + "\n"


class ServerAudit(commands.Cog):
    """Review safety settings, role and channel access, and bot privilege."""

    def __init__(self, bot):
        self.bot = bot
        self._running = set()

    async def get_members(self, guild):
        members = list(guild.members)
        count = guild.member_count
        complete = count is not None and len(members) >= count
        note = "Cached guild members."
        if not complete and self.bot.intents.members and count is not None and count <= 2500:
            try:
                await asyncio.wait_for(guild.chunk(cache=True), timeout=25)
                members = list(guild.members)
                complete = len(members) >= count
                note = "Member chunk completed." if complete else "Member chunk partial."
            except (discord.HTTPException, discord.ClientException, asyncio.TimeoutError) as exc:
                note = "Member chunk failed: {}.".format(type(exc).__name__)
        elif not complete:
            note = ("Members intent off; member inventory partial." if not self.bot.intents.members
                    else "Large or unknown-size guild; cached members only.")
        return members, complete, note

    async def scan(self, guild):
        findings = []
        members, complete, member_note = await self.get_members(guild)
        me = guild.me or guild.get_member(self.bot.user.id)
        my_perms = me.guild_permissions if me else discord.Permissions.none()
        settings = {
            "owner_id": guild.owner_id,
            "verification_level": enum_label(guild.verification_level),
            "explicit_content_filter": enum_label(guild.explicit_content_filter),
            "moderator_2fa_requirement": enum_label(guild.mfa_level),
            "default_notifications": enum_label(guild.default_notifications),
            "community_enabled": "COMMUNITY" in guild.features,
            "nsfw_level (not proof of age)": enum_label(getattr(guild, "nsfw_level", "unknown")),
            "rules_channel": getattr(guild.rules_channel, "name", "not set"),
            "system_channel": getattr(guild.system_channel, "name", "not set"),
            "safety_alerts_channel": getattr(getattr(guild, "safety_alerts_channel", None), "name", "not set"),
        }
        if guild.verification_level == discord.VerificationLevel.none:
            add_flag(findings, "MEDIUM", "settings", "Server verification level disabled",
                     "New joins have no Discord verification-level checks.",
                     "Review Server Settings > Safety Setup and use a suitable verification level.")
        if guild.explicit_content_filter == discord.ContentFilter.disabled:
            add_flag(findings, "LOW", "settings", "Built-in explicit media scanning off",
                     "Discord media scanning is disabled for this guild.",
                     "Review whether enabling it suits this community and its content policy.")
        if getattr(guild.mfa_level, "value", guild.mfa_level) == 0:
            add_flag(findings, "MEDIUM", "settings", "Moderator 2FA requirement off",
                     "Server-level requirement for moderator 2FA is off.",
                     "Consider enabling Require 2FA for moderator actions.")
        if not self.bot.intents.members:
            add_flag(findings, "INFO", "bots", "Server Members Intent disabled",
                     "Bot/member inventories may be partial.",
                     "Enable Members Intent in Discord Developer Portal and Red, then restart.")

        roles = []
        for r in sorted(guild.roles, key=lambda role: role.position, reverse=True):
            roles.append({
                "id": r.id, "name": r.name, "position": r.position,
                "managed": r.managed, "mentionable": r.mentionable,
                "members": len(r.members) if complete else "unknown (partial cache)",
                "sensitive": sensitive(r.permissions),
                "permissions": perms_enabled(r.permissions),
            })
            if r == guild.default_role:
                bad = [p for p in CRITICAL if getattr(r.permissions, p, False)]
                if bad:
                    add_flag(findings, "HIGH", "roles", "@everyone has privileged permissions",
                             ", ".join(bad), "Remove unnecessary permissions from @everyone.")
                if r.permissions.mention_everyone:
                    add_flag(findings, "MEDIUM", "roles", "@everyone can mass-mention",
                             "@everyone role has Mention Everyone.",
                             "Restrict @everyone and @here mentions unless intentionally public.")
            elif r.permissions.administrator:
                add_flag(findings, "MEDIUM", "roles", "Administrator role to review",
                         "{} [{}] has Administrator; members={}".format(
                             r.name, r.id, len(r.members) if complete else "unknown"),
                         "Confirm assigned members and necessity; Administrator bypasses channel restrictions.")

        bots = []
        for m in sorted((m for m in members if m.bot), key=lambda x: x.display_name.casefold()):
            effective = m.guild_permissions
            bots.append({
                "id": m.id, "name": str(m), "top_role": m.top_role.name,
                "roles": [r.name for r in m.roles if r != guild.default_role],
                "sensitive": sensitive(effective),
                "permissions": perms_enabled(effective),
            })
            if effective.administrator:
                add_flag(findings, "HIGH", "bots", "Bot has Administrator",
                         "{} [{}] has effective Administrator.".format(m, m.id),
                         "Review the bot's needs and minimize its privileges where practical.")
            elif effective.manage_guild and effective.manage_roles:
                add_flag(findings, "MEDIUM", "bots", "Bot has broad management rights",
                         "{} [{}] has Manage Server and Manage Roles.".format(m, m.id),
                         "Review role hierarchy, command access and least-privilege configuration.")
        if not complete:
            add_flag(findings, "INFO", "bots", "Bot roster may be incomplete", member_note,
                     "Enable Members Intent and rerun; bot membership is not fully verified.")

        channels = []
        unsynced = 0
        hidden_from_bot = 0
        for c in sorted(guild.channels, key=lambda x: (x.position, x.id)):
            p = c.permissions_for(guild.default_role)
            visible = bool(p.view_channel)
            can_post = bool(p.send_messages or getattr(p, "send_messages_in_threads", False))
            bot_view = c.permissions_for(me).view_channel if me else None
            synced = getattr(c, "permissions_synced", None) if c.category else None
            unsynced += (synced is False)
            hidden_from_bot += (bot_view is False)
            channels.append({
                "id": c.id, "name": c.name, "type": str(c.type),
                "category": getattr(c.category, "name", "none"),
                "everyone_view": visible, "everyone_post": can_post,
                "everyone_webhooks": bool(p.manage_webhooks),
                "category_synced": synced, "bot_view": bot_view,
            })
            if visible and p.manage_webhooks:
                add_flag(findings, "HIGH", "channels", "Public channel: webhook management",
                         "@everyone can manage webhooks in #{} [{}].".format(c.name, c.id),
                         "Remove that permission in the channel/category overwrite.")
            if visible and can_post and any(x in c.name.casefold() for x in
                                            ("rules", "announcement", "welcome", "read-only", "information")):
                add_flag(findings, "LOW", "channels", "Possible writable information channel",
                         "@everyone can post in #{} [{}] (name-based heuristic).".format(c.name, c.id),
                         "If it should be read-only, disable sending messages for @everyone.")
        if unsynced:
            add_flag(findings, "INFO", "channels", "Category permission exceptions",
                     "{} channel(s) have unsynced category overwrites.".format(unsynced),
                     "Review overrides; synchronize only those meant to inherit.")
        if hidden_from_bot:
            add_flag(findings, "INFO", "channels", "Auditor lacks some channel visibility",
                     "{} channel(s) not visible to the bot.".format(hidden_from_bot),
                     "Grant visibility if needed for your intended moderation coverage; not Administrator.")

        automod = None
        invites = None
        automod_note = "Bot lacks Manage Server; not checked."
        invites_note = "Bot lacks Manage Server; not checked."
        if my_perms.manage_guild:
            try:
                rules = await guild.fetch_automod_rules()
                automod = [
                    {"name": r.name, "enabled": r.enabled, "trigger": enum_label(r.trigger.type)}
                    for r in rules
                ]
                active = sum(1 for r in rules if r.enabled)
                automod_note = "{} rules read, {} enabled.".format(len(rules), active)
                if not active:
                    add_flag(findings, "LOW", "settings", "No enabled native AutoMod",
                             automod_note,
                             "Consider built-in spam/mention rules; check overlap with existing mod bots.")
            except discord.NotFound:
                automod = []
                automod_note = "No AutoMod rules returned."
            except (discord.HTTPException, AttributeError) as exc:
                automod_note = "Unavailable: {}".format(type(exc).__name__)
            try:
                found = await guild.invites()
                invites = [{
                    "channel": getattr(i.channel, "name", "unknown"),
                    "uses": i.uses, "max_age": i.max_age, "max_uses": i.max_uses,
                } for i in found]
                invites_note = "{} invites read.".format(len(found))
                unrestricted = sum(i.max_age == 0 and i.max_uses == 0 for i in found)
                if unrestricted:
                    add_flag(findings, "LOW", "settings", "Permanent unlimited invites",
                             "{} unlimited, non-expiring invite(s).".format(unrestricted),
                             "Review and revoke unneeded invite links.")
            except discord.HTTPException as exc:
                invites_note = "Unavailable: {}".format(type(exc).__name__)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "guild": {"name": guild.name, "id": guild.id,
                      "owner_id": guild.owner_id, "member_count": guild.member_count},
            "settings": settings, "roles": roles, "bots": bots,
            "channels": channels, "automod": automod, "invites": invites,
            "findings": findings,
            "coverage": {
                "members_inspected": len(members), "members_complete": complete,
                "member_inventory": member_note, "automod": automod_note,
                "invites": invites_note, "unsynced_channels": unsynced,
                "channels_invisible_to_bot": hidden_from_bot,
                "bot_manage_guild": my_perms.manage_guild,
            },
            "limitations": [
                "Administrator roles and category exceptions are prompts for review, not proof of vulnerabilities.",
                "Without a complete Members Intent/cache, bot lists and role membership counts may be incomplete.",
                "@everyone channel permissions do not represent every member's combined permission set.",
                "Other bots' private configs, plugin settings and third-party dashboards cannot be inspected.",
                "Discord does not expose actual member ages; this is not proof of an 18+ audience.",
                "One current-state snapshot is not a historical moderation/audit log.",
            ],
        }

    @commands.command(name="audit", aliases=["serveraudit"])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    @commands.cooldown(1, 60, commands.BucketType.guild)
    async def audit(self, ctx, scope: str = "all"):
        """DM a read-only report: audit [all|settings|roles|bots|channels|export]."""
        scope = scope.lower()
        if scope not in ("all", "settings", "roles", "bots", "channels", "export"):
            await ctx.send("Usage: audit [all|settings|roles|bots|channels|export]")
            return
        # Do not allow a Red permission rule to bypass actual Manage Server access.
        if ctx.author.id != ctx.guild.owner_id and not ctx.author.guild_permissions.manage_guild:
            await ctx.send("Server owner or Manage Server permission required.")
            return
        if ctx.guild.id in self._running:
            await ctx.send("Audit already running in this server.")
            return
        self._running.add(ctx.guild.id)
        try:
            async with ctx.typing():
                data = await self.scan(ctx.guild)
            section = "all" if scope == "export" else scope
            flags = [f for f in data["findings"] if section == "all" or f["section"] == section]
            counts = Counter(f["severity"] for f in flags)
            lead = (
                "Audit: {} | {}\n".format(data["guild"]["name"], section.upper())
                + "Flags: {} high, {} medium, {} low, {} info\n".format(
                    counts["HIGH"], counts["MEDIUM"], counts["LOW"], counts["INFO"])
                + "Roles: {} | Bots observed: {} | Channels: {}\n".format(
                    len(data["roles"]), len(data["bots"]), len(data["channels"]))
                + "Read-only snapshot. No server settings were changed."
            )
            md = report_md(data, section).encode("utf-8")
            files = [discord.File(io.BytesIO(md), filename="serveraudit-{}-{}.md".format(ctx.guild.id, section))]
            if scope == "export":
                raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
                files.append(discord.File(io.BytesIO(raw), filename="serveraudit-{}.json".format(ctx.guild.id)))
            try:
                await ctx.author.send(lead, files=files, allowed_mentions=discord.AllowedMentions.none())
            except (discord.Forbidden, discord.HTTPException):
                await ctx.send("Could not DM the report. Enable DMs and retry. "
                               "Sensitive audit details will not be posted publicly.")
                return
            await ctx.send("Audit complete; private report sent by DM.",
                           allowed_mentions=discord.AllowedMentions.none())
        finally:
            self._running.discard(ctx.guild.id)

    async def red_delete_data_for_user(self, *, requester, user_id):
        """No user records or snapshots are persisted by this cog."""
        return
