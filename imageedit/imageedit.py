"""Attachment/reply based image editing commands for Red-DiscordBot."""

from __future__ import annotations

import asyncio
import io
from typing import Optional

import discord
from redbot.core import commands

from .processing import MAX_INPUT_BYTES, edit_image

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")


class ImageEdit(commands.Cog):
    """Simple offline image edits for attached or replied-to images."""

    __author__ = "Will"
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self._worker_slots = asyncio.Semaphore(2)

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """This cog does not persist any personal data."""
        return

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
