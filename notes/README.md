# Notes — Discord server management to-do lists

A persistent Red-DiscordBot V3 cog for **private staff task boards and reference memos**.

## Install

```text
$repo update redbot-cogs
$cog install redbot-cogs notes
$load notes
$help notes
```

The repo must first contain the `notes/` folder. If not, add the repo with `$repo add redbot-cogs https://github.com/ill-will-iam/redbot-cogs` and install after it has been published.

## Commands

| Command | What it does |
| --- | --- |
| `$notes` or `$notes list` | Show the default `general` checklist. |
| `$notes add Fix moderator permissions` | Create a task in `general`. |
| `$notes addto moderation Audit bot roles` | Create a task in another list. |
| `$notes show moderation` | View another list. |
| `$notes all [page]` | Review tasks across all lists. |
| `$notes task 3` | View the full task and status. |
| `$notes done 3` | Mark task #3 done. |
| `$notes undo 3` | Reopen it. |
| `$notes edit 3 Rewrite the rules` | Change the task text. |
| `$notes remove 3` | Permanently remove it. |
| `$notes priority 3 urgent` | Set `urgent`, `high`, `normal` or `low`. |
| `$notes due 3 2026-10-25` | Set a date (UTC); `clear` removes it. |
| `$notes assign 3 @Moderator` | Assign someone (no notification ping). |
| `$notes unassign 3` | Remove the assignment. |
| `$notes move 3 staffing` | Move a task to another list. |
| `$notes boards` | List your management boards. |
| `$notes board create staffing` | Create a task board. |
| `$notes board rename staffing staff` | Rename a board. |
| `$notes board delete staff` | Delete an empty board. |
| `$notes memo add Review ban appeals weekly` | Save a separate reference note. |
| `$notes memo list [page]` | Browse memos. |
| `$notes memo show 1` | Read full memo. |
| `$notes memo delete 1` | Delete a memo. |

All tasks have server-wide permanent numeric IDs, even after moving boards or deleting other tasks. The `general` board cannot be deleted or renamed. Board names must start with a letter and be up to 24 letters, digits, underscores or hyphens. Displays show 8 items per page.

## Security and storage

- **All commands** are usable only by Redbot admins or members with Discord's **Manage Server** (`manage_guild`) permission. Use a private staff channel for additional confidentiality. Bot owners may have broader access under Redbot's global command permissions.
- Each Discord server has **separate data**, persisted through Redbot's `Config` storage (not a JSON file in the repo).
- Limits per server: 300 tasks total, 20 boards, 100 memos; tasks up to 400 characters and memos up to 1,000 characters.
- Notes are **not encrypted**; never put passwords, recovery codes, tokens or other secrets in them.
- UTC due dates are for tracking and display only. **The cog does not send automatic reminders.**
- `remove` and `memo delete` are permanent; board deletion only works when the board is empty.
- A Red user-data deletion request disassociates IDs in creator/completer/assignment/memo metadata but keeps server operational content.
