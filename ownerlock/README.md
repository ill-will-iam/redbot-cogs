# OwnerLock — selectively owner-only cog commands

OwnerLock is a Red-DiscordBot 3.5+ cog for Fatboy that lets its bot owner make **specific loaded cogs' commands owner-only** in *every* server (and DMs). It does not change everyone else's access to unprotected cogs.

The policy persists when the bot restarts, the guarded cog reloads, or a protected cog is temporarily unloaded. If that cog is loaded later with the same name, its commands are still protected.

## Install

```text
~repo update redbot-cogs
~cog install redbot-cogs ownerlock
~load ownerlock
```

## Commands

| Command | Meaning |
| --- | --- |
| `~olock cogs` | Display all loaded cogs and which are protected |
| `~olock protect AutoResponder` | Allow only Red bot owners to invoke AutoResponder commands |
| `~olock protect Purge` | Protect every Purge command |
| `~olock unprotect Purge` | Restore normal Purge command permissions |
| `~olock list` | List protected cogs, including any currently unloaded |
| `~olock inspect AutoResponder` | Check whether a cog has automatic event listeners |

All OwnerLock commands require **bot ownership**. Discord server administrators and server owners cannot manage the protection or use locked commands unless they are also registered Red bot owners.

You must use the **loaded cog's actual name**, not its Python folder or a command prefix; `~olock cogs` shows the names. Matching is case-insensitive. Policies are global, not tied to the server where the command is used.

## What gets blocked

A global non-overridable bot command check rejects commands and nested subcommands from a protected cog when the caller is not a Red bot owner. This applies across every guild and in DMs. Other cogs remain unchanged.

**Important limitation:** Red/discord.py command checks do **not** intercept automated `on_message`/`on_member_join` listeners, scheduled jobs, background tasks, or separate slash/app command handlers. `~olock protect` reports detected listeners, and `~olock inspect` displays a cog's listeners. A listener-based cog needs explicit checks inside that cog to enforce owner-only event handling.

Our **AutoResponder** and **BannedWords** cogs include an optional OwnerLock integration so their `on_message` listeners ignore messages from non-owners when those cogs are protected. This integration does not apply automatically to third-party cogs. For other listener-based cogs, treat the OwnerLock setting as a **command lock**, not a complete operational lock.

**Security note:** Red can have more than one configured bot owner. Every configured Red bot owner can pass owner-only checks; OwnerLock does not restrict commands to one hardcoded Discord ID.

## Examples

```text
~olock cogs
~olock inspect Purge
~olock protect Purge
~olock protect AutoResponder
~olock list
~olock unprotect Purge
```

Protecting a cog does not delete its data, remove the cog, or disable the bot's other commands. Removing or unloading OwnerLock removes its global command check until it is reloaded.
