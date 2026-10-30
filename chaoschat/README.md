# ChaosChat 1.1 — for fatboy (Red-DiscordBot 3.5+)

A spontaneous, profanity-heavy, no-API-key conversational menace. Designed for channels where **adult humour is welcome**, not family-friendly spaces. Replies to random human messages, answers questions with surreal nonsense, asks strange questions, and can continue a conversation **once** if the same person responds. A direct mention of fatboy or a reply to one of his messages can also trigger a response.

## Install

Copy the `chaoschat` directory into a Redbot Downloader repository, or add the directory to your own `redbot-cogs` repository. Then use your Discord prefix (shown as `~` below):

```text
~repo add willcogs https://github.com/ill-will-iam/redbot-cogs
~cog install willcogs chaoschat
~load chaoschat
~chaoschat on
```

If your existing Downloader repo is named something else, use its actual name instead of `willcogs`. **The `chaoschat` folder must be committed to the remote repository before Downloader can install it**. Otherwise install locally by copying the directory into your Redbot's cog path and using `~load chaoschat`.

## Recommended setup

```text
~chaoschat on
~chaoschat chance 8
~chaoschat mode feral
~chaoschat slavic 25
~chaoschat language random
~chaoschat cooldown 75
~chaoschat channelcooldown 120
~chaoschat usercooldown 240
~chaoschat direct on
~chaoschat followups on
~chaoschat channel block #staff
~chaoschat status
```

To limit it to one or two channels:

```text
~chaoschat channel only #general
~chaoschat channel add #off-topic
```

`~chaoschat` and `~chaoschat help` show all settings. Commands are available to server admins and members with `Manage Server` permissions. Configuration and reply count are per-server. ChaosChat starts **disabled** in each server until activated.

## Slavic outbursts

`~chaoschat slavic 25` makes roughly 25% of the **wild** or **feral** replies
come out in a Slavic language. Use `~chaoschat slavic 0` to disable them or
`~chaoschat slavic 100` for every wild/feral reply. `~chaoschat language random`
randomly picks Russian, Polish, Ukrainian, Czech or Serbian; choose any one
with `~chaoschat language polish` or the short codes `ru`, `pl`, `uk`, `cs`, `sr`.
Slavic responses are intentionally in the language itself rather than English
translations. Language choice is random and is not based on users' identities.

## Behavior

- All dialogue is generated offline from original adult-oriented lines, lightweight topic matching, and question detection. **This is not a language model or an AI chat API**.
- **8% default chance** per eligible human message, AFTER cooldowns and channel checks.
- Ignores bot/webhook messages, DMs, commands, short non-directed messages, excluded channels, and any server where the cog has been disabled.
- Direct @mentions and replies to bot messages may bypass random odds, but still have their own spam limits. Mention-as-prefix real Redbot commands still take priority.
- Optional single follow-up within 90 seconds if the same person posts again in that channel, with a 72% chance and a 3-second minimum gap. Never generates an ongoing reply loop.
- Uses Discord replies without pinging authors or anyone else. Works in threads, with rules inherited from their parent text channels.
- Does not store chat transcripts, message content, or persistent user IDs. The cooldown cache is in memory only and resets when the cog unloads.

### Requirements

- Red-DiscordBot 3.5+ on Python 3.9+.
- Discord's **Message Content Intent** must be enabled in the application's Developer Portal, and enabled for the running bot.
- The bot needs permission to read and send messages in the eligible channel (or `Send Messages in Threads` for threads).
- No extra Python dependencies, tokens, AI services, or payments. Expect profanity, mature jokes, and occasional untranslated foreign-language messages.
