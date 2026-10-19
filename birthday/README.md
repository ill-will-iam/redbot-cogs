# Birthday — Red-DiscordBot cog

A lightweight birthday cog with per-server saved birthdays and optional birthday announcements. No external API keys or third-party Python dependencies beyond Red-DiscordBot.

## Member commands

| Command | Action |
| --- | --- |
| $birthday 07/27/1985 | Set your birthday immediately. |
| $birthday set 07/27/1985 | Alternate syntax to set it. |
| $birthday set 07/27 | Set it without sharing a birth year. |
| $birthday | View your own birthday and countdown. |
| $birthday @member | View another member's birthday (month/day). |
| $birthday today | Today's birthdays in the server's timezone. |
| $birthday upcoming | The next ten birthdays. |
| $birthday upcoming 20 | The next twenty birthdays (max 20). |
| $birthday age on | Opt into displaying your age. |
| $birthday age off | Keep your age hidden (default). |
| $birthday remove | Erase your saved birthday in this server. |

## Server administrator commands

| Command | Action |
| --- | --- |
| $birthday channel #birthdays | Enable birthday announcements in the named channel. |
| $birthday channel off | Turn announcements off. |
| $birthday timezone America/Vancouver | Set server timezone (default UTC). |
| $birthday time 09:00 | Set 24-hour local announcement time (default 09:00). |

**Important:** Announcement messages appear at or after the configured local time if the bot is available; they are checked every five minutes and sent at most once per calendar day per server. They never ping anyone. Multiple birthdays are combined into one message. February 29 birthdays are observed on February 28 in non-leap years.

A user's birthday is **not imported from Discord**; they must set it manually. Birthday month/day is viewable by members of the server. Birth year is not publicly displayed by the cog by default, but typing $birthday 07/27/1985 in a public channel **does expose the full date in the original command message**, potentially also to logging bots. For privacy, users may prefer omitting the year, or using a restricted channel to set their birthday. Announcements are disabled until an administrator sets a channel.

## Installation

To install via Red's Downloader:

~~~text
$load downloader
$repo update redbot-cogs
$cog install redbot-cogs birthday
$load birthday
$help birthday
~~~

If the repository isn't added yet, run:

~~~text
$repo add redbot-cogs https://github.com/ill-will-iam/redbot-cogs
~~~

The bot needs permission to **Send Messages** in the configured birthday channel. Member lookup works best with the **Server Members Intent** enabled.
