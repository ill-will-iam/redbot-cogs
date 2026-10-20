# Truth or Dare — Rated R (18+)

A chat-friendly, adult-oriented Red-DiscordBot 3.5+ game for Fatboy. Designed for server social nights and 18+ communities.

**This is R-rated, not an explicit-content generator.** Prompts are spicy, flirty, funny, embarrassing, and frequently inappropriate, but never require nudity, explicit photos, unwanted contact, harassment, unsafe acts, or real-life proof. Any player can decline any prompt, without explanation.

## Install / update

In Discord, with the bot's current prefix (~):

    ~load downloader
    ~repo update redbot-cogs
    ~cog install redbot-cogs truthordare
    ~load truthordare
    ~help tod

For future changes, use ~cog update truthordare and reload if prompted.

## Commands

| Command | What it does |
|---|---|
| ~tod | Random truth or dare for yourself |
| ~truth | Random truth |
| ~dare | Random dare |
| ~tod truth / ~tod dare | Same commands under the main group |
| ~tod @member | Random challenge for a participant who joined this channel's game |
| ~truth @member / ~dare @member | Specific prompt for an opted-in participant |
| ~tod join | Add yourself to the channel's optional random-player pool |
| ~tod leave | Remove yourself from the pool |
| ~tod players | See who has joined |
| ~tod next | Select a random joined player and a random challenge |
| ~tod next truth / ~tod next dare | Pick a joined player and that category |
| ~tod rules | Explain consent and game boundaries |
| ~todset | View server setting (admin) |
| ~todset on / ~todset off | Enable/disable gameplay on this server (admin) |

## Configuration and rules

1. Mark the game text channel **Age-Restricted (NSFW)** in Discord's channel settings. The cog checks this for every challenge (including threads when the parent is age-restricted).
2. The server's setting defaults to on, but prompts are **always restricted to an age-restricted channel**. Admins can disable the game with ~todset off and turn it back on with ~todset on.
3. Any member can request a truth or dare for **themselves**. Members who want to be randomly selected or tagged by others voluntarily use ~tod join.
4. Targeting a different member who hasn't opted in is blocked; players can leave any time using ~tod leave.
5. Allow anyone to pass, and honor Discord's rules and your own community guidelines. **NSFW channel marking alone does not verify a person's age.** Server moderators are responsible for adult-only access controls.

## Implementation notes

- 120 truths and 113 dares, 233 prompts total.
- Avoids the most recently used 25 prompts **per category per channel**.
- Five-second per-user prompt throttle.
- Up to 100 opted-in players per channel; tries not to select the same person twice in a row when multiple volunteers are present.
- No APIs, external dependencies, scheduled posts, message scanning, or privileged intents are needed.
- Player IDs, prompt history, and last selected player are stored in **memory only** and disappear on cog reload/restart. The only persistent value is each guild's enable/disable setting.
- Red's end-user-data deletion hook removes a player's ID from all in-memory pools.
- The game does not store answers, messages, or challenge outcomes.

If a command name clashes with another installed cog, unload/rename the conflicting cog or invoke the namespaced ~tod truth / ~tod dare commands.
