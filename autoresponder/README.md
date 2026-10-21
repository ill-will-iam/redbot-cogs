# AutoResponder — Fatboy Red-DiscordBot Cog

Make Fatboy speak automatically when someone says a configured **word or short phrase** anywhere in the server, including threads. Each Discord server has independent rules that survive bot restarts.

## Installation

```text
~load downloader
~repo update redbot-cogs
~cog install redbot-cogs autoresponder
~load autoresponder
```

Create your first reply (requires **Manage Server** permission):

```text
~ar add hello | Hey there!
~ar add frog | Ribbit!
~ar add good morning | Rise and shine!
```

When someone says "Hello everyone!" in chat, Fatboy sends "Hey there!" as a **normal bot message**. Triggers are case-insensitive. Only whole words are matched: `cat` matches "a cat!" but does **not** match "scatter". Phrases can have up to five words. Single-letter triggers like `I` also work.

## Commands

| Command | Permissions | Description |
| --- | --- | --- |
| `~ar add word \| response` | Manage Server | Add a trigger and response |
| `~ar edit word \| response` | Manage Server | Change the existing response |
| `~ar remove word` | Manage Server | Delete a trigger |
| `~ar list` | Everyone | View all configured triggers |
| `~ar show word` | Everyone | View the configured response |
| `~ar test example text` | Everyone | Preview the reply without actually triggering it |
| `~ar enable` / `~ar disable` | Manage Server | Enable or pause all replies |
| `~ar cooldown 15` | Manage Server | Throttle each trigger within each channel (0–300 seconds) |
| `~ar status` | Everyone | Show enabled status, number of triggers and cooldown |
| `~ar help` | Everyone | Command help |

Fatboy's prefix is currently `~`; the cog works with whatever prefix Red uses. `~autoresponder` is an alias for `~ar`.

## Behavior and limits

- Applies to all server text channels and threads that Fatboy can read.
- Ignores bots, webhooks, and bot command invocations (including unknown commands beginning with the configured prefix).
- **One reply per chat message**. When several triggers match, the longest matching phrase wins.
- A reply may be up to **1000 characters**, and a trigger may be up to **60 characters / five words**.
- Supports **150 triggers per server**.
- Default cooldown is **15 seconds per trigger and channel**; set `~ar cooldown 0` to turn throttling off.
- Sends responses without Discord mentions or pings, even if an administrator enters `@everyone` in the response.
- Rules and settings persist across bot restarts; rate-limit timestamps do not.
- The cog does **not** remove messages, store user IDs, or save message content.

## Required permissions

Enable **Message Content Intent** in the Discord developer portal for the bot. Grant Fatboy **View Channel** and **Send Messages** in channels where replies should appear, plus **Send Messages in Threads** for thread replies.
