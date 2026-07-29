from __future__ import annotations

import io
import random
import string
import time
import uuid
from base64 import b64encode

from PIL import Image, ImageDraw, ImageFont

from app.core.config import get_settings

settings = get_settings()

# In-memory store: captcha_id -> (answer, expires_at)
_store: dict[str, tuple[str, float]] = {}


def _random_text(length: int = 4) -> str:
    chars = string.ascii_uppercase + string.digits
    # remove easily confused characters
    chars = chars.translate(str.maketrans("", "", "0O1I"))
    return "".join(random.choices(chars, k=length))


def _draw_captcha(text: str) -> bytes:
    width, height = 140, 50
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # draw text with varied positions
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()

    for i, ch in enumerate(text):
        x = 15 + i * 28 + random.randint(-4, 4)
        y = 5 + random.randint(-4, 8)
        color = (random.randint(0, 120), random.randint(0, 120), random.randint(0, 120))
        draw.text((x, y), ch, fill=color, font=font)

    # noise dots
    for _ in range(80):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)))

    # interference lines
    for _ in range(3):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line(
            (x1, y1, x2, y2),
            fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)),
            width=1,
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _cleanup_expired() -> None:
    now = time.time()
    expired = [cid for cid, (_, exp) in _store.items() if now > exp]
    for cid in expired:
        del _store[cid]


def generate_captcha() -> tuple[str, str]:
    """Return (captcha_id, image_base64)."""
    _cleanup_expired()
    captcha_id = str(uuid.uuid4())
    text = _random_text(4)
    image_bytes = _draw_captcha(text)
    image_base64 = b64encode(image_bytes).decode("ascii")
    _store[captcha_id] = (text.lower(), time.time() + settings.captcha_ttl_seconds)
    return captcha_id, image_base64


def verify_captcha(captcha_id: str, user_text: str) -> bool:
    """Verify and consume the captcha. Returns True if valid."""
    _cleanup_expired()
    entry = _store.pop(captcha_id, None)
    if entry is None:
        return False
    answer, expires = entry
    if time.time() > expires:
        return False
    return answer == user_text.strip().lower()
