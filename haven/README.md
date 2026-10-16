# Haven — reversible read-only server mode

Haven temporarily blocks posting and reacting, including threads and speaking/
streaming in voice channels, for non-administrators. It preserves who can see
each channel, including private channels, and snapshots original permission
overwrites for a reversible restoration.

It never deletes channels, messages, roles, or members. It **does not remove
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
