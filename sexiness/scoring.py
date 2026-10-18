"""Pure functions for the Sexiness novelty rating cog."""

import random


LOW_QUIPS = (
    "The charm detector might need new batteries.",
    "The meter is buffering. Your glow-up is still loading.",
    "The scanner wants a second opinion.",
    "Low reading, high potential. Science is confusing.",
    "The machine is clearly having a bad day.",
    "You've got mysterious charm. Very mysterious.",
    "This result has been submitted for quality assurance.",
    "The confidence department would like a word.",
)

MID_QUIPS = (
    "Solid rizz. The committee nods approvingly.",
    "A respectable amount of heart-stealing potential.",
    "You're dangerously close to causing a double take.",
    "The charm is there. The meter can feel it.",
    "The frog council has noticed your swagger.",
    "A little sparkle, a little trouble. Nice.",
    "You've got main-character energy on a budget.",
    "Not bad. Even the mirror gave you a wink.",
)

HIGH_QUIPS = (
    "Fire alarms are considering a career change.",
    "The room temperature just went up.",
    "Certified heartthrob material.",
    "Even your reflection is blushing.",
    "The charm levels are becoming a public safety concern.",
    "Someone call the weather service. It's heating up.",
    "The frog council has declared you a certified snack.",
    "You walked in and the soundtrack changed.",
)

LEGENDARY_QUIPS = (
    "The meter has melted. Absolute menace.",
    "100%? The universe requests that you share.",
    "No further testing required. You broke the scale.",
    "The mirror just asked for your autograph.",
    "Emergency meeting: the charm levels are off the charts.",
)


def roll_score() -> int:
    """Roll a new, independent, inclusive 0-100 result for each invocation."""
    return random.randint(0, 100)


def choose_quip(score: int) -> str:
    """Select a lighthearted quip from the matching score range."""
    if not 0 <= score <= 100:
        raise ValueError("score must be between 0 and 100")
    if score == 100:
        return random.choice(LEGENDARY_QUIPS)
    if score <= 33:
        return random.choice(LOW_QUIPS)
    if score <= 66:
        return random.choice(MID_QUIPS)
    return random.choice(HIGH_QUIPS)


def meter(score: int) -> str:
    """Ten-character bar, rounded to the nearest 10%."""
    if not 0 <= score <= 100:
        raise ValueError("score must be between 0 and 100")
    filled = (score + 5) // 10
    return "\u25b0" * filled + "\u25b1" * (10 - filled)
