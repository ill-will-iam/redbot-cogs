# Sexiness

A playful, random percentage rating for your Red Discord Bot server. Entertainment only—not a real assessment of someone's appearance.

## Commands

- `$sexy` — roll your own fresh 0–100% rating.
- `$sexy @member` — roll a fresh rating for another server member.
- `$sexiness` — alias for `$sexy` (also accepts a mentioned member).

Each command produces a new independent roll, a ten-segment progress bar, and a random quip matched to the score. A perfect 100% has special messages. Scores are **not** saved or based on member traits or Discord profile information.

## Install on Fatboy

```text
$repo update redbot-cogs
$cog install redbot-cogs sexiness
$load sexiness
$sexy
```

No API keys or external dependencies required. This command is available to regular members in a server; it does not support DMs. Member mentions are not pinged in the response. No personal data is stored.
