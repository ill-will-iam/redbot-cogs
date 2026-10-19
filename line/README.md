# Line

A simple timed group command for Red-DiscordBot (Fatboy). In a server text channel, the first `$line` starts a **45-second** joining window. Each additional member who types `$line` receives a personalized response. Then joining closes, the bot sends a **3, 2, 1** countdown with one second between messages, and finishes with **🥂 Cheers, enjoy! 🥂**.

Example:

```text
@LordHelderon is lining up! Join them with `$line` and get lifted.
@ʝᥱᥒᥙɩᥒᥱ is lining up a fatty!
3...
2...
1...
🥂 Cheers, enjoy! 🥂
```

Names are shown in bold in Discord. These display-name references are not actual pings.

## Install

```text
$repo update redbot-cogs
$cog install redbot-cogs line
$load line
$line
```

Each channel gets its own independent round. A user may join a round only once. After the 45 seconds, late joiners are informed that the countdown has started; the next `$line` after the cheers starts a fresh round. No admin permissions, API keys, dependencies or configuration required. The bot needs permission to view and send messages in the channel. Unloading or restarting the cog cancels active rounds.

## Data handling

Only participants' Discord user IDs are held in RAM during an active round. There is no persistent storage. IDs are discarded when rounds end, and Red data-deletion requests remove matching IDs from active rounds. The bot's public line-up and countdown messages remain in Discord until deleted under ordinary server policies.
