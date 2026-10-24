# ImageEdit — FATBOY's local image editor

For Red-DiscordBot 3.5+ (discord.py v2). Uses **Pillow**. Local commands need no API key. AI editing additionally supports OpenAI Images API with an owner-configured API key and separate API billing.

## Install

The repository should already be connected to FATBOY.

```text
~load downloader
~repo update redbot-cogs
~cog install redbot-cogs imageedit
~load imageedit
~help image
```

Ensure FATBOY has **Attach Files** and **Read Message History** in the channel (Read Message History is necessary to fetch uncached replies).

## Usage

**Either** add an image attachment to the command message **or** reply to an existing image attachment with a command. For example, reply to a posted picture and enter `~img grayscale`.

| Command | Effect |
| --- | --- |
| `~img resize 512 512` | Fit within 512×512, preserving aspect ratio |
| `~img crop 600 400` | Crop from the center to 600×400 |
| `~img square` | Crop to a centered square |
| `~img rotate 90` | Rotate counterclockwise |
| `~img flip` | Mirror horizontally |
| `~img flop` | Flip vertically |
| `~img grayscale` | Black and white |
| `~img invert` | Invert colors, preserving transparency |
| `~img blur 5` | Blur (radius 0–30, default 3) |
| `~img sharpen 2` | Sharpness (0–5, unchanged = 1) |
| `~img brightness 1.5` | Brightness (0–3, unchanged = 1) |
| `~img contrast 1.4` | Contrast (0–3, unchanged = 1) |
| `~img saturate 2` | Saturation (0–3, unchanged = 1) |
| `~img pixelate 12` | Blocky pixelation (2–64) |
| `~img caption Send more frogs` | White text on a translucent black caption footer |
| `~img sticker` | 320×320 PNG with transparent padding |

`~image` and `~img` are equivalent, and `~img bw` aliases grayscale.

## Limits and behavior

- Accepts PNG, JPEG, WebP, GIF **attachments** (including reply attachments), not arbitrary URLs.
- **First frame only** of animated GIF/WebP images; edits are static.
- Input up to **8 MiB and 16 million pixels**; output longest side at most **2048 px** and file size at most **8 MiB**.
- Sends a new JPEG or PNG; never modifies or deletes the original image.
- Sticker export preserves transparency already in the image but does **not** remove a background or publish a Discord sticker.
- Captions max 200 characters; font falls back to a local installed font.
- At most two image operations execute concurrently. Nothing is retained after the command completes.

## AI image editing (optional)

**Requires a funded OpenAI API account.** A ChatGPT Plus subscription or login is not an API credit balance. Only the AI subcommand transmits an image and prompt to OpenAI; the local effects remain offline.

### Configure the API key safely

As the bot owner, run `~set api` with no arguments to open Red's **secure API credential modal** (on supported Red versions). Use service name **openai** and token name **api_key**, then paste the secret in the modal. Do not paste the key into a public Discord channel, a repository, or this chat.

If your Red version does not support that modal, use the documented `set api` secret mechanism in **a private DM with the bot** only.

### Examples

Reply to a message with an image attachment and send any of these:

- `~img ai Replace the background with a haunted forest`
- `~img ai Give this photo a cinematic gothic purple atmosphere`
- `~img ai Turn the subject into a hand-drawn cartoon, preserving their pose`
- `~img ai Remove the background and make it transparent`

Or attach an image to the same message containing the command.

### AI controls

| Command | Purpose |
| --- | --- |
| `~img ai status` | Show chosen model, access and key presence (not the secret) |
| `~img ai model gpt-image-2.5-flare` | Owner: choose the faster image model |
| `~img ai model gpt-image-2.5-sunburst` | Owner: use precise image editing (default) |
| `~img ai model gpt-image-1-mini` | Owner: choose a smaller legacy option |
| `~img ai access owner` | Owner: restrict this server to bot owners (default) |
| `~img ai access admin` | Owner: allow server administrators / Manage Server |
| `~img ai access everyone` | Owner: permit everyone in this server (incurs paid API usage) |

- **Cost guardrails:** owner-only by default, per-server access controls, 120-second per-user cooldown, at most one AI edit in progress across the bot.
- Model preference is global; AI access is per server. DMs are owner-only.
- Prompts must be 1–2,000 characters; source images max 8 MiB and 16 megapixels.
- Converts supported attachments to PNG or JPEG before sending the image and prompt to OpenAI over HTTPS; the bot resizes and compresses returned images to fit Discord.
- No URL fetches, no automatic AI editing, no persistent prompt/image storage. Normal Discord messages remain on Discord.
- User permissions apply only to AI. Local image commands remain available to everyone.
- Models and API rate limits depend on the OpenAI account and may change.


## Updating

```text
~cog update imageedit
~reload imageedit
```

AI edits require paid OpenAI API access and an API key. The local editing features remain free to run.
