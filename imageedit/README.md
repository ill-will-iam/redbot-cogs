# ImageEdit — FATBOY's local image editor

For Red-DiscordBot 3.5+ (discord.py v2). Uses **Pillow**. No API key, image-generation service, database, or persistent storage.

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

## Updating

```text
~cog update imageedit
~reload imageedit
```

For AI-powered subject removal, image generation and natural-language editing, a separate provider integration would be required.
