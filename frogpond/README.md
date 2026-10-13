# Frog Pond

A quick frog-themed word race for Red-DiscordBot. Players work together to help
a frog hop home while competing for individual points. No sign-up: anyone in the
game channel can guess by typing the answer as an ordinary message.

## Install

As the bot owner, with the repository already added:

```text
$repo update redbot-cogs
$cog install redbot-cogs frogpond
$load frogpond
$frog
```

Enable Message Content Intent so the bot can read guesses. The bot needs View
Channel, Send Messages and Embed Links. Use a regular text channel where members
can send messages. No Manage Messages permission or API key is needed.

## Play

Each crossing has five puzzles by default, sampled without repeats from 100
familiar animals, plants and outdoor words. Each puzzle shows scrambled letters
and a short clue. For example:

> 🐸 Frog Pond • Lily pad 1/5
>
> **Unscramble: `GFOR`**
>
> A pond resident that says ribbit.

Type `frog` to answer. Capitalization and surrounding whitespace do not matter;
the message must contain just the answer. Only the first correct guess counts.
Bots cannot play, and unrelated conversation is ignored.

The first half of the timer offers **3 points**. A halfway hint reveals the first
letter and word length, lowering the award to **2 points**. At three quarters,
a second hint reveals vowel positions, lowering it to **1 point**. One randomly
chosen puzzle per crossing has a **golden fly**, doubling its points. Default
time per puzzle: **25 seconds**. A timeout reveals the answer.

Every solved puzzle moves the frog forward. Solving at least **60%** of the
crossing's puzzles gets it home (three out of five). The final message shows
the individual scores. Earned points are saved immediately per solved puzzle.

## Commands

| Command | Effect |
| --- | --- |
| `$frog` | Start five puzzles in this channel. |
| `$frog start [rounds]` | Start 3–10 puzzles; default five. |
| `$frog rules` | Explain hints, points and the team goal. |
| `$frog top` | Show the server's ten highest scorers. |
| `$frog score` | Show your own points and number of puzzles solved. |
| `$frog stop` | Stop; permitted for the starter, moderators, members with Manage Server, or bot owner. |
| `$frog time <seconds>` | Set 10–60 seconds per puzzle for future games; administrator/Manage Server only. |
| `$help frog` | Show commands, creator and version. |

Only one crossing can run per server. Scores and timer settings survive reloads
and restarts; active crossings do not. Stopping a game preserves points already
earned. Disabling the whole `FrogPond` cog cancels an active game; a watcher checks
once per second even when chat is quiet. Individual command-disabling settings
control those commands; use the whole-cog setting to stop gameplay listeners.

## Other games and logging

Frog Pond refuses to start in a channel with an active AcroGame round. If AcroGame
starts there later, Frog Pond cancels without consuming more guesses or awarding
more points. Start a new crossing after AcroGame ends. Run other chat games in a
different channel or at a different time; no integration with their listeners is
assumed.

Frog Pond leaves guesses and game messages in Discord. AdminLog needs no special
exclusion for this game; any edits or deletions are handled according to its
existing settings. Markov and WordStats continue their existing behavior.
Leaderboard mentions do not ping players. Guess handling respects Red's cog
disable, ignored-channel and user allow/block settings.

## Storage and maintenance

No database, network lookup or additional Python package is used. The packaged
word bank is loaded once; only active game state and two tasks per active server
are kept in memory. Red Config stores user IDs, total points and solved counts,
plus the server timer. Guess text is not archived by the cog.

Red user-data deletion removes the user's scores across all servers and cancels
any active game they started or scored in, including a pending winning answer.
Writes and deletion requests share a lock so a tally cannot recreate removed
data. Existing Discord messages remain under server administration.

Update an installed copy with:

```text
$cog update frogpond
$reload frogpond
```

Validation uses real Red/discord.py command classes with simulated Discord
events and Config persistence. Live Discord installation is a separate check.
