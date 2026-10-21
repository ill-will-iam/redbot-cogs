"""Owner-only command access for selected cogs, shared across all guilds.

A Discord command check cannot stop event listeners or background tasks. OwnerLock
never claims to do so; 'inspect' reports listener presence to the administrator.
"""

import asyncio

import discord
from redbot.core import Config, commands

from .rules import canonical_cog_name, command_allowed


class OwnerLock(commands.Cog):
    """Restrict selected cogs' commands to Red's configured bot owners."""

    __author__ = "Will"
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=788029416335, force_registration=True)
        self.config.register_global(protected_cogs=[])
        self._protected = set()
        self._lock = asyncio.Lock()
        # Retain exactly the callback object that we register, for clean unloading.
        self._command_check_callback = self._command_check
        self._check_registered = False

    async def cog_load(self):
        """Load persisted policy before registering a non-overridable bot check."""
        saved = await self.config.protected_cogs()
        self._protected = {canonical_cog_name(name) for name in saved if name.strip()}
        self.bot.add_check(self._command_check_callback)
        self._check_registered = True

    def cog_unload(self):
        """Do not leave stale global checks after the cog is reloaded."""
        if self._check_registered:
            self.bot.remove_check(self._command_check_callback)
            self._check_registered = False

    async def _command_check(self, ctx: commands.Context) -> bool:
        """Run for every command, including commands in nested groups and DMs."""
        command = ctx.command
        if command is None or command.cog is None:
            return True
        name = canonical_cog_name(command.cog.qualified_name)
        if name not in self._protected:
            return True
        return command_allowed(name, self._protected, await self.bot.is_owner(ctx.author))

    async def allows_event(self, cog_name: str, actor: discord.abc.User) -> bool:
        """Optional cooperative check for custom cogs' on_message listeners.

        Other cogs must call this method explicitly. This does not magically
        intercept their listeners, and must not be treated as such.
        """
        name = canonical_cog_name(cog_name)
        if name not in self._protected:
            return True
        return await self.bot.is_owner(actor)

    def _resolve_cog(self, name: str):
        normalized = canonical_cog_name(name)
        for cog in self.bot.cogs.values():
            if canonical_cog_name(cog.qualified_name) == normalized:
                return cog
        return None

    @staticmethod
    def _listener_names(cog) -> list:
        return sorted({event for event, _callback in cog.get_listeners()})

    @commands.group(name="ownerlock", aliases=["olock"], invoke_without_command=True)
    @commands.is_owner()
    async def ownerlock(self, ctx: commands.Context):
        """Manage owner-only access to the commands of selected cogs."""
        prefix = ctx.clean_prefix
        await ctx.send(
            "**OwnerLock — global owner-only cog commands**\n"
            f"`{prefix}olock protect <CogName>` — restrict a loaded cog\n"
            f"`{prefix}olock unprotect <CogName>` — restore its command access\n"
            f"`{prefix}olock list` — view protected cogs\n"
            f"`{prefix}olock inspect <CogName>` — show command/listener limitations\n"
            f"`{prefix}olock cogs` — list available loaded cogs\n\n"
            "Command restrictions apply in every server and in DMs. "
            "Listeners and background tasks are not automatically blocked.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ownerlock.command(name="protect", aliases=["add", "lock"])
    @commands.is_owner()
    async def protect(self, ctx: commands.Context, *, cog_name: str):
        """Make a cog's commands usable only by bot owners."""
        cog = self._resolve_cog(cog_name)
        if cog is None:
            await ctx.send("No loaded cog matches that name. Use `olock cogs` to list them.")
            return
        normalized = canonical_cog_name(cog.qualified_name)
        if normalized == canonical_cog_name(self.qualified_name):
            await ctx.send("OwnerLock already requires bot ownership; it cannot lock itself.")
            return

        async with self._lock:
            if normalized in self._protected:
                await ctx.send(f"**{discord.utils.escape_markdown(cog.qualified_name)}** is already owner-only.")
                return
            new_set = set(self._protected)
            new_set.add(normalized)
            await self.config.protected_cogs.set(sorted(new_set))
            self._protected = new_set

        listeners = self._listener_names(cog)
        detail = (
            "\n**Important:** This cog has event listeners. Commands are now owner-only, "
            "but its listeners and background behavior are not automatically restricted. "
            "That requires checks within the selected cog."
            if listeners else
            "\nNo event listeners were detected. Any background tasks still require separate review."
        )
        await ctx.send(
            f"**Locked:** {discord.utils.escape_markdown(cog.qualified_name)} — "
            "only Red bot owners can invoke its commands anywhere." + detail,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ownerlock.command(name="unprotect", aliases=["remove", "unlock"])
    @commands.is_owner()
    async def unprotect(self, ctx: commands.Context, *, cog_name: str):
        """Remove an owner-only command policy; normal cog checks still apply."""
        key = canonical_cog_name(cog_name)
        async with self._lock:
            if key not in self._protected:
                await ctx.send("That cog isn't on the protected list.")
                return
            new_set = set(self._protected)
            new_set.remove(key)
            await self.config.protected_cogs.set(sorted(new_set))
            self._protected = new_set
        await ctx.send(
            f"**Unlocked:** {discord.utils.escape_markdown(cog_name)} — normal command "
            "permissions now apply. Restrictions built into that cog still remain.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ownerlock.command(name="list", aliases=["status"])
    @commands.is_owner()
    async def protected_list(self, ctx: commands.Context):
        """List the owner-only command cogs (including unloaded cogs)."""
        if not self._protected:
            await ctx.send("No cogs are protected yet. Use `olock protect <CogName>`.")
            return
        chunks = []
        for key in sorted(self._protected):
            cog = self._resolve_cog(key)
            if cog is None:
                chunks.append(f"• {discord.utils.escape_markdown(key)} (currently unloaded)")
            elif self._listener_names(cog):
                chunks.append(f"• {discord.utils.escape_markdown(cog.qualified_name)} — event listeners also present")
            else:
                chunks.append(f"• {discord.utils.escape_markdown(cog.qualified_name)}")
        for i in range(0, len(chunks), 25):
            await ctx.send(
                "**Owner-locked cog commands (all servers):**\n" + "\n".join(chunks[i:i + 25]),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    @ownerlock.command(name="inspect", aliases=["check"])
    @commands.is_owner()
    async def inspect(self, ctx: commands.Context, *, cog_name: str):
        """Explain whether a cog has automatic listeners unaffected by this gate."""
        cog = self._resolve_cog(cog_name)
        if cog is None:
            await ctx.send("That cog is not loaded; use `olock cogs`.")
            return
        key = canonical_cog_name(cog.qualified_name)
        listeners = self._listener_names(cog)
        roots = len(cog.get_commands())
        status = "PROTECTED" if key in self._protected else "not protected"
        events = ", ".join(listeners[:12]) if listeners else "none detected"
        if len(listeners) > 12:
            events += ", ..."
        await ctx.send(
            f"**{discord.utils.escape_markdown(cog.qualified_name)}**\n"
            f"Command access: **{status}** (top-level commands: {roots})\n"
            f"Event listeners: **{discord.utils.escape_markdown(events)}**\n"
            "OwnerLock only blocks command invocations. Event listeners, app commands "
            "(slash commands), and background tasks are not guaranteed to be covered. "
            "For those, add enforcement in the underlying cog.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ownerlock.command(name="cogs", aliases=["available"])
    @commands.is_owner()
    async def cogs(self, ctx: commands.Context):
        """List currently loaded cogs and their protection status."""
        cogs = sorted(self.bot.cogs.values(), key=lambda c: c.qualified_name.casefold())
        lines = [
            f"{'LOCKED' if canonical_cog_name(c.qualified_name) in self._protected else 'open'}"
            f" — {discord.utils.escape_markdown(c.qualified_name)}"
            for c in cogs
        ]
        # Keep all messages well below Discord's 2000-character content limit.
        block = "**Loaded cogs:**\n"
        for line in lines:
            if len(block) + len(line) + 1 > 1750:
                await ctx.send(block, allowed_mentions=discord.AllowedMentions.none())
                block = "**More cogs:**\n"
            block += line + "\n"
        await ctx.send(block, allowed_mentions=discord.AllowedMentions.none())

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """OwnerLock stores only cog names, no personal information."""
        return
