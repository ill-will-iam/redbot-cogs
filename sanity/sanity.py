"""A quick, good-natured sanity check, just for fun."""

import random

import discord
from redbot.core import commands


LOW_QUIPS = (
    "Your last brain cell has left the group chat.",
    "Reality called. You sent it straight to voicemail.",
    "Your thoughts are currently supervised by a raccoon.",
    "The frog council has requested an emergency meeting.",
    "Instructions unclear. Befriended the toaster.",
    "You're running entirely on vibes and questionable decisions.",
    "Your brain's check-engine light is flashing.",
    "Common sense is on an unpaid leave of absence.",
    "Your imaginary lawyer has advised you to remain silent.",
    "One more minor inconvenience and you become a swamp cryptid.",
)

MID_QUIPS = (
    "Mostly operational. Ignore the mysterious rattling noise.",
    "One foot in reality, one foot in a suspicious puddle.",
    "Calm on the outside, circus music on the inside.",
    "All systems nominal. Please ignore the smoke.",
    "Reasonable decisions are being considered, not guaranteed.",
    "The frog council approves, with minor reservations.",
    "You're sane enough to know better, but will you?",
    "Your brain is currently in power-saving mode.",
    "Functioning normally, according to very generous standards.",
    "You've got all your ducks in a row. They're facing different directions.",
)

HIGH_QUIPS = (
    "Suspiciously well-adjusted. We have questions.",
    "You might actually read the instructions today.",
    "Reality and you are currently on speaking terms.",
    "Certified to operate heavy thoughts.",
    "You're the designated responsible adult. Terrifying.",
    "The frog council grants you one whole wise decision.",
    "Your emotional support brain cell reported for duty.",
    "Clear skies upstairs. Enjoy it while it lasts.",
    "Remarkable composure. Did you get a software update?",
    "Even your inner goblin is using an inside voice.",
)


def choose_quip(score: int) -> str:
    """Choose a playful comment based on a 0–100 score."""
    if score <= 33:
        return random.choice(LOW_QUIPS)
    if score <= 66:
        return random.choice(MID_QUIPS)
    return random.choice(HIGH_QUIPS)


class Sanity(commands.Cog):
    """Check your entirely unscientific daily sanity percentage."""

    __author__ = "Will"
    __version__ = "1.0.0"

    @commands.command(name="sanity")
    async def sanity(self, ctx: commands.Context):
        """Roll a fresh 0–100% sanity score with a funny quip."""
        score = random.randint(0, 100)
        quip = choose_quip(score)
        filled = (score + 5) // 10
        meter = "▰" * filled + "▱" * (10 - filled)
        name = discord.utils.escape_markdown(
            discord.utils.escape_mentions(ctx.author.display_name)
        )

        await ctx.send(
            f"🧠 **{name}'s Sanity Check**\n"
            f"**Today's sanity: {score}%**\n"
            f"{meter}\n"
            f"*{quip}*"
        )
