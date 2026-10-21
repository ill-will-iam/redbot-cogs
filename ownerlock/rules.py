"""Pure helpers for OwnerLock's case-insensitive cog access rules."""


def canonical_cog_name(name: str) -> str:
    """Normalize cog names, preserving spaces in qualified cog names."""
    return " ".join(name.strip().casefold().split())


def command_allowed(cog_name: str, protected: set, is_bot_owner: bool) -> bool:
    """A protected cog permits commands from Red's bot owners only."""
    return canonical_cog_name(cog_name) not in protected or is_bot_owner
