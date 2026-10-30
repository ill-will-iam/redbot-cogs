# ServerSnapshot — complete accessible Discord guild archive for Fatboy

**What it is:** an owner-only Red-DiscordBot cog that creates **private, checksum-verified, on-VPS archives** of a Discord server's accessible structure, content and media. Reconstruction is deliberately separated into steps: create missing channels/roles, review, then optionally replay historical messages.

**What it is not:** a Discord account backup or a way to bypass server permissions. **Discord does not support restoring deleted messages with the original authors, timestamps, IDs, reactions or original member identities.** Replay explicitly labels each post as historical and posts it from Fatboy. **Bots/apps cannot be reinstalled automatically** (the snapshot saves an inventory). Deleted content predating the archive is unrecoverable.

## Capture coverage

- Guild name, security defaults, AFK timeout, guild icon/banner asset, channel pointers and feature inventory.
- Roles (including permissions, colour, order and managed-role metadata).
- Standard categories, text, announcement, voice, stage, forum and media channel definitions; permission overrides, topics, slowmode, voice limits and forum tags.
- Active and discoverable archived threads, including forum posts; private threads are only captured when Fatboy can access them.
- Every readable message in accessible channels/threads, oldest to newest. Message metadata includes original ID, author display name/user ID, timestamp, text, edit time, pins, embeds, reply references, reaction counts, sticker references, and attachment filenames.
- **Binary copies** of Discord-hosted message attachments, images, GIFs and videos, guild icon/banner, emoji and sticker assets. Downloads are streamed (not buffered in memory); SHA-256 filename deduplicates files.
- Fetchable member roster + role assignments, bots, integration/webhook/invite inventories, ban list and scheduled event inventory. **No bot tokens, webhook URLs, or credentials** are saved.
- Missing permissions, failed downloads and incomplete channel histories are reported in `metadata.json` as capture issues.

Note that Discord may hide content unless **Message Content intent** is enabled. **Server Members intent** is recommended for member-role snapshots. The bot needs **View Channel**, **Read Message History**, and **Connect** for voice-channel history; **Manage Threads** improves archived/private-thread access. Even with administrator permissions, not all private threads and integration configuration are API-accessible.

## Install

Use your existing Red cog installer:

```text
~repo add ill-will-iam https://github.com/ill-will-iam/redbot-cogs
~cog install ill-will-iam serversnapshot
~load serversnapshot
```

If you already have this cog loaded, use `~cog update` and `~reload serversnapshot` (subject to your Red installation and repo alias).

All commands require **Red bot owner** and (on the target guild) **server owner or administrator**. Fatboy needs permissions appropriate to each restore action. Bot role must rank above roles it recreates/assigns. Commands work in a guild (not DM).

## Commands (`~` prefix)

| Command | Operation |
|---|---|
| `~sbackup save` | Archive the current guild; never modifies Discord |
| `~sbackup list [source_guild_id]` | List private snapshots for a guild |
| `~sbackup verify <snapshot_id> [source_guild_id]` | SHA-256 verify every archived file |
| `~sbackup inspect <snapshot_id> [source_guild_id]` | Review capture coverage and skipped/incomplete histories |
| `~sbackup plan <source_guild_id> <snapshot_id>` | Summarize restore plan into current guild |
| `~sbackup restore <source_guild_id> <snapshot_id>` | Recreate missing roles, channels and threads without deleting existing ones |
| `~sbackup replay <source_guild_id> <snapshot_id>` | Republish historical messages **only to newly restored channels/threads** |
| `~sbackup settings <source_guild_id> <snapshot_id>` | Explicitly restore supported guild settings and icon |
| `~sbackup assets <source_guild_id> <snapshot_id>` | Explicitly re-upload missing emoji/stickers if possible |
| `~sbackup members <source_guild_id> <snapshot_id>` | Explicitly reassign roles to members still present; does not remove roles |
| `~sbackup path` / `~sbackup setpath /absolute/path` | View/change private storage destination |
| `~sbackup quota [max_gib]` | View/set media limit (0 = unlimited, default) |

Each **mutating restore command requires a typed confirmation** (e.g. `RESTORE 20261030T120000Z-0123abcd`). Restore and replay keep checkpoints in `restore-state/` so a second run resumes rather than recreating all channels or duplicating previously completed posts. A crash or partial send before a checkpoint can duplicate some already-posted historical content on retry.

### Safe recovery recipe

1. Keep Fatboy running (or reinstall it with **RedBackup**). Add it to the destination server and grant permissions.
2. `~sbackup list <old_guild_id>`, `~sbackup verify <snapshot_id> <old_guild_id>`.
3. `~sbackup plan <old_guild_id> <snapshot_id>` — target is whichever server you send the command in, including a newly created server if the original is gone.
4. `~sbackup restore <old_guild_id> <snapshot_id>`; review the structure.
5. `~sbackup assets ...`, `~sbackup settings ...`, `~sbackup members ...` if desired.
6. `~sbackup replay <old_guild_id> <snapshot_id>` after reviewing the target. Replays can take a long time for very large servers and Discord imposes rate limits and upload limits.

**Existing channels are not deleted or overwritten** by structure restore. Existing channels are reused if an ID or unique name/type/category match exists, but `replay` deliberately **skips existing channels** to prevent accidental duplicate messages. Manual remediation is required for existing channel permissions/settings or replay into a non-new channel.

## Archive on the VPS

Default: `~/discord-server-snapshots/` for the Linux user running Red (usually `/home/redbot/discord-server-snapshots`).

```
discord-server-snapshots/
  snapshots/123456789012345678/
    20261030T120000Z-0123abcd/
      metadata.json
      integrity.json
      messages/<channel_id>.jsonl
      assets/<sha256-content-hash>
  restore-state/<destination-guild-id>/<source-guild-id>/<snapshot-id>.json
```

Directories use mode **0700** and files **0600**. A snapshot is built under a `.partial` directory and made visible only after checksums are written. A failed partial snapshot is not usable for restore. **Existing snapshots are immutable** and no automatic pruning is performed; manage disk usage yourself. Downloads stop when free disk space falls below 512 MiB.

The full archive contains personal and private message content. Protect it as sensitive data, and make **encrypted off-VPS copies**; a VPS loss otherwise destroys both Fatboy and its backups. Never upload archive files into Discord. For off-VPS transfer, copy the snapshot directory with a secure transfer tool or encrypted archive.

## Important limitations

- Bots cannot clone original users, create accounts, invite old members back, recreate application grants, OAuth installations, interaction permissions, webhook tokens, invite URLs or subscriptions.
- External embed/linked media (for example, a Tenor link) may remain as a URL in the metadata rather than a downloaded binary. Cannot restore deleted messages that were never saved. Replayed messages come from Fatboy and keep original author and time **as text labels only**. Replies, stickers, embeds, polls, reactions and original IDs remain in archive metadata but are not re-created as native Discord objects.
- Avatar/emoji/sticker formats, server tier limits, Nitro attachment sizes, channel/role limits, private thread permissions and missing forum/media support in older discord.py versions may prevent identical recreation.
- Rate limits, network interruptions, invalid/revoked CDN URLs and missing permissions can create partial coverage. Check `metadata.json` errors and `histories[].complete` before relying on a backup.
- Managed/bot roles and external app setup cannot be reconstructed without reinstalling the corresponding apps. Ban list, invites and scheduled events are inventory-only. Role order and some channel/server settings may need manual changes.
- No automatic schedule in version 1. Run `~sbackup save` periodically. Store backups off the VPS.

Developed against the Red-DiscordBot v3 cog conventions and discord.py 2.x. Test in a **disposable guild** before restoring a real server.