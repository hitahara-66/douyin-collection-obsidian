# -*- coding: utf-8 -*-
"""公共工具：配置、路径、文件名清洗、frontmatter 读写。"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def expand_env(value):
    if not isinstance(value, str):
        return value
    return re.sub(r"%([^%]+)%", lambda m: os.environ.get(m.group(1), m.group(0)), value)


def _deep_expand(value):
    if isinstance(value, dict):
        return {k: _deep_expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_expand(v) for v in value]
    return expand_env(value)


DEFAULTS = {
    "edge": {
        "executable": "",
        "port": 9333,
        "profile_dir": str(Path(os.environ.get("LOCALAPPDATA", str(REPO_ROOT))) / "douyin-library" / "edge-profile"),
    },
    "capture": {
        "delay_min_sec": 2.0,
        "delay_max_sec": 5.0,
        "max_idle_scrolls": 5,
        "max_scrolls": 400,
        "page_load_timeout_sec": 60,
    },
    "covers": {"width": 480, "max_bytes": 61440, "format": "webp"},
    "deepdive": {"keep_video": False},
    "lists": {"watch_later_bridge_folder": "稍后再看·留存"},
    "paths": {
        "taxonomy": "config/taxonomy.yml",
        "db": "data/library.db",
        "raw": "data/raw",
        "logs": "data/logs",
        "spike": "data/spike",
    },
}


def load_config(settings_path=None):
    path = Path(settings_path) if settings_path else REPO_ROOT / "config" / "settings.yml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = _deep_expand(raw)
    for section, defaults in DEFAULTS.items():
        merged = dict(defaults)
        merged.update(cfg.get(section) or {})
        cfg[section] = merged
    paths = {}
    for key, value in cfg["paths"].items():
        p = Path(str(value))
        paths[key] = p if p.is_absolute() else REPO_ROOT / p
    cfg["paths"] = paths
    for key in ("vault_dir", "media_dir"):
        if cfg.get(key):
            cfg[key] = Path(str(cfg[key]))
    cfg["repo_root"] = REPO_ROOT
    cfg["settings_path"] = path
    return cfg


def now_iso():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_id():
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def ensure_dirs(*paths):
    for p in paths:
        Path(p).mkdir(parents=True, exist_ok=True)


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json_file(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def id8(aweme_id):
    s = str(aweme_id or "")
    return s[-8:] if len(s) > 8 else s


_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def sanitize_filename(name, max_len=60, fallback="未命名"):
    s = _ILLEGAL.sub(" ", str(name or ""))
    s = re.sub(r"\s+", " ", s).strip().strip(".")
    if not s:
        s = fallback
    return s[:max_len].strip() or fallback


def fmt_duration(seconds):
    try:
        total = int(float(seconds or 0))
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}小时{m}分"
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"


def read_text(path):
    return Path(path).read_text(encoding="utf-8")


def write_text_if_changed(path, text):
    p = Path(path)
    old = p.read_text(encoding="utf-8") if p.exists() else None
    if old == text:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    return True


_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)


def parse_frontmatter(text):
    m = _FM_RE.match(text or "")
    if not m:
        return None, text or ""
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        return None, text or ""
    if not isinstance(fm, dict):
        return None, text or ""
    return fm, (text or "")[m.end():]


def dump_frontmatter(fm):
    body = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False, width=100000)
    return "---\n" + body + "---\n"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def log(msg=""):
    print(msg, flush=True)
