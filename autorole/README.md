# AutoRole

Assign designated roles to **new human members** as they join a Discord guild. This cog works per server, saves its settings across bot restarts, and does not post welcome or join messages.

## Commands

- `~autorole add @Member` — start automatically assigning a role.
- `~autorole remove @Member` — stop assigning a role.
- `~autorole list` (or `~autorole`) — list configured roles and status.
- `~autorole on` / `~autorole off` — enable/disable without deleting settings.
- `~autorole clear` — clear all configured roles.

Up to 10 roles may be configured per guild. Roles are assigned only to future joiners, not existing members. Bots are excluded. When Membership Screening is enabled, roles are applied after a member accepts the rules. Role grants are silent, and failures appear only in the Redbot log.

## Installation

```text
~repo update redbot-cogs
~cog install redbot-cogs autorole
~load autorole
~autorole add @Member
~autorole list
```

Enable **Server Members Intent** in the Discord Developer Portal and in your running bot's gateway-intent configuration. Restart Red if you just enabled the intent. The bot needs **Manage Roles** and its top Discord role must be **higher** than each role being assigned. For safety, the cog rejects roles containing administrator or other high-impact staff permissions.

Only server admins / people with **Manage Roles** may change settings. This cog does not store any personal data.
