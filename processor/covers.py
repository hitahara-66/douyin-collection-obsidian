# -*- coding: utf-8 -*-
"""封面下载与压缩（webp，≤ max_bytes）。"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, ImageDraw

import requests

from . import common

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://www.douyin.com/",
}


def _placeholder(aweme_id, width, height=270):
    digest = hashlib.md5(str(aweme_id).encode("utf-8")).hexdigest()
    color = tuple(int(digest[i : i + 2], 16) for i in (0, 2, 4))
    color = tuple(min(200, max(30, c)) for c in color)
    img = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, height - 40), (width, height)], fill=tuple(max(0, c - 25) for c in color))
    return img


def ensure_cover(item, cfg, offline=False, refresh=False):
    """返回 (ok, path, error)。path 为绝对路径。"""
    aweme_id = item["aweme_id"]
    out_dir = Path(cfg["vault_dir"]) / "attachments" / "covers"
    out = out_dir / f"{common.id8(aweme_id)}.webp"
    if out.exists() and out.stat().st_size > 0 and not refresh:
        return True, out, None
    target_w = int(cfg["covers"]["width"])
    max_bytes = int(cfg["covers"]["max_bytes"])
    try:
        if offline or not item.get("cover_url"):
            img = _placeholder(aweme_id, target_w)
        else:
            resp = requests.get(item["cover_url"], headers=HEADERS, timeout=20)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        if img.width > target_w:
            img = img.resize((target_w, max(1, int(img.height * target_w / img.width))), Image.LANCZOS)
        quality = 80
        buf = io.BytesIO()
        while True:
            buf = io.BytesIO()
            img.save(buf, format="WEBP", quality=quality, method=4)
            if buf.tell() <= max_bytes or quality <= 35:
                break
            quality -= 10
        out_dir.mkdir(parents=True, exist_ok=True)
        out.write_bytes(buf.getvalue())
        return True, out, None
    except Exception as exc:  # noqa: BLE001 - 需要兜住所有网络/图片异常
        return False, None, str(exc)
