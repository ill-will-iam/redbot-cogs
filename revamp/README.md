# Revamp Cog v0.3 — import custom themes or start a brand-new server

A deliberately simple Red-DiscordBot (Red V3) cog for fatboy. There are **two ways** to use it:

**A. Starting a new server:** Fatboy inventories the current channels, categories and roles, selects a built-in starter layout, and shows what is missing. You preview and explicitly confirm. It **does not archive, delete, rename, move or edit existing channels**.

**B. Revamping an established server:** Design a theme with North, upload its JSON file, preview, and confirm. This retains the v0.2 archival workflow for eligible old public channels. The imported theme decides roles, categories, channel topics, welcome messages, rules and channel permissions.

`[p]` means the bot's prefix. Examples below use `~` (use `$` if that's what fatboy currently uses).

## New-server starter

```text
~revamp starter     # Read the existing server structure and select the starter template
~revamp preview     # Show the channels/roles to add and anything being left alone
~revamp apply       # Display the plan and require typed confirmation to deploy
```

The default starter adds **4 categories, 8 channels and 2 unassigned roles** on an otherwise empty server:

- **START HERE** — `#rules` (read-only), `#announcements` (read-only)
- **COMMUNITY** — `#general`, `#introductions`, `#off-topic`
- **VOICE** — `General Voice`, `Gaming`
- **STAFF** — `#staff-chat` (private to Moderators and members with applicable administrator permissions)
- **Roles:** `Members` (teal), `Moderators` (blue)
- Five basic rules posted and pinned **only if the `#rules` text channel is created by this run**.

Fatboy's “review” is a **local inventory**, not AI analysis. It checks which starter channel names/types and categories already exist. A matching channel anywhere on the server is **left in place**, not moved, modified, renamed, or posted into. New channels may be created under an existing same-named category; intended per-channel overwrites are applied to **new** channels in that case, without changing existing category access.

No users are assigned to the new roles automatically. The starter has no user or guild-specific branding and can later be replaced with a theme generated in ChatGPT.

## Our custom JSON themes (unchanged workflow)

```text
~revamp load        # In the same Discord message, attach the JSON file from North
~revamp preview
~revamp apply       # This mode archives eligible old public text/voice channels
```

Uploading a theme replaces the pending starter selection **for this server only**. A completed starter deployment does not prevent later custom revamps: when you apply a custom theme later, eligible starter public channels can be archived as part of that new revamp (with normal preview and confirmation). Different Discord servers have independent selected templates. See `revamp/example-theme.json` for the editable schema.

### Optional recovery

```text
~revamp old                # Show archived old channels (custom theme mode)
~revamp restore #old-name  # Restore one channel
~revamp undo               # Best-effort rollback of the latest revamp
~revamp keep #important    # Protect a public channel against custom revamp archiving
```

Rollback preserves conversations by moving new channels into a private review category and restoring archived originals. **It does not automatically delete newly created roles, pins, or empty categories.** The starter does not archive anything, so its undo operation quarantines created channels for review; it will not remove existing content.

## Install/upgrade

1. Back up Redbot's data and test in a disposable guild first.
2. Extract the zip. Copy the **entire `revamp/` folder** to your normal Redbot cog source, replacing the previous `revamp/` files, including the new `starter-theme.json`.
3. Reload the cog, for example `~reload revamp` if your instance already has it loaded, or follow your normal Redbot cog install and load process.
4. Give fatboy **Manage Channels**, **Manage Roles**, **Send Messages**, **View Channels** and **Manage Messages**. Its role must be high enough to create new roles. Administrators of the server can run the cog commands (subject to Redbot permissions).

The starter JSON file ships with the cog and is editable by the operator if desired; otherwise leave it alone and generate custom themes with North.

## Safety and limits

- Commands require explicit typed confirmation before Discord changes.
- Starter mode never archives existing channels and skips matches by **case-insensitive name and channel type** (not by their category). This is intentional to prevent duplicate channels, but it means an existing `#general` might remain in its original Discord category.
- Preexisting private staff areas are not exposed by the starter; new staff channels explicitly receive privacy overwrites if a same-named existing staff category is reused.
- A custom theme can create new channels and archive eligible old public ones; existing private and Discord special channels are exempt.
- Only standard text/voice channel creation is supported, not forum/stage channel creation.
- Discord's 500-channel and 250-role caps, bot permissions, rate limits and role hierarchy apply.
- **Status:** Python syntax checked and core starter planning/schema smoke-tested. Not yet live-tested with a running fatboy/Discord guild. Test before use on a real community.
