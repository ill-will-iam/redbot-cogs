# Redbot Cogs

Custom [Red-DiscordBot](https://docs.discord.red/en/stable/) V3 cogs for Fatboy. This repository includes games, moderation, backups, an economy, and utility tools. The catalog below tracks the cog packages on the `main` branch.

| Cog | Command | Purpose |
| --- | --- | --- |
| [`hellocog`](hellocog/) | `$coghello` | Simple installation smoke test. |
| [`acrogame`](acrogame/) | `$acro start` | Acronym game with private submissions, voting, and leaderboard. |
| [`serveraudit`](serveraudit/) | `$audit` | Read-only audit of server settings, bots, roles and channel permissions. |
| [`adminlog`](adminlog/) | `$adminlog status` | Logs server, member, message, role, channel and voice changes. |
| [`dailydrawings`](dailydrawings/) | `$draw status` | Scheduled physical-paper drawing prompts, entries and voting. |
| [`frogcrib`](frogcrib/) | `$crib challenge @member` | Two-player 121-point cribbage with optional Ribbucks rewards. |
| [`frogpond`](frogpond/) | `$frog` | Timed word unscrambling with frog-themed points and challenges. |
| [`haven`](haven/) | `$haven nuke preview` | Reversible lockdown or separately confirmed owner-only destructive server reset. |
| [`revamp`](revamp/) | `~revamp preview` | Preview and apply reusable Discord server layouts; archives existing channels in custom-theme mode. |
| [`markov`](markov/) | `$markov stats` | Markov models, size reports, admin enrollment and channel modeling. |
| [`pp`](pp/) | `$pp` | Random-length custom emoji chain. |
| [`line`](line/) | `$line` | 45-second group line-up, 3-second countdown and final cheers. |
| [`notes`](notes/) | `$notes` | Staff-only server management checklists, named boards, priorities, due dates, assignments and memos. |
| [`redbackup`](redbackup/) | `$backup` | VPS-local live backup snapshots, integrity checks and retention. |
| [`serversnapshot`](serversnapshot/) | `~sbackup save` | Private Discord server snapshots of channels, roles, accessible history and media; controlled restoration. |
| [`ribbit`](ribbit/) | `$ribbit` | Royal Ribbit Reserve frog economy using Ribbucks. |
| [`dig`](dig/) | `~d` / `~dig` | Dig 3 times per 10 minutes for valuables and future fishing bait; sell loot for Ribbucks. |
| [`chaoschat`](chaoschat/) | `~chaoschat` | Random chaotic bot replies with configurable behavior. |
| [`runescapex`](runescapex/) | `$rsx help` | OSRS-only player hiscores, boss records, gains and GE prices. |
| [`sanity`](sanity/) | `$sanity` | Random sanity meter and humorous response. |
| [`sexiness`](sexiness/) | `$sexy` | Random sexiness percentage with a playful quip; optional @member target. |
| [`autorole`](autorole/) | `~autorole add @Member` | Silent per-server join roles, multiple roles, and screening-aware assignment. |
| [`birthday`](birthday/) | `~birthday 01/01/2000` | Global birthday profiles, countdowns and per-server daily announcements. |
| [`truthordare`](truthordare/) | `~tod` / `~truth` / `~dare` | 233 R-rated truth/dare prompts for age-restricted channels, voluntary turn-taking and admin controls. |
| [`snipe`](snipe/) | `$snipe` | Review recent deleted messages; admin history clearing. |
| [`purge`](purge/) | `~purge 25` | Silent moderator-only message cleanup by count, member/ID, links, bots, keywords, attachments and message range. |
| [`bannedwords`](bannedwords/) | `~bwg start` | Continuous server-wide opt-in game, seeded with a random common banned word; players add words and collect strikes until manually ended. |
| [`autoresponder`](autoresponder/) | `~ar add hello \| Hey there!` | One bot-global trigger list: owner-managed autoresponses in every server, with independent channel cooldowns. |
| [`ownerlock`](ownerlock/) | `~olock protect Purge` | Selectively restrict cog commands to Red bot owners, with event-listener inspection. |
| [`rolecontrol`](rolecontrol/) | `~roleme <role>` | Owner-only self-assignment/removal of server roles and a role listing command. |
| [`imageedit`](imageedit/) | `~img grayscale` | Offline image edits for attachments/replies: crop, resize, rotate, filters, captions, and sticker-sized PNGs. |
| [`voicetranscribe`](voicetranscribe/) | `~vt on` | Locally transcribe native Discord voice messages into text replies (server opt-in). |

`[p]` means the bot's configured command prefix. Fatboy currently uses `~` (for example, `~coghello`).

## OwnerLock — selectively owner-only cogs

Install with `~repo update redbot-cogs`, `~cog install redbot-cogs ownerlock`, and `~load ownerlock`. Run `~olock cogs` to see available cog names and `~olock protect Purge` to restrict that cog's commands to Red bot owners in **every server** and DMs. Use `~olock unprotect Purge` to restore normal access, and `~olock inspect CogName` to check for event listeners. Command checks do not automatically prevent background events or slash commands; AutoResponder and BannedWords now cooperate with OwnerLock for message listeners. See [ownerlock/README.md](ownerlock/README.md) for details.

## AutoResponder — global word triggers in every Fatboy server

To install: `~repo update redbot-cogs`, `~cog install redbot-cogs autoresponder`, `~load autoresponder`. A bot owner can configure `~ar add hello | Hey there!` once to make Fatboy respond to **hello** in all servers where the bot is present, including threads. Old per-server triggers are merged into the global rule list on the first v2 load. Use `~ar edit`, `~ar remove`, `~ar list`, `~ar test`, `~ar cooldown`, and `~ar enable` / `~ar disable` to manage rules. Responses ignore bots and commands, never ping members, and persist across restarts. See [autoresponder/README.md](autoresponder/README.md) for the full command list.

## BannedWords server-wide game

Run `~repo update redbot-cogs`, `~cog install redbot-cogs bannedwords`, then `~load bannedwords`. A moderator starts a game with `~bwg start`, which chooses and announces one random common banned word. Players opt in with `~bwg join` and add banned words with `~bwg add <word>`. Words apply to opted-in players across all server channels and threads, one strike per offending message. The game persists across restarts and continues until `~bwg end`. See [bannedwords/README.md](bannedwords/README.md) for the complete command list.

## AutoRole join assignments

Use `~repo update redbot-cogs`, `~cog install redbot-cogs autorole`, `~load autorole`, then `~autorole add @Member`. Give Fatboy **Manage Roles**, position its highest role above the assigned role, and enable **Server Members Intent**. The cog waits for Membership Screening completion if necessary, and does not post a message for joins. See [autorole/README.md](autorole/README.md) for all commands.

## Install a cog

For an existing Fatboy installation using the `~` prefix, Red's Downloader should already have this repository registered. To add a cog such as Purge:

```text
~load downloader
~repo update redbot-cogs
~cog install redbot-cogs purge
~load purge
~help purge
```

If the repository isn't registered yet, first run:

```text
~repo add redbot-cogs https://github.com/ill-will-iam/redbot-cogs
```

Replace `purge` with any cog package name in the catalog. Cog commands require the relevant roles, permissions and Discord intents described in their docs. Always review a cog's `info.json` and `README.md` before installing.

## Repository layout

Each cog package belongs directly in the repository root.

| Path | Purpose |
| --- | --- |
| `README.md` | Repository description and instructions. |
| `.gitignore` | Exclusions for local Git operations. |
| `info.json` | Repository metadata for Red. |
| `hellocog/__init__.py` | Loads the cog with the async `setup` function. |
| `hellocog/hellocog.py` | The cog's Python implementation. |
| `hellocog/info.json` | Cog metadata, requirements, and data statement. |

`acrogame/` is the acronym game package. Running `[p]acro start` chooses 3–5 random letters (not preset words). Players type their answers directly into the game channel; the bot stores and deletes those messages, then reveals anonymous submissions for voting after 30 seconds. Note that Discord messages may briefly appear before deletion.

## Add another cog

1. Create a folder at the repository root with a lowercase package name, such as `acro`.
2. Add `__init__.py` with an async `setup(bot)` function.
3. Add the cog's implementation file and its own `info.json`.
4. Describe any stored user data accurately and implement Red's data-deletion hook if needed.
5. Commit the files to GitHub.
6. Run `[p]repo update redbot-cogs`, then `[p]cog install redbot-cogs acro` and `[p]load acro`.

## Install AcroGame

```text
[p]repo update redbot-cogs
[p]cog install redbot-cogs acrogame
[p]load acrogame
[p]acro start
```

When the submissions are revealed, **type only the number** of the entry you want to vote for (for example, `1`, `2`, or `3`) directly into the same channel. Your vote message is deleted after it is captured, self-votes are rejected, and you can change your vote until voting ends. The older `$acro vote <number>` command still works, but is no longer needed. To begin a game, use `$acro start`; `$acro start KZP` supplies custom 3–5-letter prompts. The game awards leaderboard points, and optional Red economy credits can be configured with `$acro setcoins`.

## Update installed code

After committing changes to an already installed cog:

```text
[p]cog update hellocog
```

Follow Red's reload prompt if it appears. If you need to reload manually, run `[p]reload hellocog`.

`repo update` refreshes the repository clone; it does not update the installed cog copies. Use `cog update` for those.

## Keep configuration separate

Commit cog source files and documentation. Keep bot tokens, API keys, passwords, and Red's live data directory outside the repository. Git's ignore rules do not prevent you from manually uploading a file through GitHub's website.

## Validation and documentation

Each cog has a `info.json` manifest. Some cogs also have their own `README.md` with full setup, security and data-handling details. Tests under `tests/` cover selected modules, but a successful GitHub commit does not guarantee live Redbot integration. Test new or updated cogs on your running bot.

**Documentation maintenance:** GitHub does not regenerate this file when a cog is created or modified. Add new cogs to the catalog and update their command descriptions in the same commit as code changes; the README catalog check in CI catches unlisted cog packages.

## References

- [Red's publishing guide](https://docs.discord.red/en/stable/guide_publish_cogs.html)
- [Red's cog creation guide](https://docs.discord.red/en/stable/guide_cog_creation.html)
- [Red's Downloader commands](https://docs.discord.red/en/stable/cog_guides/downloader.html)
- [GitHub repository creation](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)
- [Uploading files to GitHub](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)

## Install PP

Use the custom server emojis `:pp1:`, `:pp2:`, and `:pp3:`, and ensure the bot can use them. Discord stores their names as `pp1`, `pp2`, and `pp3`; the surrounding colons are shortcode notation. The cog sends each emoji’s full Discord code (`<:name:id>` or `<a:name:id>`) so it renders as an image. With the bot's `$` prefix:

```text
$repo update redbot-cogs
$cog install redbot-cogs pp
$load pp
$pp
```

Each use chooses a random number from **0 through 7 inclusive** for the middle emoji. Zero sends `:pp1::pp3:`; seven sends `:pp1::pp2::pp2::pp2::pp2::pp2::pp2::pp2::pp3:`. The response contains only the emojis with no spaces or line breaks. Static and animated custom emojis are supported. Missing or unusable emojis produce an explanatory message. The cog stores no user data.

## Install AdminLog

As the bot owner:

```text
$repo update redbot-cogs
$cog install redbot-cogs adminlog
$load adminlog
$adminlog channel #admin-logs
$adminlog test
$adminlog status
```

Replace `#admin-logs` with your chosen text channel. Administrators or members with Manage Server can configure the cog. The destination is saved per server and survives restarts. Use `$adminlog off` to stop logging; existing records remain.

**Logged events:** member joins/departures; nickname, member-role, timeout, server-avatar and username/profile changes; bans/unbans; message deletions, bulk deletions and text edits; voice joins/leaves/moves, mute/deaf, streaming, camera and stage-audience changes; channel creation/deletion/settings changes; role creation/deletion/settings and permission changes; server name, description, verification, content filter and icon changes. Records contain UTC timestamps and relevant IDs. This cog reports the changed member/object or message author; it does not infer the moderator responsible, or distinguish voluntary departures from kicks. Automatic timeout expiry may not dispatch a member-update event.

**Required setup:** enable Server Members Intent and Message Content Intent for the bot in Discord's Developer Portal (**Bot → Privileged Gateway Intents**) and in the running Red instance; restart after changing intents. Keep guild/message/voice/moderation intents enabled. `$adminlog status` reports the active intents. Give the bot View Channel, Send Messages, Embed Links and Attach Files in the log channel, plus visibility into source channels. View Audit Log is not required.

**Message records:** deleted text and original edited text come from Red's existing message cache. If a message is uncached, only the available event IDs/current edit text can be logged. Messages sent while the bot was offline or already evicted from its cache cannot be recovered after deletion. Enable Message Content Intent to receive ordinary message text and attachments. Long records are attached as complete UTF-8 text files rather than silently cut off; attachment URLs are recorded, but original files are not downloaded and those URLs may expire. Log-channel messages and cached messages authored by this bot are excluded to prevent noise and recursion. Embed-only updates are ignored.

Only the log-channel ID is stored in the cog's configuration. Discord log records include user IDs, names and available message text; administrators manage their retention and removal. Red's user-data deletion hook does not delete already posted Discord records. No extra message archive or user database is maintained by this cog. Logging is best effort while the bot is online and has the needed permissions.

Validation: source syntax, metadata and simulated event/recording behavior are tested; check `$adminlog test` and real events on your running bot after installation.

### AcroGame integration

AdminLog automatically pauses message deletion, bulk-deletion and edit records in the active AcroGame channel for the entire round. It resumes normal message logging when the round ends or is stopped. Other channels and member/voice/server events continue to be logged. No channel exclusion command is needed, so games can run in general chat. Update and reload both cogs to enable this integration.

AcroGame remembers up to 10,000 IDs of messages it deletes (including invalid submissions and vote messages) in memory. AdminLog also filters those IDs after a round finishes, preventing delayed deletion events from revealing game entries or votes. No extra message content is archived, and these suppression IDs are cleared when AcroGame is reloaded or the bot restarts.

```text
$cog update acrogame adminlog
$reload acrogame adminlog
```

Reloading AcroGame cancels an active round; update between games. This integration affects AdminLog only; other logging bots/cogs have their own settings.

### AcroGame cancellation safeguards

AcroGame checks Red's disabled-cog state before capturing/deleting submissions or votes and before awarding points. A watcher also checks active rounds once per second, so disabling the cog cancels a round even if nobody sends another message. Round cancellation clears its captured submissions, ballot and votes and stops both background tasks. AdminLog then resumes ordinary message logging in that channel; already deleted game-message IDs remain suppressed as described above.

```text
$command disablecog AcroGame
$command enablecog AcroGame
```

When Red processes a user-data deletion request, an active round involving that user as an author or voter is cancelled. The cog waits for the cancelled tasks to finish, then removes the user's leaderboard records from all servers. Leaderboard writes and deletion requests are serialized so an in-flight tally cannot recreate the removed record. Unrelated rounds keep running, and normal games can still award points.

### Ignore automatic bot cleanup

To omit CatBot's image deletions and edits while retaining human message records:

```text
$adminlog ignorebot @CatBot
$adminlog status
```

Select the actual bot member when mentioning it. This setting is per server and persists across restarts. Use `$adminlog unignorebot @CatBot` to resume its message records. Member, voice and server events are not excluded by this setting.

For ignored bots (and this bot itself), AdminLog retains up to 10,000 recent message IDs and their guild/author IDs in memory, without message contents. This lets it suppress automatic deletions even after the original message has left Red's cache. It cannot identify the author of an uncached deletion it never observed; configure the exclusion before triggering new bot replies. The ID registry resets on reload/restart. Existing posted logs are not removed.

## Refreshed trivia questions

See [trivia_lists/README.md](trivia_lists/README.md) for the Lily Pad Trivia pack: 300 easy/medium questions across 10 broad topics, plus a combined `lily_mix` list. Upload `trivia_lists/lists/lily_mix.yaml` with `$triviaset custom upload` and play `$trivia lily_mix`. The full question/answer catalog and review notes are included. These custom lists work with the existing Trivia cog; bundled categories remain available under their old names.

## Install Frog Pond

Frog Pond is a lightweight frog rescue word game. Unscramble a nature word and
type it in chat before the timer ends. The first correct guess earns points and
moves the frog forward. Hints reduce the available points, and one golden-fly
round doubles them. Solve at least 60% of a crossing together to get the frog home.

```text
$repo update redbot-cogs
$cog install redbot-cogs frogpond
$load frogpond
$frog
```

Default: ten puzzles, 25 seconds each. Use `$frog start 20` for a longer crossing,
`$frog rules` for instructions, `$frog top` for the server leaderboard, and
`$frog stop` to stop. Administrators can set the next game's timer with
`$frog time 30`. There are 114 distinct answers of seven or more letters, with
harder clues, no API keys and no extra packages. Crossings accept 10–20 puzzles.
Each server's shuffled question deck is saved through reloads and restarts;
answers do not repeat until the deck is exhausted, and crossings spanning a
reshuffle still contain no duplicates. Existing points and timer settings remain.
Message Content Intent and permission to send messages/embeds are required.

See [frogpond/README.md](frogpond/README.md) for scoring, privacy, permissions and
AcroGame coexistence details. Creator and version appear in `$help frog`.



## Install Daily Drawings

Daily Drawings announces a shared paper drawing topic at **8 PM Eastern** by
default. Members have **15 minutes** to draw and upload a photo. At least
**three artists** are required for **five minutes** of button voting. Everyone
gets one changeable vote and cannot vote for themselves; the most votes earns
props and cheers, with ties sharing the applause. The physical-only rule is
enforced by staff; uploaded images alone do not establish how artwork was made.

```text
$repo update redbot-cogs
$cog install redbot-cogs dailydrawings
$load dailydrawings
$draw channel #daily-drawings
$draw time 20:00 America/New_York
$draw status
```

Change the time later with `$draw time 19:00` or `$draw time 21:00`. Eastern
daylight-saving changes are handled automatically. There are 120 rotating
topics spanning fantasy, real life, funny, serious, scary and nature. Active
drawing/voting windows and votes survive normal restarts; no image files,
leaderboard or prizes are stored on the VPS. Use `$draw remove @member` for
ineligible entries and `$draw off` to pause. See
[dailydrawings/README.md](dailydrawings/README.md) for permissions, commands,
scheduling/recovery details and the data statement.


## Install Sanity Check

Use the established repository on your bot:

```text
$repo update redbot-cogs
$cog install redbot-cogs sanity
$load sanity
$sanity
```

Each `$sanity` run randomly generates a new score. Scores of 0–33 get a low-sanity quip, 34–66 a mid-sanity quip, and 67–100 a high-sanity quip. The cog saves no user data and needs no extra dependencies.


## Markov chain statistics and manual enrollment

This repository includes a compatibility fork of ZanCogs Markov. See [markov/README.md](markov/README.md) for behavior, opt-out safeguards, and important backup/switching instructions before replacing the installed ZanCogs package. New commands: `$markov stats`, `$markov stats @member`, `$markov statsall`, `$markov userenable @member`, `$markov userdisable @member`, and `$markov userlist`. Existing stored models use the unchanged Red Config identifier and `Markov` class.

## Frog Cribbage

Play traditional two-player cribbage using `$crib challenge @member`. Full rules, configurable rewards, match stats and safeguards are documented in [frogcrib/README.md](frogcrib/README.md). If `ribbit` is loaded and configured, completed matches can award Ribbucks. Hands are sent privately by DM.

```text
$repo update redbot-cogs
$cog install redbot-cogs frogcrib
$load frogcrib
$crib challenge @member
```

## Haven

Haven provides a **reversible, read-only server mode** through `seal`/`restore`, and a separate **destructive reset** through `nuke`. Reset requires the caller to own both the bot and server: it pauses invites, removes assignable roles from other members, clears @everyone permissions, and permanently deletes old channels/messages, leaving a private owner channel. Use `haven nuke preview` before confirmation. Managed roles cannot be removed; privileged managed roles block the reset. Delegates can operate reversible lockdown only. Deleted content cannot be restored.

```text
$repo update redbot-cogs
$cog install redbot-cogs haven
$load haven
$haven inspect
$haven seal
$haven restore
```

Read [haven/README.md](haven/README.md) for the required permissions, confirmation flow, limitations, and safe recovery procedure before activating a lockdown.

## RedBackup

RedBackup creates verified, timestamped, local VPS ZIP snapshots of Red's instance data and registered cog paths. It is **bot-owner-only** and does not send backups to Discord or off-server storage.

```text
$repo update redbot-cogs
$cog install redbot-cogs redbackup
$load redbackup
$backup
$backup list
$backup verify
$backup path
```

**Important:** live snapshots are not guaranteed to be atomic. Protect the backups because they can contain tokens and user data. For a critical restoration point, read the offline backup and restoration guidance in [redbackup/README.md](redbackup/README.md).

## RuneScapeX — Old School RuneScape only

RuneScapeX uses public Old School RuneScape hiscores and OSRS Wiki Grand Exchange data. It supports skill ranks, levels and XP, boss/clue rankings, player comparison, price lookup and gains since the last snapshot. It has no RS3 commands and needs no API key.

```text
$repo update redbot-cogs
$cog install redbot-cogs runescapex
$load runescapex
$rsx help
$rsx profile Zezima
$rsx price Abyssal whip
```

See [runescapex/README.md](runescapex/README.md) for the command catalog, aliases, caching and API caveats.

## Snipe — recently deleted messages

Moderators can view the most recently deleted **cached** message in the current channel. Supplying a number displays a paginated viewer for up to 50 messages. A server administrator can clear the stored history.

```text
$repo update redbot-cogs
$cog install redbot-cogs snipe
$load snipe
$snipe
$snipe 5
$snipe clear
$snipe clear here
```

- History is isolated by server and channel, kept in RAM, capped at 50 entries per channel, and expires after 24 hours.
- `$snipe` requires moderator privileges or Manage Messages. `$snipe clear` and `$snipe clear here` require administrator privileges or Manage Server.
- Text is recoverable only for messages that were in the running bot's Discord message cache. Deleted attachments are shown as links that might expire; missing/uncached messages cannot be reconstructed. Enable Message Content Intent and allow the bot to read channels and send embeds.
- Cache history disappears on a bot restart or cog reload; clearing deletes entries immediately from the in-memory store.


## Install Line

Start or join a timed group line-up in any server text channel. Each member who types `$line` during the 45-second window receives a personalized response. The bot then counts down `3...`, `2...`, `1...` (one second each) and posts `🥂 Cheers, enjoy! 🥂`. One round runs per channel; repeat attempts and late joining are handled without creating a second round.

```text
$repo update redbot-cogs
$cog install redbot-cogs line
$load line
$line
```

See [line/README.md](line/README.md) for usage and data-handling details.

## Notes — staff management checklists

Notes keeps per-server private management task boards and memos using Red's Config persistence. Lists can be created, renamed, viewed and deleted when empty. Managers can add, prioritize, assign, edit, complete, reopen, move and delete tasks; due dates are tracked in UTC but do not trigger reminders. Access is limited to bot admins/owners or members with Manage Server permission. See [notes/README.md](notes/README.md) for the full command reference and privacy notes.

```text
$repo update redbot-cogs
$cog install redbot-cogs notes
$load notes
$help notes
$notes
$notes add Review moderator permissions
$notes board create moderation
$notes addto moderation Review ban appeals
```


## Birthday — global user profiles

Set a birthday **once** with `~birthday 01/01/2000` or `~birthday 01/01` (year optional); it follows the user to **every server using the same Fatboy instance**. `~birthday today` and `~birthday upcoming` list only members of the current server. Admins can configure announcements per server using `~birthday channel #birthdays`, `~birthday timezone America/Vancouver`, and `~birthday time 09:00`. Dates can also be registered privately in DMs. Previous per-server records require explicit `~birthday import` by their owners. See [birthday/README.md](birthday/README.md) for full commands and privacy details.
