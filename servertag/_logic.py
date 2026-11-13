"""Pure rules for Discord Server Tag + boost role reconciliation."""

from typing import Any, Dict, Mapping, Optional


def wearing_guild_tag(primary_guild: Any, guild_id: int) -> Optional[bool]:
    """Return whether the tag is displayed; None means the data is unavailable."""
    if primary_guild is None:
        return False
    if not isinstance(primary_guild, Mapping):
        return None
    enabled = primary_guild.get("identity_enabled")
    if enabled is None:
        return False
    if enabled is not True:
        return False
    identity_guild_id = primary_guild.get("identity_guild_id")
    if identity_guild_id is None:
        return False
    try:
        return int(identity_guild_id) == int(guild_id)
    except (ValueError, TypeError):
        return None


def booster_state(member_payload: Mapping[str, Any], boost_role_id: Optional[int]) -> Optional[bool]:
    """Use premium_since when available, otherwise Discord's managed booster role."""
    if "premium_since" in member_payload:
        return member_payload["premium_since"] is not None
    roles = member_payload.get("roles")
    if isinstance(roles, list) and boost_role_id is not None:
        try:
            return boost_role_id in {int(value) for value in roles}
        except (TypeError, ValueError):
            return None
    return None


def wanted_roles(
    tag: Optional[bool],
    boosting: Optional[bool],
    has_basic_role: bool,
    tag_role_id: Optional[int],
    boost_tag_role_id: Optional[int],
    boost_role_id: Optional[int],
) -> Dict[int, bool]:
    """Map each configured reward role ID to whether it should be present.

    Unavailable tag/boost state is not interpreted as a negative observation.
    Boost-tag replaces basic-tag if configured; booster reward is independent.
    """
    wanted: Dict[int, bool] = {}
    if boost_role_id is not None and boosting is not None:
        wanted[boost_role_id] = boosting
    if tag is not None:
        if boost_tag_role_id is not None:
            if boosting is not None:
                wanted[boost_tag_role_id] = bool(tag and boosting)
                if tag_role_id is not None:
                    wanted[tag_role_id] = bool(tag and not boosting and has_basic_role)
        elif tag_role_id is not None:
            if boosting is True:
                wanted[tag_role_id] = bool(tag)
            elif boosting is False:
                wanted[tag_role_id] = bool(tag and has_basic_role)
            elif has_basic_role:
                wanted[tag_role_id] = bool(tag)
    return wanted


def changed_roles(old: Mapping[str, Any], new: Mapping[str, Any]):
    """Human-readable role and channel-overwrite differences between snapshots."""
    changes = []
    old_roles, new_roles = old.get("roles", {}), new.get("roles", {})
    for role_id in sorted(set(old_roles) | set(new_roles), key=int):
        previous, current = old_roles.get(role_id), new_roles.get(role_id)
        if previous is None:
            changes.append(f"Added role {current['name']} ({role_id})")
        elif current is None:
            changes.append(f"Deleted role {previous['name']} ({role_id})")
        else:
            for key in ("name", "permissions", "position", "managed", "hoist", "mentionable"):
                if previous.get(key) != current.get(key):
                    changes.append(
                        f"Role {current['name']} ({role_id}): {key} changed "
                        f"{previous.get(key)!r} -> {current.get(key)!r}"
                    )
            a, b = previous.get("overwrites", {}), current.get("overwrites", {})
            for channel_id in sorted(set(a) | set(b), key=int):
                if a.get(channel_id) != b.get(channel_id):
                    changes.append(
                        f"Role {current['name']} ({role_id}): channel {channel_id} "
                        "overwrite changed"
                    )
    return changes
