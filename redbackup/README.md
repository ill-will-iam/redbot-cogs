# RedBackup

Owner-only backup commands for **Red-DiscordBot 3.5.24+**. Local VPS snapshot, no uploads or network transfer.

## Usage (bot prefix `$`)

| Command | Purpose |
| --- | --- |
| `$backup` | Create and integrity-check a timestamped ZIP snapshot |
| `$backup create` / `$backup now` | Same as `$backup` |
| `$backup list` | See recent archives |
| `$backup verify [latest\|filename]` | Re-check CRC, per-file SHA-256 digests and ZIP integrity |
| `$backup path` | Print destination and protected sources |
| `$backup setpath /absolute/path` | Configure destination; must not overlap the backup sources |
| `$backup keep 10` | Keep last N archives (1–100); default 10 |
| `$backup prune` | Apply retention immediately |

Default path: `~/redbot-backups/<Red-instance-name>/` **as resolved for the user running the bot**. Directory mode 0700 and archive mode 0600. The bot user must be able to write to the destination.

## What's captured

- Entire Red instance data directory (including cog data, config, downloaded repo metadata and local files under this directory)
- Installed third-party cog source code and any additional registered custom cog paths, *if outside the instance data directory*
- Current instance's registration information from Red's config.json, including its backend settings (do not share)
- Red/Python version, installed Python package versions, and loaded extension inventory
- SQLite databases (`.db`, `.sqlite`, `.sqlite3`) via SQLite's online backup API instead of raw copying
- Per-file SHA-256 digests within manifest, ZIP CRC validation, plus overall ZIP digest in local `.sha256` sidecar

Symlinks and build/git caches are skipped. Files maintained outside Red data/cog paths, such as service unit files, system packages, python virtual environment and external databases, are **not** captured. Non-JSON Red storage backends are deliberately rejected rather than silently omitted.

## Important: what 'live' means

The bot continues running while this archive is created. SQLite snapshots are individually consistent; however, JSON and other files may change during copying, and multiple SQLite databases are not captured as one atomic transaction. **No live archive can guarantee a fully consistent restore point of the whole bot.**

For critical updates, Red's officially supported approach is: `$shutdown` → activate the Red venv → `redbot-setup backup <instance>` → restart bot. The official command backs up cog data but not third-party cog code; this cog's live archive includes source code for standard registered cog paths.

## Restoration (offline/manual, never from Discord)

1. **Stop the bot** and make a fresh copy of the *current* instance data somewhere safe before changing anything.
2. Run `$backup verify` **before** shutting down, or verify the ZIP CRC/SHA-256 hashes manually from the shell.
3. Extract the archive into a **staging directory** on the VPS, e.g. `mkdir -m 700 /home/redbot/restore-staging && cd /home/redbot/restore-staging && unzip /path/to/redbackup-...zip`.
4. Inspect `metadata/manifest.json` and `metadata/instance-registration.json`. `instance-data/` contains the saved Red data; `installed-cogs/` and `custom-cogs-N/` contain cog code for external source paths. Use the manifest's `source_paths` to determine what goes where.
5. With Red still stopped, restore only the relevant files, **after backing up the live state**, preserving filesystem permissions/ownership. Do not blindly overwrite a Red install or replace another instance's config.json. Recreate/merge the single instance registration as needed.
6. Restore Python dependencies and services separately as needed, then start `red-fatboy.service` and check the logs.

**Sensitive:** archives may include the bot's token, guild config, message content and personal user data. Keep backups private (0700 directory / 0600 file), do not attach them to Discord, and keep a protected off-VPS copy for host failure.
