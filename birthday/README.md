# Birthday — Red-DiscordBot cog

**Set your birthday once, across every server using the same Redbot instance.** Birthdays and age preferences are stored as global user data. Each server independently configures its own daily birthday announcement channel and timezone. No external API keys or third-party Python packages are needed.

## Member commands

| Command | Action |
| --- | --- |
| `~birthday 01/01/2000` | Save your global birthday once (example only). |
| `~birthday set 01/01/2000` | Alternative save command. |
| `~birthday 01/01` | Save month/day without a birth year. |
| `~birthday` | Check your own birthday and countdown. |
| `~birthday @member` | Check another member's global birthday in a shared server. |
| `~birthday today` | Show today's birthdays of users in this server. |
| `~birthday upcoming` | Show the next ten birthdays in this server. |
| `~birthday upcoming 20` | Show the next twenty birthdays. |
| `~birthday age on` | Opt in to showing your age globally. |
| `~birthday age off` | Hide your age globally (default). |
| `~birthday import` | Import your own old per-server birthday from the current server. |
| `~birthday remove` | Delete your global birthday plus old local records. |

**You can set, view, or remove your own global birthday in a direct message to Fatboy.** Viewing someone else's birthday, lists, imports, and admin settings are server-only.

## Server administrator commands

| Command | Action |
| --- | --- |
| `~birthday channel #birthdays` | Enable announcements in this server's selected text channel. |
| `~birthday channel off` | Disable announcements in this server. |
| `~birthday timezone America/Vancouver` | Set this server's timezone (default UTC). |
| `~birthday time 09:00` | Set the local announcement time (default 09:00). |

Announcements are checked every five minutes and sent at most once a day per server after the specified local time, when the bot is available. They do **not** ping anyone; multiple birthdays are combined into one announcement. February 29 birthdays are observed on February 28 in non-leap years.

## Updating from the older per-server version

Existing per-server birthday records are **not automatically published globally**. A member who already registered under the old version should run `~birthday import` in a server where that date was saved. This imports the existing date to their global profile, disables age visibility as a privacy precaution, and erases that user's old per-server birthday records. Alternatively, run `~birthday set MM/DD/YYYY` to replace old data and start fresh. Deleting a birthday with `~birthday remove` also removes old local records.

## Privacy

Month/day is visible to anyone who shares a server where the cog can be used; age is only shown if its owner opts in. Year is stored when provided and isn't printed by birthday lookups or announcements, though members could infer the year if age is visible. A full birthdate typed in a **public command message can still be read there** and may be logged by other bots; to keep the birth year private, DM Fatboy or omit the year entirely. The global data belongs to **this bot instance only**, not all Discord bots. Birthday announcements require each server's admin to opt in.

## Installation/update

```text
~load downloader
~repo update redbot-cogs
~cog install redbot-cogs birthday
~load birthday
```

For an already installed cog:

```text
~repo update redbot-cogs
~cog update birthday
~reload birthday
```

If not previously added:

```text
~repo add redbot-cogs https://github.com/ill-will-iam/redbot-cogs
```

The bot needs permission to send messages in its configured birthday channel. Enabling the Server Members Intent improves member lookup.
