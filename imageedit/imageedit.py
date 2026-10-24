"""Attachment/reply based image editing commands for Red-DiscordBot."""

from __future__ import annotations

import asyncio
import io
import time
from typing import Optional

import discord
from redbot.core import Config, commands

from .processing import MAX_INPUT_BYTES, edit_image
from .ai import (
    AIEditError,
    SUPPORTED_MODELS,
    prepare_input,
    prepare_output,
    request_image_edit,
)

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")


class ImageEdit(commands.Cog):
    """Simple offline image edits for attached or replied-to images."""

    __author__ = "Will"
    __version__ = "1.1.0"

    def __init__(self, bot):
        self.bot = bot
        self._worker_slots = asyncio.Semaphore(2)
        self._ai_lock = asyncio.Lock()
        self._ai_last_used = {}
        self.config = Config.get_conf(self, identifier=847309215, force_registration=True)
        self.config.register_global(ai_model="gpt-image-2.5-sunburst")
        self.config.register_guild(ai_access="owner")

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """Remove this user's transient AI cooldown entry, if present."""
        self._ai_last_used.pop(user_id, None)

    @staticmethod
    def _pick_attachment(message: Optional[discord.Message]):
        if not message:
            return None
        for attachment in message.attachments:
            filename = attachment.filename.lower()
            content_type = attachment.content_type or ""
            if filename.endswith(_IMAGE_SUFFIXES) or content_type.startswith("image/"):
                return attachment
        return None

    async def _get_attachment(self, ctx: commands.Context):
        attachment = self._pick_attachment(ctx.message)
        if attachment:
            return attachment
        reference = ctx.message.reference
        if reference and reference.message_id:
            resolved = reference.resolved
            if isinstance(resolved, discord.Message):
                return self._pick_attachment(resolved)
            try:
                message = await ctx.channel.fetch_message(reference.message_id)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                return None
            return self._pick_attachment(message)
        return None

    async def _run_edit(self, ctx: commands.Context, operation: str, *values):
        attachment = await self._get_attachment(ctx)
        if attachment is None:
            await ctx.send(
                "Attach a PNG/JPEG/WebP/GIF to this command, or reply to a message "
                "containing an image attachment. Use [p]help image for commands.".replace(
                    "[p]", ctx.clean_prefix
                ),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        if attachment.size > MAX_INPUT_BYTES:
            await ctx.send("Image must be 8 MiB or smaller.")
            return
        try:
            async with ctx.typing():
                raw = await attachment.read()
                async with self._worker_slots:
                    output, extension = await asyncio.to_thread(
                        edit_image, raw, operation, *values
                    )
                await ctx.send(
                    file=discord.File(io.BytesIO(output), filename=f"fatboy-{operation}.{extension}"),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except ValueError as exc:
            await ctx.send(str(exc), allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            await ctx.send(
                "I couldn't read or upload that image. Check my attachment permissions "
                "and the upload size limit.",
                allowed_mentions=discord.AllowedMentions.none(),
            )

    @commands.group(name="image", aliases=["img"], invoke_without_command=True)
    @commands.bot_has_permissions(attach_files=True)
    async def image_group(self, ctx: commands.Context):
        """Edit an image attached to your command, or reply to an image.

        The original attachment is never changed.
        """
        await ctx.send(
            f"Use {ctx.clean_prefix}help image for filters, resizing, cropping, "
            "captioning and sticker export."
        )

    @image_group.command(name="resize")
    async def resize(self, ctx: commands.Context, width: int, height: int):
        """Fit within WIDTH x HEIGHT, keeping aspect ratio.

        Example: [p]img resize 512 512
        """
        await self._run_edit(ctx, "resize", width, height)

    @image_group.command(name="crop")
    async def crop(self, ctx: commands.Context, width: int, height: int):
        """Center crop to WIDTH x HEIGHT.

        Example: [p]img crop 600 400
        """
        await self._run_edit(ctx, "crop", width, height)

    @image_group.command(name="square")
    async def square(self, ctx: commands.Context):
        """Center crop to a square."""
        await self._run_edit(ctx, "square")

    @image_group.command(name="rotate")
    async def rotate(self, ctx: commands.Context, degrees: float):
        """Rotate counterclockwise -360 to 360 degrees."""
        await self._run_edit(ctx, "rotate", degrees)

    @image_group.command(name="flip")
    async def flip(self, ctx: commands.Context):
        """Mirror horizontally (left to right)."""
        await self._run_edit(ctx, "flip")

    @image_group.command(name="flop")
    async def flop(self, ctx: commands.Context):
        """Flip vertically (top to bottom)."""
        await self._run_edit(ctx, "flop")

    @image_group.command(name="grayscale", aliases=["greyscale", "bw"])
    async def grayscale(self, ctx: commands.Context):
        """Convert to black and white."""
        await self._run_edit(ctx, "grayscale")

    @image_group.command(name="invert")
    async def invert(self, ctx: commands.Context):
        """Invert colours while retaining transparency."""
        await self._run_edit(ctx, "invert")

    @image_group.command(name="blur")
    async def blur(self, ctx: commands.Context, radius: float = 3.0):
        """Blur an image, radius 0–30. Example: [p]img blur 5."""
        await self._run_edit(ctx, "blur", radius)

    @image_group.command(name="sharpen")
    async def sharpen(self, ctx: commands.Context, strength: float = 2.0):
        """Adjust sharpness, 0–5 (1 = unchanged)."""
        await self._run_edit(ctx, "sharpen", strength)

    @image_group.command(name="brightness")
    async def brightness(self, ctx: commands.Context, factor: float = 1.25):
        """Adjust brightness, 0–3 (1 = unchanged)."""
        await self._run_edit(ctx, "brightness", factor)

    @image_group.command(name="contrast")
    async def contrast(self, ctx: commands.Context, factor: float = 1.25):
        """Adjust contrast, 0–3 (1 = unchanged)."""
        await self._run_edit(ctx, "contrast", factor)

    @image_group.command(name="saturate", aliases=["saturation"])
    async def saturate(self, ctx: commands.Context, factor: float = 1.4):
        """Adjust colour saturation, 0–3 (1 = unchanged)."""
        await self._run_edit(ctx, "saturate", factor)

    @image_group.command(name="pixelate")
    async def pixelate(self, ctx: commands.Context, block: int = 12):
        """Pixelate with block size 2–64."""
        await self._run_edit(ctx, "pixelate", block)

    @image_group.command(name="caption")
    async def caption(self, ctx: commands.Context, *, text: str):
        """Add a readable caption at the bottom of the image.

        Example: [p]img caption THIS IS FINE
        """
        await self._run_edit(ctx, "caption", text)

    @image_group.command(name="sticker")
    async def sticker(self, ctx: commands.Context):
        """Export a 320x320 PNG with transparent padding.

        This is sizing, not automatic background removal.
        """
        await self._run_edit(ctx, "sticker")

    async def _ai_allowed(self, ctx: commands.Context) -> bool:
        """AI access is owner-only unless the owner changes a guild's policy."""
        if await self.bot.is_owner(ctx.author):
            return True
        if ctx.guild is None:
            return False
        mode = await self.config.guild(ctx.guild).ai_access()
        if mode == "everyone":
            return True
        if mode == "admin":
            perms = ctx.author.guild_permissions
            return bool(perms.administrator or perms.manage_guild)
        return False

    @image_group.group(name="ai", invoke_without_command=True)
    async def image_ai_group(self, ctx: commands.Context, *, prompt: str = ""):
        """AI-edit the image attached to this command or a replied-to message.

        Example: [p]img ai Replace the background with a haunted forest
        The source image is sent to OpenAI. AI requests may incur charges.
        """
        if not await self._ai_allowed(ctx):
            await ctx.send(
                "AI editing is restricted here. A bot owner can configure access "
                f"with {ctx.clean_prefix}img ai access owner|admin|everyone."
            )
            return
        prompt = prompt.strip()
        if not 1 <= len(prompt) <= 2000:
            await ctx.send(
                f"Usage: {ctx.clean_prefix}img ai <editing instructions> "
                "(1–2,000 characters). Attach an image or reply to one."
            )
            return
        keys = await self.bot.get_shared_api_tokens("openai")
        api_key = keys.get("api_key")
        if not api_key:
            await ctx.send(
                "No OpenAI API key is configured. The bot owner must run "
                f"{ctx.clean_prefix}set api to open the secure key-entry form "
                "(service openai, key name api_key). "
                "Do not post API keys publicly."
            )
            return
        attachment = await self._get_attachment(ctx)
        if attachment is None:
            await ctx.send(
                "Attach an image with this command or reply to an image attachment."
            )
            return
        if attachment.size > MAX_INPUT_BYTES:
            await ctx.send("The input image must be 8 MiB or smaller.")
            return

        now = time.monotonic()
        previous = self._ai_last_used.get(ctx.author.id, 0.0)
        if now - previous < 120:
            await ctx.send(
                f"AI editing has a two-minute per-user cooldown. "
                f"Try again in {int(121 - (now - previous))} seconds."
            )
            return
        if self._ai_lock.locked():
            await ctx.send("FATBOY is already processing another AI image edit.")
            return

        try:
            async with self._ai_lock:
                self._ai_last_used[ctx.author.id] = time.monotonic()
                async with ctx.typing():
                    raw = await attachment.read()
                    async with self._worker_slots:
                        prepared, filename = await asyncio.to_thread(prepare_input, raw)
                    model = await self.config.ai_model()
                    edited = await request_image_edit(
                        api_key, model, prepared, filename, prompt
                    )
                    async with self._worker_slots:
                        output, ext = await asyncio.to_thread(prepare_output, edited)
                    await ctx.send(
                        file=discord.File(
                            io.BytesIO(output), filename=f"fatboy-ai-edit.{ext}"
                        ),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
        except AIEditError as exc:
            await ctx.send(str(exc), allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            await ctx.send(
                "Unable to read the attachment or upload the AI result. "
                "Check FATBOY's file permissions and upload limits."
            )

    @image_ai_group.command(name="status")
    async def ai_status(self, ctx: commands.Context):
        """Show current model, availability and this server's AI access policy."""
        configured = bool((await self.bot.get_shared_api_tokens("openai")).get("api_key"))
        model = await self.config.ai_model()
        access = (
            await self.config.guild(ctx.guild).ai_access()
            if ctx.guild else "owner"
        )
        await ctx.send(
            f"ImageEdit AI: model {model}, key {'configured' if configured else 'missing'}, "
            f"access {access}, user cooldown 120s, max 1 concurrent edit."
        )

    @image_ai_group.command(name="model")
    @commands.is_owner()
    async def ai_model(self, ctx: commands.Context, model: str):
        """Set image model (owner only).

        Models: gpt-image-2.5-sunburst, gpt-image-2.5-flare, gpt-image-2,
        gpt-image-1.5, gpt-image-1-mini.
        """
        if model not in SUPPORTED_MODELS:
            await ctx.send("Choose one: " + ", ".join(SUPPORTED_MODELS))
            return
        await self.config.ai_model.set(model)
        await ctx.send(f"AI image model set to {model}.")

    @image_ai_group.command(name="access")
    @commands.is_owner()
    @commands.guild_only()
    async def ai_access(self, ctx: commands.Context, access: str):
        """Set AI access for THIS server (owner only): owner, admin, everyone."""
        mode = access.lower().strip()
        if mode not in ("owner", "admin", "everyone"):
            await ctx.send("Use owner, admin, or everyone.")
            return
        await self.config.guild(ctx.guild).ai_access.set(mode)
        await ctx.send(
            f"AI image editing access in this server is now {mode}. "
            "Paid API requests use the bot owner's OpenAI key."
        )
