# -*- coding: utf-8 -*-
"""原始 JSON（api 响应）→ 标准化条目。"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import common


def _has_id(d):
    return isinstance(d, dict) and any(k in d for k in ("aweme_id", "awemeId"))


def _find_aweme_list(node, depth=0):
    if depth > 8 or node is None:
        return []
    if isinstance(node, dict):
        for key in ("aweme_list", "awemeList"):
            if key in node and isinstance(node[key], list):
                return node[key]
        for value in node.values():
            found = _find_aweme_list(value, depth + 1)
            if found:
                return found
        return []
    if isinstance(node, list):
        if node and _has_id(node[0]):
            return node
        for value in node:
            found = _find_aweme_list(value, depth + 1)
            if found:
                return found
    return []


def extract_aweme_list(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return []
    return _find_aweme_list(data)


def _deep_get(obj, keys, default=None):
    cur = obj
    for key in keys:
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int) and 0 <= key < len(cur):
            cur = cur[key]
        else:
            return default
        if cur is None:
            return default
    return cur


def _first_url(node):
    if isinstance(node, dict):
        for key in ("url_list", "urlList", "urls"):
            value = node.get(key)
            if isinstance(value, list) and value:
                return value[0]
        for key in ("cover", "origin_cover", "dynamic_cover", "play_addr", "download_addr"):
            if key in node:
                found = _first_url(node[key])
                if found:
                    return found
    if isinstance(node, list) and node:
        return _first_url(node[0])
    return None


def _all_urls(node):
    urls = []
    if isinstance(node, dict):
        for key in ("url_list", "urlList", "urls"):
            value = node.get(key)
            if isinstance(value, list):
                urls.extend([str(u) for u in value if u])
    elif isinstance(node, list):
        for item in node:
            urls.extend(_all_urls(item))
    return urls


def parse_aweme(raw):
    if not isinstance(raw, dict):
        return None
    aweme_id = str(raw.get("aweme_id") or raw.get("awemeId") or "").strip()
    if not aweme_id:
        return None
    title = str(raw.get("desc") or "").strip()
    author = raw.get("author") or {}
    create_time = raw.get("create_time") or raw.get("createTime")
    published = ""
    if create_time:
        try:
            published = dt.datetime.fromtimestamp(int(create_time)).strftime("%Y-%m-%d %H:%M")
        except Exception:
            published = str(create_time)
    images = raw.get("images") or []
    kind = "images" if images else "video"
    video = raw.get("video") or {}
    cover_url = _first_url(video.get("cover")) or _first_url(video.get("origin_cover"))
    image_urls = []
    if images:
        for img in images:
            urls = _all_urls(img)
            if urls:
                image_urls.extend(urls[:1])
        if not cover_url and image_urls:
            cover_url = image_urls[0]
    duration_ms = _deep_get(raw, ["video", "duration"]) or 0
    try:
        duration_sec = float(duration_ms) / 1000.0
    except (TypeError, ValueError):
        duration_sec = 0.0
    tags = []
    for extra in raw.get("text_extra") or []:
        if isinstance(extra, dict) and extra.get("hashtag_name"):
            tags.append(str(extra["hashtag_name"]))
    share_url = _deep_get(raw, ["share_info", "share_url"]) or _deep_get(raw, ["share_url"]) or ""
    if share_url:
        # 分享链接带一堆跟踪参数（region/mid/u_code/did…），去掉查询串保证笔记稳定
        share_url = str(share_url).split("?")[0]
    url = f"https://www.douyin.com/note/{aweme_id}" if kind == "images" else f"https://www.douyin.com/video/{aweme_id}"
    return {
        "aweme_id": aweme_id,
        "kind": kind,
        "title": title,
        "author_name": str(author.get("nickname") or ""),
        "author_id": str(author.get("uid") or ""),
        "url": url,
        "share_url": str(share_url),
        "cover_url": cover_url or "",
        "images_json": json.dumps(image_urls, ensure_ascii=False),
        "published_at": published,
        "duration_sec": duration_sec,
        "hashtags": tags,
    }


def load_raw(raw_dir, bridge_folder):
    raw_dir = Path(raw_dir)
    manifest = common.read_json(raw_dir / "manifest.json", {}) or {}
    favorites_complete = bool(manifest.get("favorites_complete"))
    folders_meta = manifest.get("folders") or {}
    folders_complete = bool(folders_meta.get("complete"))
    watch_later_meta = manifest.get("watch_later") or {}
    watch_later_complete = bool(watch_later_meta.get("complete")) or bool(manifest.get("watch_later_complete"))
    id2name = {}
    for folder in folders_meta.get("discovered") or []:
        if isinstance(folder, dict) and folder.get("id") is not None:
            id2name[str(folder["id"])] = str(folder.get("name") or folder["id"])

    items = {}

    def add(rec, folder_name=None, from_favorites=False, from_watch_later=False):
        if not rec:
            return
        cur = items.get(rec["aweme_id"])
        if cur is None:
            rec["folders"] = []
            rec["in_favorites"] = False
            rec["in_watch_later"] = False
            items[rec["aweme_id"]] = rec
            cur = rec
        else:
            for key, value in rec.items():
                if value not in (None, "", [], {}) and not cur.get(key):
                    cur[key] = value
        if folder_name and folder_name not in cur["folders"]:
            cur["folders"].append(folder_name)
        if from_favorites:
            cur["in_favorites"] = True
        if from_watch_later:
            cur["in_watch_later"] = True

    for path in sorted(raw_dir.glob("listcollection.*.json")):
        for raw in extract_aweme_list(path):
            add(parse_aweme(raw), None, True)
    for path in sorted(raw_dir.glob("collects-video.*.json")):
        parts = path.name.split(".")
        folder_id = parts[1] if len(parts) >= 4 else "unknown"
        folder_name = id2name.get(folder_id, f"收藏夹{folder_id}")
        for raw in extract_aweme_list(path):
            add(parse_aweme(raw), folder_name, False)
    for path in sorted(raw_dir.glob("watchlater.*.json")):
        for raw in extract_aweme_list(path):
            add(parse_aweme(raw), None, False, True)

    seen_in_bridge = set()
    seen_in_watch_later = set()
    for rec in items.values():
        in_bridge = bridge_folder in rec["folders"]
        in_watch_later = bool(rec.get("in_watch_later"))
        rec["in_bridge"] = in_bridge
        rec["in_watch_later"] = in_watch_later
        if in_bridge:
            seen_in_bridge.add(rec["aweme_id"])
        if in_watch_later:
            seen_in_watch_later.add(rec["aweme_id"])
        parts = []
        if in_watch_later:
            parts.append("稍后再看")
        if rec["in_favorites"]:
            parts.append("收藏")
        parts.extend(rec["folders"])
        rec["source"] = "、".join(parts) if parts else "收藏"
    return {
        "items": list(items.values()),
        "favorites_complete": favorites_complete,
        "folders_complete": folders_complete,
        "watch_later_complete": watch_later_complete,
        "seen_in_bridge": seen_in_bridge,
        "seen_in_watch_later": seen_in_watch_later,
        "manifest": manifest,
    }
