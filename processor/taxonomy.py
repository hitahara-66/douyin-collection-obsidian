# -*- coding: utf-8 -*-
"""分类规则：taxonomy.yml 读取与匹配。"""
from __future__ import annotations

from pathlib import Path

import yaml


def load_rules(path):
    p = Path(path)
    raw = {}
    if p.exists():
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    categories = []
    for item in raw.get("categories") or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        categories.append(
            {
                "name": str(item["name"]).strip(),
                "keywords": [str(k).lower() for k in (item.get("keywords") or []) if str(k).strip()],
                "authors": [str(a) for a in (item.get("authors") or []) if str(a).strip()],
                "priority": int(item.get("priority") or 0),
                "_order": len(categories),
            }
        )
    categories.sort(key=lambda c: (-c["priority"], c["_order"]))
    return {"default": str(raw.get("default") or "未分类"), "categories": categories}


def classify(title, tags, author, rules):
    text = (title or "").lower()
    tag_text = " ".join(str(t) for t in (tags or [])).lower()
    for cat in rules["categories"]:
        for kw in cat["keywords"]:
            if kw and (kw in text or kw in tag_text):
                return cat["name"]
        if author and author in cat["authors"]:
            return cat["name"]
    return rules["default"]


def category_names(rules):
    return [c["name"] for c in rules["categories"]]
