"""Bounded, CPU-local image transforms for the ImageEdit cog."""

from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_INPUT_PIXELS = 16_000_000
MAX_OUTPUT_SIDE = 2048
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}
FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
)


def _check_number(value: float, minimum: float, maximum: float, label: str) -> float:
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum:g} and {maximum:g}.")
    return value


def _load(raw: bytes) -> Image.Image:
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise ValueError("Upload an image no larger than 8 MiB.")
    try:
        with Image.open(io.BytesIO(raw)) as original:
            if original.format not in ALLOWED_FORMATS:
                raise ValueError("Use a PNG, JPEG, WebP or GIF attachment.")
            width, height = original.size
            if width < 1 or height < 1 or width * height > MAX_INPUT_PIXELS:
                raise ValueError("The input image exceeds the 16-megapixel limit.")
            # Animated inputs intentionally use the first frame only.
            original.seek(0)
            original.load()
            image = ImageOps.exif_transpose(original)
            is_transparent = (
                image.mode in {"RGBA", "LA"}
                or (image.mode == "P" and "transparency" in image.info)
            )
            return image.convert("RGBA" if is_transparent else "RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("This image couldn't be decoded.") from exc


def _font(size: int):
    for name in FONT_PATHS:
        if Path(name).is_file():
            return ImageFont.truetype(name, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Older Pillow versions do not accept size.
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textbbox((0, 0), candidate, font=font, stroke_width=0)[2] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            # Break unusually long tokens rather than allowing text off canvas.
            for char in word:
                candidate = current + char
                if draw.textbbox((0, 0), candidate, font=font, stroke_width=0)[2] > max_width and current:
                    lines.append(current)
                    current = char
                else:
                    current = candidate
        if current:
            lines.append(current)
    return lines


def _caption(image: Image.Image, text: str) -> Image.Image:
    text = text.strip()
    if not text or len(text) > 200:
        raise ValueError("Caption must contain 1–200 characters.")
    layer = image.convert("RGBA")
    width, height = layer.size
    if width < 96 or height < 72:
        raise ValueError("Image is too small for a caption (minimum 96×72).")
    margin = max(8, min(width, height) // 30)
    draw = ImageDraw.Draw(layer)
    available = width - 2 * margin
    font, lines = None, []
    for font_size in range(max(16, min(width // 12, 72)), 11, -2):
        test_font = _font(font_size)
        test_lines = _wrap(draw, text, test_font, available)
        if len(test_lines) <= 7:
            font, lines = test_font, test_lines
            break
    if font is None:
        raise ValueError("Caption is too long for this image.")
    heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line or "Ag", font=font, stroke_width=0)
        heights.append(max(12, bbox[3] - bbox[1]))
    spacing = max(3, font.size // 5) if hasattr(font, "size") else 3
    text_height = sum(heights) + spacing * (len(lines) - 1)
    footer = min(height, text_height + 2 * margin)
    if footer < text_height + margin:
        raise ValueError("Image is too short to hold this caption.")
    shade = Image.new("RGBA", (width, footer), (0, 0, 0, 185))
    layer.alpha_composite(shade, (0, height - footer))
    draw = ImageDraw.Draw(layer)
    y = height - footer + (footer - text_height) // 2
    for line, line_height in zip(lines, heights):
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=0)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y - bbox[1]), line, font=font, fill="white")
        y += line_height + spacing
    return layer


def _transform(image: Image.Image, operation: str, values: tuple) -> Image.Image:
    if operation == "resize":
        width, height = values
        if not (16 <= width <= 2048 and 16 <= height <= 2048):
            raise ValueError("Resize width and height must both be 16–2048.")
        return ImageOps.contain(image, (width, height), method=Image.Resampling.LANCZOS)
    if operation == "crop":
        width, height = values
        if not (1 <= width <= image.width and 1 <= height <= image.height):
            raise ValueError(f"Crop must fit the source ({image.width}×{image.height}).")
        left, top = (image.width - width) // 2, (image.height - height) // 2
        return image.crop((left, top, left + width, top + height))
    if operation == "square":
        side = min(image.size)
        return ImageOps.fit(image, (side, side), method=Image.Resampling.LANCZOS)
    if operation == "rotate":
        angle, = values
        _check_number(angle, -360, 360, "Rotation")
        return image.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    if operation == "flip":
        return ImageOps.mirror(image)
    if operation == "flop":
        return ImageOps.flip(image)
    if operation == "grayscale":
        alpha = image.getchannel("A") if image.mode == "RGBA" else None
        result = ImageOps.grayscale(image.convert("RGB")).convert("RGB")
        if alpha:
            result.putalpha(alpha)
        return result
    if operation == "invert":
        if image.mode == "RGBA":
            rgb = ImageOps.invert(image.convert("RGB"))
            rgb.putalpha(image.getchannel("A"))
            return rgb
        return ImageOps.invert(image)
    if operation == "blur":
        radius, = values
        _check_number(radius, 0, 30, "Blur radius")
        return image.filter(ImageFilter.GaussianBlur(radius))
    if operation == "sharpen":
        factor, = values
        _check_number(factor, 0, 5, "Sharpness")
        return ImageEnhance.Sharpness(image).enhance(factor)
    if operation == "brightness":
        factor, = values
        _check_number(factor, 0, 3, "Brightness")
        return ImageEnhance.Brightness(image).enhance(factor)
    if operation == "contrast":
        factor, = values
        _check_number(factor, 0, 3, "Contrast")
        return ImageEnhance.Contrast(image).enhance(factor)
    if operation == "saturate":
        factor, = values
        _check_number(factor, 0, 3, "Saturation")
        return ImageEnhance.Color(image).enhance(factor)
    if operation == "pixelate":
        block, = values
        if not 2 <= block <= 64:
            raise ValueError("Pixel size must be 2–64.")
        tiny = image.resize(
            (max(1, image.width // block), max(1, image.height // block)),
            resample=Image.Resampling.BOX,
        )
        return tiny.resize(image.size, resample=Image.Resampling.NEAREST)
    if operation == "caption":
        return _caption(image, values[0])
    if operation == "sticker":
        contained = ImageOps.contain(image.convert("RGBA"), (320, 320), Image.Resampling.LANCZOS)
        background = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
        background.alpha_composite(
            contained, ((320 - contained.width) // 2, (320 - contained.height) // 2)
        )
        return background
    raise ValueError("Unknown image operation.")


def edit_image(raw: bytes, operation: str, *values) -> tuple[bytes, str]:
    """Apply a single edit. Return file data and filename extension.

    This function deliberately does not fetch URLs, read local paths or keep files.
    """
    image = _load(raw)
    result = _transform(image, operation, values)
    if max(result.size) > MAX_OUTPUT_SIDE:
        result.thumbnail((MAX_OUTPUT_SIDE, MAX_OUTPUT_SIDE), Image.Resampling.LANCZOS)
    transparent = result.mode == "RGBA" and result.getchannel("A").getextrema()[0] < 255
    output = io.BytesIO()
    if transparent or operation == "sticker":
        result.save(output, format="PNG", optimize=True)
        ext = "png"
    else:
        for quality in (90, 80, 70, 60):
            output.seek(0)
            output.truncate(0)
            result.convert("RGB").save(output, format="JPEG", quality=quality, optimize=True)
            if output.tell() <= MAX_OUTPUT_BYTES:
                break
        ext = "jpg"
    if output.tell() > MAX_OUTPUT_BYTES:
        raise ValueError("The edited image exceeds the 8 MiB output limit.")
    return output.getvalue(), ext
