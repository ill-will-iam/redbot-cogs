# Haven — reversible Discord lockdown for Red-DiscordBot

Haven is an **owner-only** channel visibility lockdown. It is NOT a server wipe,
and **does not delete messages, channels, or roles, kick/ban members, revoke
other admins, or grant anyone Administrator**.

## Setup

Install from the existing cog repository:

```text
$repo update redbot-cogs
$cog install redbot-cogs haven
$load haven
```

## Commands (the server owner only)

- `$haven inspect` — preview how many channels and overwrites need changes;
  list administrator roles that will bypass lockdown.
- `$haven seal` — prompts for `SEAL <server_id>` confirmation, then saves the
  original overwrites and hides channels from non-administrators.
- `$haven status` — reports whether an active snapshot exists.
- `$haven restore` — prompts for `RESTORE <server_id>` confirmation, then
  re-applies the saved permission overwrites and clears the snapshot upon
  successful restoration.

## Important limitations

- Discord Administrator permissions **bypass** all channel overwrites. Other
  administrators are not modified by this cog. Review roles using `inspect`.
- The bot **must already** have the Administrator permission. It is never
  granted by this cog.
- Discord server ownership is permanent and belongs to the actual guild owner;
  the bot does not acquire or transfer that status.
- Channel/category changes made after sealing can conflict with restored
  overwrites. Backup your Red data before large administrative changes.
- This saves current channel permission overwrites, not a copy of server data.
  It cannot recover deleted channels/messages.
- Categories and channels synced to those categories are treated together to
  avoid unnecessary channel/category permission desynchronization.
- In rare cases a role/member or channel deleted since sealing cannot be
  restored. Haven retains the snapshot when an error occurs.
- Lockdown does not remove members from an existing voice connection, and
  permissions can be cached briefly on clients. Audit logs show changes.

**Security:** Because each subcommand is checked against Discord's actual
server owner ID, Red bot owners and arbitrary admins do not get access unless
they are also the owner of that Discord server.
