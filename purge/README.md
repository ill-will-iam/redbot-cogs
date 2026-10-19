# Purge

Moderator-only selective chat cleanup for Red-DiscordBot v3.5+ (discord.py v2).

## Commands

Use the bot's **current prefix** (Fatboy uses `~`). Each command affects **only the current channel or thread**, never the entire server.

| Command | Action |
| --- | --- |
| `~purge 25` | Delete the most recent 25 messages (excluding the command). |
| `~purge all 50` | Same as above. |
| `~purge user @Member 25` | Delete up to 25 messages from that member. |
| `~purge userid 123456789012345678 25` | Same for an author ID (including members who left). |
| `~purge me 25` | Delete your own last 25 messages. |
| `~purge bots 25` | Delete up to 25 messages from bots. |
| `~purge webhooks 25` | Delete up to 25 webhook messages. |
| `~purge links 25` | Delete up to 25 messages containing links or Discord invites. |
| `~purge files 25` | Delete up to 25 messages containing uploads. Aliases: attachments, media. |
| `~purge embeds 25` | Delete up to 25 messages containing embeds. |
| `~purge contains 25 unwanted text` | Delete up to 25 messages containing a phrase (case-insensitive). |
| `~purge before MESSAGE_ID 25` | Delete 25 messages older than the specified message. |
| `~purge after MESSAGE_ID 25` | Delete 25 messages newer than the specified message. |

For user, bots, webhooks, links, files, embeds and me, you can add a **scan limit** after the deletion count, e.g. `~purge user @Member 25 2000`. The default history scan limit is 1,000 messages. Keyword searches also scan 1,000 messages.

## Limits and safeguards

- Maximum **500 matching messages deleted** per invocation.
- Maximum **5,000 messages scanned** per invocation.
- Purging **more than 100** messages requires the invoker to reply `yes` within 30 seconds.
- Commands require a Red moderator or the **Manage Messages** permission, and the bot needs **Manage Messages** and **Read Message History**.
- The command itself is excluded from matching and is removed after a successful purge. A temporary results summary disappears after 10 seconds.
- Discord bulk deletion cannot include messages over 14 days old. discord.py falls back to slower individual deletes for older messages.
- Deleted messages cannot be restored by this cog. Other cogs (such as Snipe or AdminLog) may independently record deletion events.
- No persistent user data is created.

## Install/update

```text
~repo update redbot-cogs
~cog install redbot-cogs purge
~load purge
~help purge
```

After an update:

```text
~cog update purge
~reload purge
```
