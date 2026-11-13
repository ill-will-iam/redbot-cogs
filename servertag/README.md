# ServerTag — Redbot V3

Automatically assigns a role when someone **equips and displays this server's Discord Server Tag**. Removes it when they switch to another tag or unequip/hide the tag.

## Installation

```text
~repo update redbot-cogs
~cog install redbot-cogs servertag
~load servertag
```

Requires Manage Roles and Server Members Intent. Place the bot's top role above the reward role.

## Configuration

```text
~tagrole setrole @Tag Supporter
~tagrole status
~tagrole sync
```

| Command | Description |
| --- | --- |
| `~tagrole setrole @Role` | Configure and enable the reward role |
| `~tagrole check @Member` | Refresh one person's tag and correct their role |
| `~tagrole sync` | Audit and reconcile existing members |
| `~tagrole status` | Inspect configuration and bot permissions |
| `~tagrole enable` / `disable` | Resume/pause automatic updates |
| `~tagrole clear` | Forget configuration without stripping roles |

The alias `~servertag` also works. Only server administrators and users with Manage Server may configure the cog. The server owner can configure any manageable role; non-owners cannot configure a role above their own role hierarchy.

## Safety and limitations

The cog checks `user.primary_guild.identity_guild_id`, not tag text, and requires `identity_enabled=true`. Gateway `GUILD_MEMBER_UPDATE` events and member-join checks drive automatic updates; the manual `sync` command can repair missed changes after bot downtime. Unknown/missing identity data is skipped rather than causing a role removal. Disabling or reconfiguring the reward role intentionally leaves previously assigned roles untouched.

This uses Discord's lower-level HTTP and gateway data and has not been live-tested on this Redbot instance. Test tag equip/change/remove after installation.
