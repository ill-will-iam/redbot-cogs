# FATBOY Information Cog

Custom bot profile with current uptime, Red/discord.py/Python versions, gateway latency,
server count, approximate member slots, number of loaded cogs, a list of cog names,
a configurable description and a purple-accented Discord embed.

## Install on Fatboy

In Discord, as the bot owner:

```text
~repo update redbot-cogs
~cog install redbot-cogs fatboyinfo
~load fatboyinfo
~info
```

The bot's prefix is currently `~`.

## Commands

| Command | Purpose |
| --- | --- |
| `~info` | FATBOY profile when its alias is available. |
| `~fatboy` | FATBOY profile regardless of the `info` command conflict. |
| `~fatboyinfo`, `~fbinfo` | Additional profile command aliases. |
| `~fatboyset show` | View current settings; owner only. |
| `~fatboyset owner Will` | Set public owner label; owner only. |
| `~fatboyset description Your text here` | Set description; owner only. |
| `~fatboyset color #7C3AED` | Customize embed color; owner only. |
| `~fatboyset infoalias on` | Attempt to bind `~info`; owner only. |
| `~fatboyset infoalias off` | Restore the original `~info` command; owner only. |

## About command compatibility

Redbot's built-in Core cog already has an `info` command. On load, FatboyInfo
temporarily removes **only Core's** `info` and registers its own replacement.
On cog unload or alias disable, it unregisters its own alias and restores the
original Core command. If a different cog owns `info`, FatboyInfo leaves that
command untouched, and `~fatboy` remains available.

All profile settings persist in Red's Config storage and never affect the
actual bot owner/permissions. Member counts add the cached counts for each
server; users who share servers may be counted more than once.

If embeds are disabled or unavailable, the cog sends a readable text profile
instead. Requires no external API keys or extra dependencies.

## Update after a code change

```text
~cog update fatboyinfo
~reload fatboyinfo
```
