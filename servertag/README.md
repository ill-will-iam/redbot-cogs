# ServerTag v2 — tiered Server Tag + booster rewards

ServerTag manages **custom reward roles**, never Discord's managed Server Booster role or your server's default/basic role. Permission auditing is read-only.

## Install/update on Fatboy
```text
~repo update redbot-cogs
~cog update servertag
~reload servertag
```

If this is your **first** installation, use `~cog install redbot-cogs servertag` followed by `~load servertag` instead. Updating and installing are different Downloader commands.

## Configuration

Run `~tagrole bind` as the FATBOY bot owner in the Discord server chosen for rewards. A fresh install or upgrade needs this once. Binding to another server switches where the cog operates. Existing role assignments in the former server can be removed there manually.

```text
~tagrole bind
~tagrole setbaserole @Wisps
~tagrole setrole @Luminaries
~tagrole setboosttagrole @Radiants
~tagrole setboostonlyrole @Embers
~tagrole status
~tagrole sync
```

AutoRole assigns `@Wisps` on join. ServerTag uses these reward tiers:

| Member's status | Reward role |
| --- | --- |
| This server's tag only, with `@Wisps` | `@Luminaries` |
| Active server boost only | `@Embers` |
| This server's tag and an active server boost | `@Radiants` |
| Neither | None |

When a tagged booster removes or switches away from this server's tag, `@Embers` replaces `@Radiants`. When a tagged booster stops boosting, `@Luminaries` replaces `@Radiants` if the member has `@Wisps`.

If you do not configure `setboosttagrole`, boosters who equip the tag use the regular tag reward. If you do not configure `setbaserole`, all non-boosting members qualify for the normal tag reward.

## Commands

| Command | Purpose |
| --- | --- |
| `~tagrole bind` | Bot owner selects the one server where ServerTag runs |
| `~tagrole roles` | Generate a complete readable server role and permission inventory |
| `~tagrole snapshot` | Persist all role permission bits and explicit role channel-overwrites |
| `~tagrole diff` | Generate a report of changes against the saved snapshot |
| `~tagrole exportsnapshot` | Download the saved JSON snapshot |
| `~tagrole setbaserole @Role` | Require a basic membership role to qualify for the basic tag reward |
| `~tagrole setbaserole` | No basic membership role required |
| `~tagrole setrole @Role` | Regular tag reward (retains v1 config) |
| `~tagrole setboostrole @Role` | Set a reward for every active booster |
| `~tagrole setboostonlyrole @Role` | Set a reward for active boosters who do not display this server's tag |
| `~tagrole setboosttagrole @Role` | Upgraded tag reward for boosters |
| `~tagrole unsetboostrole` | Stop managing the configured booster reward |
| `~tagrole approve @Role I_ACCEPT_PRIVILEGES` | Server owner explicitly approves one role with elevated guild permissions |
| `~tagrole revokeapproval @Role` | Server owner revokes an elevated-role approval |
| `~tagrole unsetboosttagrole` | Stop managing the boosted tag upgrade |
| `~tagrole check @Member` | Correct one member's reward roles |
| `~tagrole sync` | Audit all members and correct reward roles |
| `~tagrole status` | Show configured rewards and snapshot timestamp |
| `~tagrole enable` / `disable` | Resume/pause without stripping current member roles |
| `~tagrole clear` | Clear reward settings; retain permission snapshot |

## Access, safety, and limitations

- `Manage Roles` bot permission and **Server Members Intent** are required.
- Bot's highest role must sit above all custom reward roles.
- Reward roles cannot be Discord-managed. Roles with moderation or administrator privileges are blocked **unless the server owner explicitly approves each role and its exact guild-permissions bitset** using `~tagrole approve @Role I_ACCEPT_PRIVILEGES`. The approval becomes invalid if those permissions change. This is dangerous: any member can potentially equip a server tag, and some may boost to obtain elevated privileges. Prefer removing moderation permissions from reward roles.
- Every reward role must be distinct from the others and from the basic eligibility role.
- A saved permission snapshot covers guild-level role permissions and explicit role-based channel overwrites, *not* member-specific overwrites or individual members' effective permissions.
- Automatic changes use Discord profile updates for tags and member updates for boosts and membership roles. Run `sync` to reconcile existing members or missed events.
- If Discord omits tag or boost data, the cog waits for the data it needs to determine eligibility. A confirmed loss of either requirement can revoke the combined reward.
- Changing or clearing a configured reward role does **not** strip previously assigned roles that are no longer configured. Remove old reward roles deliberately as needed.
- The current configuration and saved permission snapshot are guild-scoped and survive bot restarts.
- Commands require an administrator or member with Manage Server permissions.
- Uses the lower-level member API for full sync; live test it after updating. Large servers may take some time.

### Important
This cog does not create new Discord roles or edit role permissions: configure the desired roles and permissions in Discord first. Run `~tagrole snapshot` before making changes and `~tagrole diff` afterward.
