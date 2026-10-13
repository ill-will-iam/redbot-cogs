# Daily Drawings

One daily topic, fifteen minutes of drawing on paper, then community voting for
props and cheers. No economy rewards, score database, API keys or extra packages.

## Install and configure

Create `#daily-drawings` in Discord, then run as the bot owner:

```text
$repo update redbot-cogs
$cog install redbot-cogs dailydrawings
$load dailydrawings
$draw channel #daily-drawings
$draw time 20:00 America/New_York
$draw status
```

The bot needs **View Channel, Send Messages, Embed Links and Read Message
History** there. Members need View Channel, Send Messages and Attach Files.
Enable **Message Content Intent** in Discord's Developer Portal and in the
running Red instance so ordinary image attachments reach the bot. The same
intent already used by AdminLog and Frog Pond is sufficient. No Manage Messages,
Add Reactions or View Audit Log permission is required by this cog.

Requires Red 3.5.24 or later and Python 3.9 or later with timezone data available
on the host. Standard Linux timezone packages supply this data.

## The daily flow

1. At **8:00 PM Eastern** by default, the bot announces "It's time to draw!" and
   gives everyone the same randomly selected topic.
2. Members have **15 minutes** to create a drawing using pen, pencil, crayons,
   markers or other physical materials on paper. Digital drawing, AI, tracing
   apps and digital assistance are prohibited. A photo or scan of the finished
   paper drawing is allowed for submission.
3. Submit **one attached JPG, PNG or WebP image** in the configured channel.
   Links and animated GIFs are not submissions. Each artist gets one entry;
   another valid photo from that artist replaces the previous entry until the
   deadline. Captions are optional. Original Discord submissions are kept.
4. At least **three distinct artists** must have submitted eligible images when
   drawing closes. With fewer entries, the bot thanks everyone and closes the
   round without a vote.
5. The bot posts an entry gallery, in shuffled order, with a vote button under
   each image. Voting opens after the complete gallery is posted and lasts
   **five minutes**. Anyone with access to the channel may vote, subject to Red's
   allow/block and ignore settings. Each person has one vote, may change it,
   and cannot vote for their own entry. Feedback is private to the voter.
6. The most votes wins. A tie produces joint winners; zero votes produces a
   thank-you for all artists. The result is simply **props, cheers and applause**.
   Vote buttons are disabled when the round closes.

The image format check establishes that a supported photo attachment was sent;
it cannot establish whether the art was drawn physically, digitally or with AI.
This is an honour rule supervised by staff. Use `$draw remove @member` for an
ineligible entry and `$draw cancel` when a round needs to be stopped. The cog
does not advertise automated AI detection or anonymous submissions. Original
posts expose their authors; the gallery uses entry numbers.

## Change the daily time

Use 24-hour time:

```text
$draw time 19:00
$draw time 20:00
$draw time 21:00
```

The default timezone is **America/New_York**, meaning Eastern local time with
daylight-saving changes handled automatically. Thus 20:00 is 8 PM EST in winter
and 8 PM EDT in summer. Keep that timezone or supply another IANA timezone:

```text
$draw time 20:00 America/New_York
```

Changes apply to future rounds. Changing the time does not reset today's
announcement marker or extend a round already in progress.

## Commands

| Command | Effect |
| --- | --- |
| `$draw` / `$draw status` | Show channel, schedule, active round, intent and permissions. |
| `$draw channel #daily-drawings` | Set the channel and enable daily announcements. |
| `$draw time HH:MM [timezone]` | Change the daily time and optionally the timezone. |
| `$draw start` | Announce today's challenge immediately; uses today's daily slot. |
| `$draw cancel` | Cancel the current round. Does not schedule a second challenge today. |
| `$draw off` | Pause the schedule and stop any active round. Set the channel again to resume. |
| `$draw remove @member` | Remove an entry and votes for it. Original photos remain. |
| `$help draw` | Show help, creator and version. |

Configuration, starting, cancellation and entry removal require a Red
administrator or Manage Server permission. Participants upload photos and click
buttons; they do not need to run commands.

Removing an entry during voting cancels the vote if fewer than three eligible
drawings remain. Deleting a source submission or editing away its selected
attachment removes that entry. Deleting a gallery post or the announcement
cancels the round. A source deletion while the gallery is being prepared also
cancels the round so an incomplete gallery does not get a vote.

## Scheduling and recovery

The scheduler checks every 30 seconds while the bot is running. It records the
date in the configured timezone before announcing, preventing a second daily
invitation after a restart. Manual starts count as that day's invitation too.

After a short outage, an unannounced challenge can start within **one hour** of
the configured daily time. Outside that window it waits for the next day.
This prevents an evening drawing invitation appearing the following morning.
An announcement send failure retains the day's marker to avoid duplicate posts;
check permissions and logs if a configured challenge fails to appear.

Active drawing/voting state is saved, so ordinary reloads and restarts recover
the original deadline, eligible entries and votes. Voting buttons are registered
again after startup. Votes cannot be cast while the bot is offline. A drawing
window more than five minutes past its deadline is closed on recovery rather
than starting a stale vote; an expired voting window is tallied using saved votes.
A restart during gallery construction or result posting discards that incomplete
phase instead of publishing duplicate galleries/results.

Disabling the whole `DailyDrawings` cog cancels an active round and clears its
saved state. A watcher checks once per second even in a quiet channel. Individual
command-disabling settings control those commands; use the whole-cog setting
to stop automatic announcements and submission/vote listeners.

There are **120 topics** across fantasy, reality, funny, serious, scary and
nature. Each server uses a saved shuffled deck without repeating a topic until
the deck is exhausted. The bot only launches a daily challenge after a channel
has been configured and enabled.

## Data and administration

Red Config stores the schedule, channel ID, daily marker and remaining topic
keys. While a round is active, it also stores entrant/voter IDs, submitted and
gallery message IDs, attachment IDs/URLs and vote choices for recovery. This
active state is cleared on completion, cancellation or an affected user-data
deletion request. No image files are downloaded or stored on the VPS. There is
no persistent win history or leaderboard.

Red user-data deletion cancels a round involving that person as an entrant or
voter and clears its stored state, including rounds not yet restored at startup.
State writes and deletion share a lock. Already posted Discord images, gallery
messages and results remain subject to server administration.

Other cogs keep their existing settings. AdminLog may record human deletions and
edits here; this cog does not delete submission messages or need AcroGame's
anonymous-game suppression. A dedicated drawing channel avoids chat-game
listeners consuming other games' answers.

Validation covers **40 tests** using real Red command classes and JSON storage:
Eastern scheduling and daylight-saving changes, once-per-day and catch-up
windows, supported attachments, replacement entries, the three-artist minimum,
single/changeable/self votes, ties, full timer flow, restart recovery, deletions,
disabled-cog cleanup and privacy races. Live Discord setup remains a separate
check on the running bot.

Update an installed copy with:

```text
$cog update dailydrawings
$reload dailydrawings
```
