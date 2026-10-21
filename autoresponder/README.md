# AutoResponder — Fatboy Red-DiscordBot Cog

Make Fatboy speak automatically when someone says a configured **word or short phrase** in **any Discord server where Fatboy is present**, including threads. There is **one bot-global rule list**, shared across every guild and saved across bot restarts.

## Installation

```text
~load downloader
~repo update redbot-cogs
~cog install redbot-cogs autoresponder
~load autoresponder
```

Create your first reply (**bot owner only**, because rules affect every server):

```text
~ar add hello | Hey there!
~ar add frog | Ribbit!
~ar add good morning | Rise and shine!
```

When someone says "Hello everyone!" in **any** server where Fatboy can read messages, Fatboy sends "Hey there!" as a **normal bot message**. If you add a trigger from Server A, it immediately applies in Servers B, C, and everywhere else Fatboy is present. Triggers are case-insensitive. Only whole words are matched: `cat` matches "a cat!" but does **not** match "scatter". Phrases can have up to five words. Single-letter triggers like `I` also work.

## Commands

| Command | Permissions | Description |
| --- | --- | --- |
| `~ar add word \| response` | Bot owner | Add a trigger and response |
| `~ar edit word \| response` | Bot owner | Change the existing response |
| `~ar remove word` | Bot owner | Delete a trigger |
| `~ar list` | Everyone | View all configured triggers |
| `~ar show word` | Everyone | View the configured response |
| `~ar test example text` | Everyone | Preview the reply without actually triggering it |
| `~ar enable` / `~ar disable` | Bot owner | Enable or pause all replies |
| `~ar cooldown 15` | Bot owner | Throttle each trigger within each channel (0–300 seconds) |
| `~ar status` | Everyone | Show enabled status, number of triggers and cooldown |
| `~ar help` | Everyone | Command help |

Fatboy's prefix is currently `~`; the cog works with whatever prefix Red uses. `~autoresponder` is an alias for `~ar`.

## Behavior and limits

- Uses **one global list** of words and replies for every Discord server where Fatboy is present. There is no per-server rule isolation; adding, editing or deleting a trigger immediately affects every server.
- Applies to all text channels and threads that Fatboy can read in those servers.
- Ignores bots, webhooks, and bot command invocations (including unknown commands beginning with the configured prefix).
- **One reply per chat message**. When several triggers match, the longest matching phrase wins.
- A reply may be up to **1000 characters**, and a trigger may be up to **60 characters / five words**.
- Supports **150 triggers globally**, shared by the entire bot.
- Default cooldown is **15 seconds per trigger and channel**; it remains independent in each server/channel. Set `~ar cooldown 0` to turn throttling off globally.
- Sends responses without Discord mentions or pings, even if an administrator enters `@everyone` in the response.
- Rules and settings persist across bot restarts; rate-limit timestamps do not.
- On first load of v2, legacy per-server rules are **merged into the global list**. Existing global entries take precedence; if multiple old servers used the same word, the lowest guild ID wins. The original per-server settings remain stored as an unmodified backup. Per-server enable/cooldown settings are not migrated; global defaults are enabled and 15 seconds.
- Only bot owners can change the global rules, enable/disable them, or change the cooldown. Members of every server can inspect and test configured rules.
- The cog does **not** remove messages, store user IDs, or save message content.

## Required permissions

Enable **Message Content Intent** in the Discord developer portal for the bot. If Red's cog is disabled in a particular guild, replies there are suppressed, even though the global rules stay configured. Grant Fatboy **View Channel** and **Send Messages** in channels where replies should appear, plus **Send Messages in Threads** for thread replies.
