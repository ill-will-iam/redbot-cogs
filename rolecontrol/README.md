# FATBOY RoleControl

Owner-only Red-DiscordBot cog to give yourself a Discord server role, remove one of your roles, and list your current roles.

## Install using Red Downloader

After adding the [redbot-cogs repository](https://github.com/ill-will-iam/redbot-cogs) to your bot, run:

```text
~repo update redbot-cogs
~cog install redbot-cogs rolecontrol
~load rolecontrol
```

These examples use the current documented FATBOY prefix `~`. If you changed FATBOY's prefix, replace `~` accordingly.

## Commands

| Command | Description |
| --- | --- |
| `~roleme <role>` | Assign the given role to yourself. |
| `~giverole <role>` | Alias for `roleme`. |
| `~unroleme <role>` | Remove a role from yourself. |
| `~removemyrole <role>` | Alias for `unroleme`. |
| `~myroles` | List all your current roles with role IDs. |

Use a role name, role ID or role mention. Role names containing spaces work as a single argument, e.g. `~roleme Cool People`.

## Discord permissions and security

- Only Red's recognized bot owner(s) can invoke the commands; other users cannot add/remove roles with them.
- FATBOY requires the **Manage Roles** permission to make changes.
- FATBOY's highest role must be **above** the role being managed in Discord's server role hierarchy.
- Discord integration-managed roles and `@everyone` cannot be assigned/removed by the cog.
- The commands work only inside servers, not DMs.
- The cog doesn't create roles, change another member's roles, or bypass Discord permissions.
- No user data is stored by this cog. Discord may record role changes in its own audit log.

## Troubleshooting

If you see a role hierarchy error, open **Server Settings → Roles** and drag FATBOY's role above the role you want to manage. If Discord denies the change, check FATBOY's **Manage Roles** permission.

To test after installation, run `~myroles`, then try `~roleme <a role below FATBOY's highest role>`.
