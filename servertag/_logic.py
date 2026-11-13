"""Small, dependency-free helpers for server identity matching."""
from typing import Any, Mapping, Optional


def wearing_guild_tag(primary_guild: Any, guild_id: int) -> Optional[bool]:
    """True if a user's visible server identity belongs to guild_id; None if unknown."""
    if primary_guild is None:
        return False
    if not isinstance(primary_guild, Mapping):
        return None
    if primary_guild.get("identity_enabled") is not True:
        return False
    identity_guild_id = primary_guild.get("identity_guild_id")
    if identity_guild_id is None:
        return False
    try:
        return int(identity_guild_id) == int(guild_id)
    except (ValueError, TypeError):
        return None
