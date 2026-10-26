# Haven — lockdown and owner-only server reset

## Destructive reset

Assuming your configured prefix is `~`:

```text
~haven nuke preview
~haven nuke
~haven status
```

`nuke preview` performs read-only API checks. `nuke` displays the plan and requires
`DELETE <guild-id> <random-token>` from the same owner in the same channel within
60 seconds. The caller must be BOTH the current Discord server owner and a Red
bot owner. Delegated administrators cannot use it. Ownership and the plan are
checked again after confirmation. The bot requires its own Administrator role
and the Members intent. A bot owner who does not own the server cannot run it.

The confirmed reset pauses invites using Discord's guild API, clears @everyone
permissions, removes assignable roles from every member except the server owner
and FATBOY, verifies isolation, creates `haven-owner` visible to those two
accounts, and deletes all reviewed old channels/categories. Threads and messages
inside deleted channels are permanently lost. Role definitions remain, and
members are not kicked. The owner and FATBOY retain their roles. Harmless managed
integration/boost roles remain because Discord does not permit removing them.
Privileged managed roles, unmanageable role hierarchy, an active seal snapshot,
or Community mode block the operation before it starts. Resolve those conditions
manually before requesting a fresh preview; Haven does not bypass them.

Discord must accept and confirm the invite pause before any roles or channels
are changed. If the API does not support it for this guild, the reset stops.
Invite pause is a guild setting, not an irreversible ban on joining: the owner
can later reopen invites. This is a one-time operation, not a continuous guard
against other bots/integrations modifying the guild. Disable competing role or
channel automation first. Concurrent changes can produce an incomplete result;
only the final live checks allow the command to report completion.

## Reset audit and partial failures

Haven writes `reset-<guild-id>-<run-id>.jsonl` inside its Red cog data directory.
It records the reviewed member role assignments, role permissions, channel
IDs/names/types, invoking owner, timestamps, each request's intent, successful
responses, and completion/failure. The file is flushed before mutations. These
local logs remain even if the command channel is deleted. Discord audit reasons
include the same run ID and owner ID. Logs contain member IDs and remain until
the operator removes them; restrict filesystem access accordingly.

On any failed step, subsequent actions stop. Already-applied changes remain.
The new private channel receives the stop notice if available, otherwise Haven
attempts an owner DM. If neither delivery works, inspect `haven status` or the
local audit. Cancellation marks the run incomplete when the process can still
write; a crash may leave its recorded status as `running`. Nothing resumes on
startup. An intent without a success entry needs manual verification in Discord.

**There is no channel/message rollback.** The audit is not a content backup.
`haven restore` only restores a prior reversible seal, never a reset. For partial
reset recovery, inspect the log, manually restore appropriate role assignments
and @everyone permissions, and re-enable invites only when ready. A fresh `nuke`
can be previewed and confirmed to finish a partial reset; it gets a separate log
and may delete a private channel left by the earlier run. It never resumes by
itself. Keep any content you need before confirming.

## Reversible read-only mode

Haven temporarily blocks posting and reacting, including threads and speaking/
streaming in voice channels, for non-administrators. It preserves who can see
each channel, including private channels, and snapshots original permission
overwrites for a reversible restoration.

The `seal` command never deletes channels, messages, roles, or members. It **does not remove
Administrator roles**. Discord Administrators bypass channel overwrites and
can still post or change permissions.

## Installation

```text
$repo update redbot-cogs
$cog install redbot-cogs haven
$reload haven
```

## Access

The actual Discord guild owner can always operate Haven. For another
Administrator to run Haven, the guild owner must first authorize the account:

```text
$haven authorize @TrustedAdmin
$haven revoke @TrustedAdmin
```

Authorization applies only while that human member has Administrator.

## Commands

```text
$haven inspect
$haven status
$haven seal
$haven restore
```

`seal` and `restore` require a follow-up confirmation with the guild ID.
Haven saves a full permission overwrite snapshot before applying changes.
If Discord rejects any permission changes, the snapshot is kept for recovery.

Bot Administrator permission is required for consistent read-only and recovery
behavior. Roles and users with Discord Administrator bypass channel overwrites.
Synced channels are modified through categories to preserve sync relationships.
Existing voice connections may remain active, and new channels created after
a seal are not automatically included. Changes during lockdown can be undone
by restoration because it reapplies the saved permission overwrites.
