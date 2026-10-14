# Markov (Fatboy fork)

Derived from [Zanidom/ZanCogs](https://github.com/Zanidom/ZanCogs/blob/main/markov/markov.py), itself credited to CrunchBangDev. This fork keeps the existing `Markov` class, config identifier `0x6D61726B6F76`, and chain dictionary keys and representation for use with existing Fatboy data.

## Commands

- `$markov stats` — Your total stored chain size, states, distinct transitions and observations.
- `$markov stats @member` — Show that member's chain statistics.
- `$markov statsall` — Bot-owner-only aggregate for all stored user models (can be slow).
- `$markov show [@member]` — Existing options, now also shows chain size.
- `$markov userenable @member` — Server admin/Manage Server: enable modeling for a member in the **current server**.
- `$markov userdisable @member` — Revoke only the current server's admin enable.
- `$markov userlist` — List members manually enabled in this server.
- `$markov enable` — Opt yourself in; clears your opt-out.
- `$markov disable` — Explicitly opt out. This overrides admin enrollment.
- `$markov reset` — Delete your stored models.
- Existing generate/mode/depth/delete/channelmode/channelstatus/prune commands are retained.

**Size note:** Byte count is the compact UTF-8 JSON serialization of chain models, an estimate of their on-disk payload, not RAM consumption or the entire Red database size. Recorded transition occurrences are summed edge weights, not necessarily message counts.

**Channel note:** The original cog treats an empty configured channel list as **all channels**. To restrict modeling, add desired channels using `$markov channelmode enable #channel` and review `$markov channelstatus`. Admin enables apply only to guild messages (never DMs). Models are per user **globally** and can contain text from more than one shared server.

**Disclosure:** `userenable` announces enrollment in the command channel, and tries to DM the user. A user can opt out or delete their models. The member flag is not a mechanism for clandestine logging; server administrators should disclose the practice in server rules.

## Updating an existing installation

This is intended as a replacement of the ZanCogs `markov` module, **not** a second concurrently loaded Markov cog. Back up the `fatboy` Red instance before changing installed packages. Unload and uninstall the previous `markov` package, then install and load `markov` from this repository. The matching cog class and Config identifier should allow the previously saved models to be reused, provided the existing Red data directory is preserved. Do not use `markov reset`, `mydata` deletion or remove the Red data directory during migration. Verify with `$markov stats` after loading.

The source is derived from prior community implementations. Preserve upstream notices and check the upstream license before redistributing outside your existing deployment.
