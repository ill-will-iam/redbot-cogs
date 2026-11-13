# ServerTag v2 — tiered Server Tag + booster rewards

ServerTag manages **custom reward roles**, never Discord's managed Server Booster role or your server's default/basic role. Permission auditing is read-only.

## Install/update on Fatboy
```text
~repo update redbot-cogs
~cog update servertag
~reload servertag
```

If this is your **first** installation, use `~cog install redbot-cogs servertag` followed by `~load servertag` instead. Updating and installing are different Downloader commands.

## Recommended configuration
```text
~tagrole roles
~tagrole snapshot
~tagrole setbaserole @Wisps
~tagrole setrole @Luminaries
~tagrole setboosttagrole @Radiants
~tagrole unsetboostrole
~tagrole status
~tagrole sync
```

**With this configuration:** `@Wisps` is the baseline join role, `@Luminaries` is rewarded when a non-booster equips this server's tag, and `@Radiants` is rewarded **only when both the tag and an active server boost are present**. A booster without the tag receives **neither** reward role. On a tag/boost transition, `@Radiants` replaces `@Luminaries` or vice versa. The built-in Discord Server Booster role stays unchanged. `~tagrole unsetboostrole` disables independent booster-only rewards.

If you do not configure `setboosttagrole`, boosters who equip the tag use the regular tag reward. If you do not configure `setbaserole`, all non-boosting members qualify for the normal tag reward.

## Commands

| Command | Purpose |
| --- | --- |
| `~tagrole roles` | Generate a complete readable server role and permission inventory |
| `~tagrole snapshot` | Persist all role permission bits and explicit role channel-overwrites |
| `~tagrole diff` | Generate a report of changes against the saved snapshot |
| `~tagrole exportsnapshot` | Download the saved JSON snapshot |
| `~tagrole setbaserole @Role` | Require a basic membership role to qualify for the basic tag reward |
| `~tagrole setbaserole` | No basic membership role required |
| `~tagrole setrole @Role` | Regular tag reward (retains v1 config) |
| `~tagrole setboostrole @Role` | Booster reward, tag not required |
| `~tagrole setboosttagrole @Role` | Upgraded tag reward for boosters |
| `~tagrole unsetboostrole` | Stop managing a booster-only reward (important for tag+boost-only setup) |
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
- Automatic events use `GUILD_MEMBER_UPDATE` for server identity and boost state. Manual `sync` reconciles missed gateway events and existing members.
- If the bot receives no server identity data, tag rewards are left unchanged rather than guessed. If it receives no boost data, booster rewards are likewise left unchanged.
- Changing or clearing a configured reward role does **not** strip previously assigned roles that are no longer configured. Remove old reward roles deliberately as needed.
- The current configuration and saved permission snapshot are guild-scoped and survive bot restarts.
- Commands require an administrator or member with Manage Server permissions.
- Uses the lower-level member API for full sync; live test it after updating. Large servers may take some time.

### Important
This cog does not create new Discord roles or edit role permissions: configure the desired roles and permissions in Discord first. Run `~tagrole snapshot` before making changes and `~tagrole diff` afterward.
