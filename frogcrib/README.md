# Frog Cribbage — the Royal Ribbit Reserve card table

Traditional **two-player cribbage to 121 points**, integrated with the `ribbit` economy (The Royal Ribbit Reserve, currency **Ribbucks**). No separate money store, no betting, and no entry fee. Matches may be played without `ribbit`, but no rewards are issued unless Ribbit's server-local bank is enabled.

## Install and load

From Discord, as the bot owner:

```text
$repo update redbot-cogs
$cog install redbot-cogs frogcrib
$load frogcrib
```

To enable Ribbuck rewards, have `ribbit` installed and loaded, with `$ribbit setup` completed. **Do not switch your existing bank from local to global** or load Red's built-in Economy cog to set this up. Card hands are privately DMed; both players must allow bot DMs. The game channel uses prefix commands (`$` shown in examples).

## Commands

| Command | Use |
| --- | --- |
| `$crib challenge @member` | Invite a second player; one game per channel, one per player per guild |
| `$crib accept` / `$crib decline` | Answer invite within 5 minutes |
| `$crib hand` | Receive a private, numbered copy of your hand |
| `$crib discard 1 4` | Secretly select 2 of 6 numbered cards for dealer's crib |
| `$crib play 2` | Play numbered card on your turn (never above 31) |
| `$crib go` | Declare go **only** when no card fits under 31 |
| `$crib board` | Scores, dealer, running count, and next turn |
| `$crib rules` | Cribbage scoring summary |
| `$crib quit` | Abandon game; neither player earns a result or Ribbucks |
| `$crib stats [@member]` | Win/loss record and awarded Ribbucks |
| `$crib top` | Server win leaderboard |

`$cribbage` is also a top-level alias for `$crib`. The game shares Ribbit balances without modifying Ribbit's commands or bank configuration.

### Admin settings

- `$crib config` — view current settings
- `$crib config rewards 100 25` — winner and other player's match-completion rewards; set both to `0` to disable (maximum 1,000 each; other must be <= winner)
- `$crib config cap 3` — maximum paid, completed games per player **per UTC day**; 0 disables paid games
- `$crib config timeout 20` — inactivity timeout in minutes (5–120). Invitations always expire after 5 minutes

**Default:** winner **100 Ribbucks**, other player **25 Ribbucks**, maximum **3 paid games per user per UTC day**. Rewards are granted only for finished 121-point games through `Ribbit.award_for_game()`, which enforces bank limits, local-bank requirement and guild enablement, and writes an audit entry. No payout for quit, declined invitations, aborted games or inactivity. Stored vault balances are untouched. Reaching the bank maximum prevents that player's reward, without affecting their game result.

## Game mechanics

- Every deal alternates dealer and deals six unique cards to each player. Both discard two face-down to the dealer's crib. Cut a starter. Starter Jack awards dealer two **heels** points and can end the game.
- Non-dealer pegs first. Cards may not exceed running total 31; 15 = 2 points, 31 = 2, equal-rank pairs/triples/quads = 2/6/12, valid longest consecutive runs earn their length, and go/last card earns one (not in addition to 31). A 31 or exhausted count resets the sequence, and runs/pairs do not cross that boundary.
- After all cards are played: non-dealer counts first, then dealer, then dealer's crib. Fifteens, pairs, longest runs (including double/triple runs), hand/crib flushes and jack matching starter's suit (**nobs**) are counted automatically. Crib flush only counts with five same-suit cards. First to 121 wins immediately; later scores are not counted.
- Hands are DMed privately, public messages show only played cards, starter, running total, and score. Card numbers are refreshed as cards are played. You use actions in the original server channel, not by DM. The bot will need permission to send messages and DMs.

## Known limitations

- Two-player games only, not partnership/team cribbage, manual muggins, or tournaments; scores are automatic.
- Table state is in RAM. Cog reload, bot restart, or timeout cancels unfinished games without payouts. Stats and daily payout counts are persisted via Red Config.
- A power loss during the final split bank/config write is not perfectly atomic; use `$ribbit audit` if you need to reconcile a payout. Individual games are not wagerable.
- The bundled automated tests cover scoring and simulated matches. Live Discord/Redbot integration still requires testing on the server.

Rules background: [American Cribbage Congress](https://www.cribbage.org/NewSite/rules/default.asp).
