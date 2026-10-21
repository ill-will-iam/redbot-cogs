# BannedWords — server-wide banned-word game

One **continuous, server-wide** game per Discord guild. No per-channel rounds, timers, or automatic elimination. The state (players, words, strikes) survives bot restarts and cog reloads until a host/moderator explicitly ends the game.

## How it works

1. A moderator enters `~bwg start` once for the whole server. The bot immediately chooses and announces **one random common banned word** (such as `I`, `it`, `what`, `me`, or `you`). This word is added to the server-wide banned list; moderators can remove it with `~bwg remove <word>`.
2. Each player opts in with `~bwg join`. Only opted-in users can earn strikes and submit banned words.
3. Players add a word with `~bwg add pineapple` or a short phrase with `~bwg add rubber duck`.
4. Any message sent **by an opted-in player** that contains a banned word in **any server text channel or thread** earns **one strike per message**, even if it contains multiple banned words. A strike announcement appears in the offending channel unless staff disable announcements.
5. Members can opt out with `~bwg leave` (their prior strikes remain visible), or rejoin at any time.
6. The starter or a moderator enters `~bwg end` to publish the final leaderboard and wipe the active game.

The starter word is selected fresh for each newly started game and is tracked exactly like a player-added word. One-letter words like `I` and `a` are accepted and matched as whole words. Banned words apply immediately and retroactively **do not** score messages sent before the word was added. Matching is case-insensitive, limited to whole words or phrases, and only inspects normal message text (not images or message edits). Discord bot commands are ignored. The best score is the **fewest strikes**.

## Commands

| Command | Purpose | Who |
| --- | --- | --- |
| `~bwg` or `~bwg help` | Overview and help | Everyone |
| `~bwg start` | Begin the server-wide game | Manage Server permission |
| `~bwg join` | Opt in | Everyone |
| `~bwg leave` | Opt out (keep previous strikes) | Players |
| `~bwg add <word>` | Ban a word / phrase (1–48 characters, up to 3 tokens) | Active players |
| `~bwg remove <word>` | Unban a word | Contributor or moderator |
| `~bwg words` | View all banned words | Everyone |
| `~bwg score` | Current standings | Everyone |
| `~bwg status` | Show counts and server-wide status | Everyone |
| `~bwg announce on\|off` | Enable/disable public strike alerts | Manage Server permission |
| `~bwg end` | Explicitly end and clear the game | Starter or moderator |

The `~` is the current Fatboy prefix; Red supports `[p]bwg` with any prefix. `bannedword` and `bannedwords` are alternate root commands. Supports up to 300 banned words per game.

## Installation

```
~load downloader
~repo update redbot-cogs
~cog install redbot-cogs bannedwords
~load bannedwords
~bwg help
```

The bot needs **Message Content Intent**, and Read Message History is not required for live scoring. It needs View Channel and Send Messages permissions to post strike alerts, and Send Messages in Threads for thread alerts. Tracking can run where alerts are not permitted, provided Discord delivers the message event. Bot messages and webhook messages are ignored, and the cog does not delete chat messages.
