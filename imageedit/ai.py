"""OpenAI Images API image edits for ImageEdit.

Images are sent to OpenAI on explicit user request. No input or result is
stored by the cog. The API key is managed by Red's shared API token storage.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
import json

import aiohttp
from PIL import Image, ImageOps, UnidentifiedImageError

from .processing import MAX_INPUT_BYTES, MAX_INPUT_PIXELS, MAX_OUTPUT_BYTES

API_URL = "https://api.openai.com/v1/images/edits"
MAX_API_RESPONSE = 24 * 1024 * 1024
MAX_OUTPUT_SIDE = 2048
SUPPORTED_MODELS = (
    "gpt-image-2.5-sunburst",
    "gpt-image-2.5-flare",
    "gpt-image-2",
    "gpt-image-1.5",
    "gpt-image-1-mini",
)


class AIEditError(Exception):
    """A safe, non-sensitive message to show in Discord."""


def prepare_input(raw: bytes) -> tuple[bytes, str]:
    """Decode, bound, orient and convert any accepted source to RGB JPEG or RGBA PNG."""
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise AIEditError("Image must be 8 MiB or smaller.")
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP", "GIF"}:
                raise AIEditError("Attach a PNG, JPG, WebP or GIF image.")
            w, h = source.size
            if not (w > 0 and h > 0 and w * h <= MAX_INPUT_PIXELS):
                raise AIEditError("The image must be no larger than 16 megapixels.")
            source.seek(0)  # First frame for animations
            source.load()
            image = ImageOps.exif_transpose(source)
            has_alpha = image.mode in {"RGBA", "LA"} or (
                image.mode == "P" and "transparency" in image.info
            )
            image = image.convert("RGBA" if has_alpha else "RGB")
            image.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            if has_alpha:
                image.save(output, format="PNG", optimize=True)
                filename = "source.png"
            else:
                image.save(output, format="JPEG", quality=90, optimize=True)
                filename = "source.jpg"
            if output.tell() > MAX_INPUT_BYTES:
                raise AIEditError("The processed input is too large to send.")
            return output.getvalue(), filename
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise AIEditError("Unable to decode the attached image.") from exc


def prepare_output(raw: bytes) -> tuple[bytes, str]:
    """Convert a generated image into a Discord-friendly JPEG/PNG/WebP."""
    if not raw or len(raw) > MAX_API_RESPONSE:
        raise AIEditError("The generated image was empty or too large.")
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"}:
                raise AIEditError("The provider returned an unsupported image.")
            w, h = source.size
            if not (w > 0 and h > 0 and w * h <= MAX_INPUT_PIXELS):
                raise AIEditError("The generated image exceeds the pixel limit.")
            source.load()
            image = ImageOps.exif_transpose(source)
            has_alpha = image.mode in {"RGBA", "LA"} or (
                image.mode == "P" and "transparency" in image.info
            )
            image = image.convert("RGBA" if has_alpha else "RGB")
            image.thumbnail((MAX_OUTPUT_SIDE, MAX_OUTPUT_SIDE), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            if has_alpha and image.getchannel("A").getextrema()[0] < 255:
                image.save(output, format="PNG", optimize=True)
                extension = "png"
                if output.tell() > MAX_OUTPUT_BYTES:
                    output.seek(0)
                    output.truncate(0)
                    image.save(output, format="WEBP", quality=84, method=5)
                    extension = "webp"
            else:
                extension = "jpg"
                for quality in (92, 84, 72, 60):
                    output.seek(0)
                    output.truncate(0)
                    image.convert("RGB").save(output, format="JPEG", quality=quality, optimize=True)
                    if output.tell() <= MAX_OUTPUT_BYTES:
                        break
            if output.tell() > MAX_OUTPUT_BYTES:
                raise AIEditError("The generated image is too large for this bot's upload limit.")
            return output.getvalue(), extension
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise AIEditError("Unable to decode the generated image.") from exc


async def request_image_edit(
    api_key: str, model: str, image_bytes: bytes, filename: str, prompt: str
) -> bytes:
    """Call the official, fixed OpenAI image-edits endpoint via multipart upload."""
    if model not in SUPPORTED_MODELS:
        raise AIEditError("Unsupported AI model.")
    if not 1 <= len(prompt.strip()) <= 2000:
        raise AIEditError("Please use an editing prompt of 1–2,000 characters.")
    form = aiohttp.FormData()
    form.add_field("model", model)
    form.add_field("prompt", prompt.strip())
    form.add_field("n", "1")
    form.add_field("output_format", "png")
    form.add_field(
        "image", image_bytes, filename=filename,
        content_type="image/png" if filename.endswith(".png") else "image/jpeg",
    )
    timeout = aiohttp.ClientTimeout(total=240, connect=15, sock_read=230)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                API_URL,
                data=form,
                headers={"Authorization": f"Bearer {api_key}"},
                allow_redirects=False,
            ) as response:
                if response.status == 401:
                    raise AIEditError("OpenAI rejected the API key. Ask the bot owner to check it.")
                if response.status == 403:
                    raise AIEditError("The API key does not have permission to use this model.")
                if response.status == 429:
                    raise AIEditError("OpenAI returned a rate limit or quota error. Check API credits and limits.")
                if response.status == 400:
                    raise AIEditError(
                        "OpenAI rejected the edit. Check the prompt, attachment and selected model."
                    )
                if response.status >= 500:
                    raise AIEditError("OpenAI is temporarily unavailable. Try again later.")
                if response.status != 200:
                    raise AIEditError(f"Image edit failed (HTTP {response.status}).")
                chunks = []
                total = 0
                async for chunk in response.content.iter_chunked(65536):
                    total += len(chunk)
                    if total > MAX_API_RESPONSE:
                        raise AIEditError("The provider response exceeded the size limit.")
                    chunks.append(chunk)
                payload = b"".join(chunks)
    except asyncio.TimeoutError as exc:
        raise AIEditError("The image edit request timed out.") from exc
    except aiohttp.ClientError as exc:
        raise AIEditError("Unable to reach the OpenAI image service.") from exc
    try:
        data = json.loads(payload)
        items = data["data"]
        encoded = items[0]["b64_json"]
        if not isinstance(encoded, str):
            raise ValueError("not base64")
        decoded = base64.b64decode(encoded, validate=True)
        if not decoded:
            raise ValueError("empty image")
        return decoded
    except (ValueError, KeyError, IndexError, TypeError, binascii.Error) as exc:
        raise AIEditError("The image service returned an invalid image response.") from exc
