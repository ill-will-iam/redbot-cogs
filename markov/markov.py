# Derived from Zanidom/ZanCogs/markov (original work credited to CrunchBangDev).
# Existing Red Config name, unique identifier, model format, and commands preserved.
import discord
import json
import logging
import random
import re
from datetime import datetime
from typing import Callable, Dict, Optional, Tuple

from redbot.core import checks, Config, commands, data_manager

log = logging.getLogger("red.cbd-cogs.markov")

UNIQUE_ID = 0x6D61726B6F76
CONTROL_TOKEN = f"{UNIQUE_ID}"
WORD_TOKENIZER = re.compile(r"(\W+)")

Model = Dict[str, Dict[str, int]]          # state -> (gram -> weight)
AllUserChains = Dict[str, Model]           # f"{mode}-{depth}" -> model
class Markov(commands.Cog):
    """A markov-chain-based text generator cog."""
    def __init__(self, bot):
        self.bot = bot
        self.conf = Config.get_conf(self, identifier=UNIQUE_ID, force_registration=True)
        # Keep the original config identifier and keys so existing models survive migration.
        self.conf.register_user(
            chains={}, chain_depth=1, mode="word", enabled=False, opted_out=False
        )
        self.conf.register_guild(
            channels=[], admin_enabled_users=[], everyone_channels=[]
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Process messages from enabled channels for enabled users."""

        if message.author.bot:
            return
        if not message.content:
            return
        if not message.content[0].isalnum():
            return

        if message.guild is not None:
            guild_settings = self.conf.guild(message.guild)
            enabled_channels = await guild_settings.channels()
            everyone_channels = await guild_settings.everyone_channels()
            if (
                enabled_channels
                and message.channel.id not in enabled_channels
                and message.channel.id not in everyone_channels
            ):
                return

        enabled, chains, depth, mode = await self.get_user_config(
            message.author, guild=message.guild, channel_id=message.channel.id
        )
                                                            
        if not enabled:
            return

        tokenizer, cleaner = self._get_tokenizer(mode)

        content = message.content.replace("`", "").strip()
        if not content:
            return

        tokens = self._tokenize(content, tokenizer, cleaner)
        if not tokens:
            return

        model_key = f"{mode}-{depth}"
        model = chains.get(model_key, {})

        state = CONTROL_TOKEN                                                
        tokens.append(CONTROL_TOKEN)

        for idx, gram in enumerate(tokens):
                                                                
            next_weights = model.setdefault(state, {})
            next_weights[gram] = next_weights.get(gram, 0) + 1

            start = 1 + idx - depth if idx >= depth else 0
            state = "".join(cleaner(x) for x in tokens[start : idx + 1])

        chains[model_key] = model
        await self.conf.user(message.author).chains.set(chains)

    @commands.group()
    async def markov(self, ctx: commands.Context):
        """New users must `enable` and say some words before using `generate`."""
        pass

    @markov.command()
    async def generate(
        self, ctx: commands.Context, length: Optional[int] = None, user: Optional[discord.Member] = None):
        """
        Generate text based on user language models.

        Usage:
        - ;markov generate
        - ;markov generate <length 1-50>
        - ;markov generate <length 1-50> @user
        """
        user = user or ctx.author

        if length is not None:
            length = max(1, min(50, int(length)))

        enabled, chains, depth, mode = await self.get_user_config(user, guild=ctx.guild)
        if not enabled:
            await ctx.send(f"Sorry, {user} won't let me model their speech")
            return

        #try a few times to avoid unlucky dead-ends
        for attempt in range(1, 5):
            text = await self.generate_text(chains, depth, mode, forced_length=length)
            if text:
                await ctx.send(text[:2000])
                return

        await ctx.send("I tried to generate text 4 times and couldn't get anything usable.")

    @markov.command()
    async def enable(self, ctx: commands.Context):
        """Allow the bot to model your messages and generate text based on that."""
        await self.conf.user(ctx.author).enabled.set(True)
        await self.conf.user(ctx.author).opted_out.set(False)
        await ctx.send("Markov modeling enabled! This also clears your previous opt-out.")

    @markov.command()
    async def disable(self, ctx: commands.Context):
        """Disallow the bot from modeling your message or generating text based on your models."""
        await self.conf.user(ctx.author).enabled.set(False)
        # An explicit member opt-out must take precedence over an admin enable.
        await self.conf.user(ctx.author).opted_out.set(True)
        await ctx.send("Markov text generation is now disabled for your user.\n"
            "I will stop updating your language models, but they are still stored.\n"
            "You may want to use `$markov reset` to delete them.\n")

    @markov.command()
    async def mode(self, ctx: commands.Context, mode: str):
        """Set the tokenization mode for model building.
        Modes:
        - word
        - chunk / chunk5 / chunk10 (etc.)                                                                              
        """
        await self.conf.user(ctx.author).mode.set(mode)
        await ctx.send(f"Token mode set to '{mode}'.")

    @markov.command()
    async def depth(self, ctx: commands.Context, depth: int):
        """Set the modeling depth (the 'n' in 'ngrams')."""
        depth = max(1, min(10, int(depth)))  # small sanity clamp
        await self.conf.user(ctx.author).chain_depth.set(depth)
        await ctx.send(f"Ngram modeling depth set to {depth}.")

    @markov.command()
    async def show(self, ctx: commands.Context, user: discord.abc.User = None):
        """Show your current settings and models, or those of another user."""
        user = user or ctx.author
        enabled, chains, depth, mode = await self.get_user_config(user, lazy=False, guild=ctx.guild)
        models = "\n".join(chains.keys()) if chains else "(none)"
        counts = self._chain_stats(chains)
        await ctx.send(f"**Enabled in this context:** {enabled}\n"
            f"**Chain Depth:** {depth}\n"
            f"**Token Mode:** {mode}\n"
            f"**Chain Size:** {self._human_bytes(counts['bytes'])} estimated JSON; "
            f"{counts['states']:,} states, {counts['edges']:,} distinct transitions\n"
            f"**Stored Models:**\n{models}")


    @markov.command()
    async def stats(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Show chain size and transition counts for yourself or a guild member."""
        user = user or ctx.author
        enabled, chains, depth, mode = await self.get_user_config(
            user, lazy=False, guild=ctx.guild
        )
        counts = self._chain_stats(chains)
        lines = [
            f"**Markov chain for {discord.utils.escape_markdown(str(user))}**",
            f"Enabled here: **{enabled}** | Mode: **{mode}** | Depth: **{depth}**",
            f"Stored models: **{counts['models']:,}**",
            f"Estimated JSON size: **{self._human_bytes(counts['bytes'])}**",
            f"States: **{counts['states']:,}**",
            f"Distinct transitions: **{counts['edges']:,}**",
            f"Recorded transition occurrences: **{counts['observations']:,}**",
        ]
        if chains:
            details = []
            for key, model in sorted(
                chains.items(), key=lambda kv: len(kv[1]), reverse=True
            )[:8]:
                details.append(f"`{key}`: {len(model):,} states")
            lines.append("Models (largest first): " + ", ".join(details))
        await ctx.send("\n".join(lines)[:1900])

    @checks.is_owner()
    @markov.command()
    async def statsall(self, ctx: commands.Context):
        """Show combined size of all Markov user models (bot owner only)."""
        async with ctx.typing():
            users = await self.conf.all_users()
            totals = dict(models=0, states=0, edges=0, observations=0, bytes=0)
            for user_conf in users.values():
                counts = self._chain_stats(user_conf.get("chains") or {})
                for key in totals:
                    totals[key] += counts[key]
        await ctx.send(
            f"**All Markov chains**\n"
            f"Stored user records: **{len(users):,}**\n"
            f"Models: **{totals['models']:,}**\n"
            f"Estimated combined JSON size: **{self._human_bytes(totals['bytes'])}**\n"
            f"States: **{totals['states']:,}**\n"
            f"Distinct transitions: **{totals['edges']:,}**\n"
            f"Recorded transition occurrences: **{totals['observations']:,}**"
        )

    @checks.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @markov.command()
    async def userenable(self, ctx: commands.Context, member: discord.Member):
        """Enable modeling for a member in this server without their own command.

        Never overrides a member's explicit `markov disable` opt-out.
        Models remain user-scoped, so data collected in different servers mixes.
        """
        if member.bot:
            await ctx.send("Bot accounts cannot be added to the Markov chain.")
            return
        if await self.conf.user(member).opted_out():
            await ctx.send(
                "That member explicitly opted out. They must run "
                f"`{ctx.clean_prefix}markov enable` to participate again."
            )
            return
        async with self.conf.guild(ctx.guild).admin_enabled_users() as ids:
            if member.id in ids:
                await ctx.send(f"{member.mention} is already admin-enabled here.")
                return
            ids.append(member.id)
        await ctx.send(
            f"Markov modeling enabled for {member.mention} in this server's "
            "eligible channels. They can opt out with "
            f"`{ctx.clean_prefix}markov disable` and delete stored models with "
            f"`{ctx.clean_prefix}markov reset`."
        )
        try:
            await member.send(
                f"Markov modeling was enabled for you in **{ctx.guild.name}** "
                f"by a server administrator. You can stop collection with "
                f"`{ctx.clean_prefix}markov disable` and delete your models "
                f"with `{ctx.clean_prefix}markov reset`."
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    @checks.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @markov.command()
    async def userdisable(self, ctx: commands.Context, member: discord.Member):
        """Remove this server's administrator enable for a member."""
        async with self.conf.guild(ctx.guild).admin_enabled_users() as ids:
            if member.id not in ids:
                await ctx.send(f"{member.mention} is not admin-enabled here.")
                return
            ids.remove(member.id)
        await ctx.send(
            f"Removed this server's admin enable for {member.mention}. "
            "This does not change their own opt-in or erase existing models."
        )

    @checks.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @markov.command()
    async def userlist(self, ctx: commands.Context):
        """List the members manually enabled in this server."""
        ids = await self.conf.guild(ctx.guild).admin_enabled_users()
        if not ids:
            await ctx.send("No members have been manually enabled in this server.")
            return
        display = [
            discord.utils.escape_markdown(
                str(ctx.guild.get_member(uid) or f"User ID {uid}")
            )
            for uid in ids[:30]
        ]
        remaining = f" (plus {len(ids) - 30} more)" if len(ids) > 30 else ""
        await ctx.send(
            f"**Admin-enabled Markov members ({len(ids)}){remaining}**\n" +
            "\n".join(display)[:1750]
        )

    @checks.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @markov.command(name="everyone")
    async def everyone(
        self, ctx: commands.Context, channel: discord.TextChannel, state: str = "on"
    ):
        """Enable modeling of every non-opted-out member in one channel.

        Usage:
        - [p]markov everyone #channel
        - [p]markov everyone #channel off

        Does not fetch old messages, enroll bots, or override an explicit opt-out.
        This setting is saved per server and applies to future members.
        """
        state = state.lower()
        if state not in ("on", "off", "enable", "disable"):
            await ctx.send(
                f"Use `{ctx.clean_prefix}markov everyone #channel [on|off]`."
            )
            return

        enable = state in ("on", "enable")
        async with self.conf.guild(ctx.guild).everyone_channels() as channel_ids:
            already_enabled = channel.id in channel_ids
            if enable and not already_enabled:
                channel_ids.append(channel.id)
            elif not enable and already_enabled:
                channel_ids.remove(channel.id)

        if enable:
            status = "already enabled" if already_enabled else "now enabled"
            await ctx.send(
                f"Automatic Markov modeling is **{status}** for all non-bot "
                f"members posting in {channel.mention}. Only future messages "
                "are collected. Members who explicitly opted out remain excluded; "
                f"any member can opt out with `{ctx.clean_prefix}markov disable`."
            )
        else:
            status = "now disabled" if already_enabled else "already disabled"
            await ctx.send(
                f"Automatic Markov modeling for all members in "
                f"{channel.mention} is **{status}**. Users who were individually "
                "enabled may still be modeled under the existing settings. "
                "No stored models were deleted."
            )

    @staticmethod
    def _human_bytes(size: int) -> str:
        value = float(size)
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if value < 1024 or unit == "TiB":
                return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.2f} {unit}"
            value /= 1024
        return f"{value:.2f} TiB"

    @staticmethod
    def _chain_stats(chains: AllUserChains) -> Dict[str, int]:
        """Estimate size of stored models, without mutating any chain."""
        states = edges = observations = 0
        for model in chains.values():
            states += len(model)
            for weights in model.values():
                edges += len(weights)
                observations += sum(weights.values())
        size = len(json.dumps(chains, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) if chains else 0
        return {
            "models": len(chains),
            "states": states,
            "edges": edges,
            "observations": observations,
            "bytes": size,
        }

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """Remove a user's models and administrator-enabled records."""
        await self.conf.user_from_id(user_id).clear()
        guilds = await self.conf.all_guilds()
        for guild_id, settings in guilds.items():
            ids = settings.get("admin_enabled_users", [])
            if user_id in ids:
                await self.conf.guild_from_id(guild_id).admin_enabled_users.set(
                    [uid for uid in ids if uid != user_id]
                )

    @markov.command()
    async def delete(self, ctx: commands.Context, model: str):
        """Delete a specific model from your profile (e.g. 'word-2', 'chunk5-3')."""
        chains = await self.conf.user(ctx.author).chains() or {}
        if model in chains:
            del chains[model]
            await self.conf.user(ctx.author).chains.set(chains)
            await ctx.send("Deleted model.")
        else:
            await ctx.send("Model not found.")

    @markov.command()
    async def reset(self, ctx: commands.Context):
        """Remove all language models from your profile."""
        await self.conf.user(ctx.author).chains.set({})
        await ctx.send("All models deleted.")

    @checks.is_owner()
    @markov.command()
    async def prune(self, ctx: commands.Context, confirm: Optional[str] = None):
        """Remove stored models for users who no longer share any server with the bot.

        Models are stored per user (not per guild), so a user is only prunable
        once they are in none of the bot's servers.

        Usage:
        - ;markov prune            (dry run - reports what would be removed)
        - ;markov prune confirm    (backs up to the cog data folder, then deletes)
        """
        if not self.bot.intents.members:
            await ctx.send("I need the members intent to know who is still in a server - refusing to prune blind.")
            return

        all_users = await self.conf.all_users()
        stale = [uid for uid in all_users
                 if not any(g.get_member(uid) for g in self.bot.guilds)]

        if not stale:
            await ctx.send(f"Nothing to prune - all {len(all_users)} stored users still share a server with me.")
            return

        #A huge stale fraction usually means the check itself is wrong (logged in
        #under a different token/account, or the member cache isn't populated),
        #not that everyone actually left. Demand a scarier confirmation for that.
        mass_prune = len(stale) > len(all_users) / 2
        required = "confirm-mass" if mass_prune else "confirm"

        if confirm != required:
            msg = (f"{len(stale)} of {len(all_users)} stored users no longer share a server with me "
                f"(I am `{self.bot.user}` in {len(self.bot.guilds)} server(s)).\n")
            if mass_prune:
                msg += ("⚠ That is over half of all stored users. If this bot is signed in under a "
                    "different token or account than the one that collected this data, this prune "
                    "would be wrong. Double-check the identity above, then run "
                    f"`{ctx.clean_prefix}markov prune confirm-mass` if you really mean it.")
            else:
                msg += f"Run `{ctx.clean_prefix}markov prune confirm` to back their data up and delete it."
            await ctx.send(msg)
            return

        backup_path = data_manager.cog_data_path(self) / f"prune_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump({uid: all_users[uid] for uid in stale}, f)
        backup_mb = backup_path.stat().st_size / 1024 / 1024

        async with ctx.typing():
            for uid in stale:
                await self.conf.user_from_id(uid).clear()

        await ctx.send(f"Pruned {len(stale)} users ({backup_mb:.1f} MB backed up to `{backup_path.name}`).\n"
            "Reload me (`[p]reload markov`) to release the memory they were using.")

    @checks.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @markov.command()
    async def channelmode(self, ctx: commands.Context, mode: str, channel: discord.TextChannel = None):
        """Toggle modeling of messages in a channel for enabled users.
        Modes:
        - enable
        - disable
        """
        channel = channel or ctx.channel
        enabled_channels = await self.conf.guild(ctx.guild).channels()

        mode_l = mode.lower()
        if mode_l == "enable":
            if channel.id not in enabled_channels:
                enabled_channels.append(channel.id)
                await ctx.send(f"Modeling enabled for {channel.mention}.")
            else:
                await ctx.send(f"Modeling already enabled for {channel.mention}.")
        elif mode_l == "disable":
            if channel.id in enabled_channels:
                enabled_channels.remove(channel.id)
                await ctx.send(f"Modeling disabled for {channel.mention}.")
            else:
                await ctx.send(f"Modeling already disabled for {channel.mention}.")
        else:
            await ctx.send("Invalid mode. Please use `enable` or `disable`.")
            return

        await self.conf.guild(ctx.guild).channels.set(enabled_channels)

    @checks.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @markov.command()
    async def channelstatus(self, ctx: commands.Context):
        """Display the status of all channels in terms of modeling."""
        enabled_channel_ids = set(await self.conf.guild(ctx.guild).channels())
        everyone_channel_ids = set(await self.conf.guild(ctx.guild).everyone_channels())
        enabled_lines = [
            ch.mention for ch in ctx.guild.text_channels if ch.id in enabled_channel_ids
        ]
        everyone_lines = [
            ch.mention for ch in ctx.guild.text_channels if ch.id in everyone_channel_ids
        ]
        standard = ", ".join(enabled_lines) if enabled_lines else "All channels (for individually enabled users)"
        everyone = ", ".join(everyone_lines) if everyone_lines else "(none)"
        await ctx.send(
            (f"**Markov channel status**\\n"
             f"Enabled users: {standard}\\n"
             f"Everyone (except opt-outs): {everyone}")[:1900]
        )

    async def get_user_config(
        self,
        user: discord.abc.User,
        lazy: bool = True,
        guild: Optional[discord.Guild] = None,
        channel_id: Optional[int] = None,
    ) -> Tuple[bool, AllUserChains, int, str]:
        """Read user data, including guild admin and channel-wide enables.

        An explicit opt-out always wins. Guild settings never apply to DMs.
        For guild commands without a channel_id, any everyone-enabled channel
        permits generating from existing models.
        """
        user_config = self.conf.user(user)
        opted_out = await user_config.opted_out()
        enabled = (await user_config.enabled()) and not opted_out
        if not enabled and not opted_out and guild is not None:
            guild_settings = self.conf.guild(guild)
            enabled = user.id in await guild_settings.admin_enabled_users()
            if not enabled:
                everyone_channels = await guild_settings.everyone_channels()
                enabled = (
                    channel_id in everyone_channels
                    if channel_id is not None
                    else bool(everyone_channels)
                )
        if lazy and not enabled:
            return (False, {}, 1, "word")

        chains: AllUserChains = await user_config.chains() or {}
        depth = await user_config.chain_depth() or 1
        mode = (await user_config.mode() or "word").lower()
        return enabled, chains, depth, mode

    async def generate_text(self, chains: AllUserChains, depth: int, mode: str, forced_length: Optional[int] = None) -> Optional[str]:
        """Generate text based on the appropriate model for user settings.
        If forced_length is provided, tries to output exactly that many grams (skipping CONTROL_TOKEN).
        """

        generator = self._get_generator(mode)
        if generator is None:
            return f"Sorry, I don't have a text generator for token mode '{mode}'"

        model_key = f"{mode}-{depth}"
        model = chains.get(model_key)
        if not model:
            return "Sorry, I can't find a model to use."

        output_parts = []
        state = CONTROL_TOKEN

        if forced_length is None:
            #Natural mode: stop when we hit CONTROL_TOKEN
            last_gram = ""
            steps = 0
            while last_gram.strip() != CONTROL_TOKEN and steps < 500:
                last_gram = await generator(model, state)
                output_parts.append(last_gram)

                steps += 1
                start = max(0, steps - depth)
                state = "".join(output_parts[start:steps])

            if not output_parts:
                return None

            #drop trailing control token
            return "".join(output_parts[:-1]).strip() or None

        #Forced-length mode: produce exactly N grams, skipping CONTROL_TOKEN
        target = max(1, min(50, forced_length))
        produced = 0
        safety_steps = 0

        #allow extra sampling in case we hit CONTROL_TOKEN or dead-ends
        while produced < target and safety_steps < target * 25:
            gram = await generator(model, state)
            safety_steps += 1
            
            if gram.strip() == CONTROL_TOKEN:
                #Treat forced boundary as a soft sentence break, pop a cheeky space in there
                if output_parts and not output_parts[-1].endswith(" "):
                    output_parts.append(" ")
                state = CONTROL_TOKEN
                continue

            output_parts.append(gram)

            #only count "words" (tokens containing any alphanumeric), not raw punctuation
            #(had an issue where I was getting 5-10 less per request)
            if any(ch.isalnum() for ch in gram):
                produced += 1

            #maintain state window
            start = max(0, len(output_parts) - depth)
            state = "".join(output_parts[start:])

        text = "".join(output_parts).strip()
        return text or None

    def _get_generator(self, mode: str) -> Optional[Callable[[Model, str], "commands.Coroutine"]]:
        if mode == "word":
            return self.generate_word_gram
        if mode.startswith("chunk"):
            return self.generate_chunk_gram
        return None

    def _get_tokenizer(self, mode: str):
        """Return (tokenizer_regex, cleaner_callable)."""
        if mode == "word":
            return WORD_TOKENIZER, (lambda s: s.strip())

        if mode.startswith("chunk"):
            #mode can be "chunk" or "chunk5", etc.
            raw_len = mode[5:]  # "" if exactly "chunk"
            chunk_len = 3 if raw_len == "" else int(raw_len)
            chunk_len = max(1, min(50, chunk_len))
            return re.compile(fr"(.{{{chunk_len}}})"), (lambda s: s)

        #fallback: treat as word
        return WORD_TOKENIZER, (lambda s: s.strip())

    def _tokenize(self, content: str, tokenizer: re.Pattern, cleaner: Callable[[str], str]):
        """Split then clean, dropping empties."""
        parts = tokenizer.split(content)
        tokens = []
        for part in parts:
            cleaned = cleaner(part)
            if cleaned:
                tokens.append(cleaned)
        return tokens

    async def generate_word_gram(self, model: Model, state: str) -> str:
        """Generate text for word-mode vectorization."""
        gram = await self.choose_gram(model, state)
        needs_space = all(
            (
                state != CONTROL_TOKEN,
                gram and (gram[-1].isalnum() or gram in "\"([{|"),
                state and (state[-1] not in "\"([{'/-_"),
            )
        )
        return f"{' ' if needs_space else ''}{gram}"

    async def generate_chunk_gram(self, model: Model, state: str) -> str:
        """Generate text for chunk-mode vectorization."""
        return await self.choose_gram(model, state)

    async def choose_gram(self, model: Model, state: str) -> str:
        """Choose a next gram based on weighted transitions from a state."""
        gram = self._choose_from_state(model, state)
        if gram is not None:                       
            return gram

        gram = self._choose_from_state(model, state.replace(" ", ""))
        if gram is not None:
            return gram

        all_grams = []
        for transitions in model.values():
            all_grams.extend(transitions.keys())

        if not all_grams:
            return CONTROL_TOKEN

        return random.choice(all_grams)

    def _choose_from_state(self, model: Model, state: str) -> Optional[str]:
        transitions = model.get(state)
        if not transitions:
            return None

        grams = list(transitions.keys())
        weights = list(transitions.values())
        return random.choices(population=grams, weights=weights, k=1)[0]
