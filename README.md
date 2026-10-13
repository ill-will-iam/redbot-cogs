# Redbot Cogs

A starter repository for custom [Red-DiscordBot](https://docs.discord.red/en/stable/) V3 cogs.

| Cog | Command | Purpose |
| --- | --- | --- |
| `hellocog` | `[p]coghello` | Confirms the repository's sample cog is installed and loaded. |
| `acrogame` | `[p]acro start` | Starts an acronym game using **3–5 random letters**, chat submissions, anonymous voting, and points. |
| `pp` | `$pp` | Sends `:pp1:`, 0–7 copies of `:pp2:`, and `:pp3:` without spaces or line breaks. |
| `adminlog` | `$adminlog channel #admin-logs` | Logs member, message, voice, channel, role, and server changes. |

`[p]` means your bot's command prefix. If your prefix is `$`, use `$coghello`.

## Put this repository on GitHub

1. Sign in and open [GitHub's new repository page](https://github.com/new).
2. Name the repository `redbot-cogs` and add the description `Custom cogs for Red-DiscordBot.`
3. Choose **Public** if you want easy installation through Red's Downloader without Git authentication. Public repositories expose their files to everyone. A private repository needs Git authentication configured on the machine running Red.
4. Turn **Add README** on so the repository is initialized. Leave **Add .gitignore** set to **None**; a starter ignore file is included here.
5. Choose a license if you are ready to allow others to use your code under it. For an open source project, **MIT** is one common option. You can also leave the license unset and decide later.
6. Click **Create repository**.
7. Extract `redbot-cogs-starter.zip`. In the repository, choose **Add file → Upload files**.
8. Drag the **contents** of the extracted `redbot-cogs` folder into the uploader. Keep the `hellocog` folder intact. Upload `.gitignore`, `README.md`, and the root `info.json` beside that folder. Do not upload the ZIP or place everything inside another `redbot-cogs` folder.
9. If the uploader reports that `README.md` will be replaced, that is expected: this README replaces the initial generated one.
10. Enter the commit message `Add starter Red cog repository`, choose to commit directly to the default branch for this initial setup, and save the commit.
11. Confirm that the main repository page lists `hellocog`, `info.json`, and `README.md` at its top level. If `.gitignore` was skipped by your file picker, use **Add file → Create new file** to add it.
12. Edit the `author` list in each `info.json` if you prefer another author name.

A **commit** is a saved change in the repository's history.

## Install the sample cog

As the bot owner, run these commands in Discord. Replace `YOUR_USERNAME` with your GitHub username and `[p]` with your bot's prefix:

```text
[p]load downloader
[p]repo add redbot-cogs https://github.com/YOUR_USERNAME/redbot-cogs
[p]cog list redbot-cogs
[p]cog install redbot-cogs hellocog
[p]load hellocog
[p]coghello
```

The final command should reply:

> Your Red cog repository is working!

If Downloader requests confirmation, read its prompt and confirm to continue.

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

## Validation

This starter's Python syntax, JSON metadata, package structure, and ZIP integrity were checked. It has not been run against a live Red instance; the `coghello` command above provides that check on your bot.

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
