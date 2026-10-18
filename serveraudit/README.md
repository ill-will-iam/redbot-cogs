# ServerAudit

Read-only, on-demand review of a Discord server for Red Discord Bot 3.5+.

## Commands

- `$audit` — full scan; privately DM Markdown report.
- `$audit settings` — verification, 2FA, media filtering, AutoMod and invites.
- `$audit roles` — sensitive role privileges and @everyone permissions.
- `$audit bots` — detected bots, their roles and effective guild permissions.
- `$audit channels` — @everyone channel permissions and category synchronization.
- `$audit export` — full report as Markdown and JSON.

## Install

```text
$repo update redbot-cogs
$cog install redbot-cogs serveraudit
$load serveraudit
$audit
```

Requires server owner or Manage Server. The command has a 60-second per-guild cooldown. Reports are sent only by DM, not published in server channels.

Enable the privileged **Server Members Intent** in the Discord Developer Portal and Red, then restart, for more complete bot/member inventories. The cog attempts a bounded member chunk for guilds with at most 2,500 members; larger guilds rely on cache, marked as partial when necessary.

Bot account **Manage Server** permission is needed to inspect built-in AutoMod rules and invitations. The report identifies missing coverage if access fails. Administrator permission is not required.

**Limitations:** This does not inspect another bot's internal config or third-party dashboard, verify member ages, provide a complete per-member effective permission matrix, or review historical activity. Administrator roles, unsynced category overrides and unrestricted invites are findings to review, not automatic proof of vulnerabilities. Discord DMs persist until deleted by users. No credentials, API keys, local files or external services are required.

**Safety:** No settings or roles are changed; report snapshots are transient and contain guild configuration details. Enable DMs to receive the results.
