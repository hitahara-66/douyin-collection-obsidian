# -*- coding: utf-8 -*-
"""Obsidian 笔记与索引生成（幂等，保留手动区）。"""
from __future__ import annotations

from pathlib import Path

from . import common

DIVIDER = "<!-- 自动生成结束 · 以下为手动区，脚本不会修改 -->"


def default_filename(item):
    author = common.sanitize_filename(item.get("author_name") or "未知作者", 24, "未知作者")
    title = common.sanitize_filename(item.get("title") or "无标题", 60, "无标题")
    return f"{author}-{title}-{common.id8(item['aweme_id'])}.md"


def build_frontmatter(item):
    return {
        "标题": item.get("title") or "（无标题）",
        "作者": item.get("author_name") or "",
        "链接": item.get("url") or "",
        "来源": item.get("source") or "",
        "分类": item.get("category") or "未分类",
        "标签": list(item.get("tags_list") or []),
        "状态": item.get("status") or "",
        "发布时间": item.get("published_at") or "",
        "首次入库": item.get("first_seen_at") or "",
        "深挖": bool(item.get("starred")),
        "aweme_id": item.get("aweme_id") or "",
    }


def cover_relpath(item, cfg):
    cover = item.get("cover_path")
    if not cover:
        return None
    p = Path(cover)
    if not p.exists():
        return None
    try:
        return p.relative_to(Path(cfg["vault_dir"])).as_posix()
    except ValueError:
        return None


def build_auto_body(item, cover_rel, transcript_text=None):
    lines = []
    if cover_rel:
        lines.append(f"![[{cover_rel}]]")
        lines.append("")
    lines.append(f"- 作者：{item.get('author_name') or '未知'}")
    duration = common.fmt_duration(item.get("duration_sec"))
    if duration:
        lines.append(f"- 时长：{duration}")
    lines.append(f"- 发布：{item.get('published_at') or '未知'} ｜ 首次入库：{item.get('first_seen_at') or ''}")
    links = f"- 原链接：[在抖音打开]({item.get('url') or ''})"
    if item.get("share_url") and item.get("share_url") != item.get("url"):
        links += f" ｜ [分享链接]({item['share_url']})"
    lines.append(links)
    folders = item.get("folders") or []
    if folders:
        lines.append(f"- 收藏夹：{'、'.join(folders)}")
    lines.append("")
    if transcript_text:
        lines.append("> [!quote]- 逐字稿（自动生成）")
        for line in transcript_text.splitlines():
            lines.append(f"> {line}" if line else ">")
        lines.append("")
    lines.append(DIVIDER)
    return "\n".join(lines) + "\n"


def split_manual(text):
    if not text:
        return ""
    idx = text.find(DIVIDER)
    if idx < 0:
        return ""
    manual = text[idx + len(DIVIDER):]
    if manual.startswith("\n"):
        manual = manual[1:]
    return manual


def write_note(item, cfg, transcript_text=None):
    vault = Path(cfg["vault_dir"])
    path = Path(item["note_path"]) if item.get("note_path") else vault / "条目" / default_filename(item)
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    manual = split_manual(old)
    fm = build_frontmatter(item)
    content = common.dump_frontmatter(fm) + build_auto_body(item, cover_relpath(item, cfg), transcript_text) + manual
    if old == content:
        return "unchanged", path, fm
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return "written", path, fm


def _index_line(item, vault):
    note_path = item.get("note_path") or ""
    target = ""
    if note_path:
        try:
            target = Path(note_path).relative_to(Path(vault)).with_suffix("").as_posix()
        except ValueError:
            target = ""
    display = item.get("title") or "（无标题）"
    if not target:
        return f"- {display} — {item.get('author_name') or '未知'}"
    suffix = f" — {item.get('author_name') or '未知'}"
    status = item.get("status") or ""
    if status and status != "未标记":
        suffix += f" · {status}"
    return f"- [[{target}|{display}]]{suffix}"


START_HERE = """# 开始这里

这是「抖音收藏本地库」的说明书页，由脚本自动维护。

## 结构

- `条目/`：一条视频一篇笔记（自动生成 + 你的手动区）
- `分类/`：按分类自动聚合的清单
- `待看清单.md`：仍处于「待看」的条目（收藏 + 稍后再看）
- `未分类.md` / `统计.md`：兜底清单与统计

## 手动区规则

每篇笔记里有一条 `<!-- 自动生成结束 · 以下为手动区，脚本不会修改 -->` 分界线。
分界线**以下**随便写（笔记、摘要、想法），脚本永远不动它。

## 怎么让脚本"听你的"

直接改笔记的 frontmatter（文件顶部 `---` 之间）即可，脚本下次同步会读到：

| 字段 | 作用 |
| --- | --- |
| `分类` | 覆盖自动分类 |
| `标签` | 覆盖自动标签（YAML 列表写法） |
| `状态` | 改成 已看 / 弃看 / 待看 等 |
| `深挖` | 改成 `true` 后，运行「深挖.cmd」会下载原片并转写 |

## 每周流程（约 10 分钟）

1. 双击「同步.cmd」（自动抓取收藏 + 稍后再看，并更新队列状态）；
2. 扫一眼新增条目，给想深挖的标 `深挖: true`；
3. （可选）双击「深挖.cmd」，等它下载 + 转写。
"""


def write_indexes(items, cfg, rules):
    vault = Path(cfg["vault_dir"])
    written = 0
    by_cat = {}
    for item in items:
        by_cat.setdefault(item.get("category") or "未分类", []).append(item)

    cat_dir = vault / "分类"
    generated = set()
    for name, lst in sorted(by_cat.items()):
        lst.sort(key=lambda x: (x.get("first_seen_at") or "", x.get("aweme_id") or ""), reverse=True)
        lines = [f"# {name}", "", f"> 共 {len(lst)} 条 · 由脚本自动生成", ""]
        lines += [_index_line(it, vault) for it in lst]
        fname = f"{common.sanitize_filename(name, 40)}.md"
        generated.add(fname)
        if common.write_text_if_changed(cat_dir / fname, "\n".join(lines) + "\n"):
            written += 1
    if cat_dir.exists():
        for old in cat_dir.glob("*.md"):
            if old.name not in generated:
                old.unlink()

    uncat = by_cat.get("未分类", [])
    lines = ["# 未分类", "", f"> 共 {len(uncat)} 条 · 由脚本自动生成", ""]
    lines += [_index_line(it, vault) for it in uncat]
    if common.write_text_if_changed(vault / "未分类.md", "\n".join(lines) + "\n"):
        written += 1

    todo = [it for it in items if (it.get("status") or "") == "待看"]
    todo.sort(key=lambda x: (x.get("first_seen_at") or "", x.get("aweme_id") or ""), reverse=True)
    lines = ["# 待看清单", "", f"> 共 {len(todo)} 条 · 由脚本自动生成；离开「稍后再看」后会自动移出", ""]
    lines += [_index_line(it, vault) for it in todo]
    if common.write_text_if_changed(vault / "待看清单.md", "\n".join(lines) + "\n"):
        written += 1

    status_count = {}
    source_count = {}
    for it in items:
        status_count[it.get("status") or "（空）"] = status_count.get(it.get("status") or "（空）", 0) + 1
        source_count[it.get("source") or "（空）"] = source_count.get(it.get("source") or "（空）", 0) + 1
    starred = sum(1 for it in items if it.get("starred"))
    transcribed = sum(1 for it in items if it.get("deep_state") == "已转写")
    stat = [
        "# 统计",
        "",
        f"- 总条目：{len(items)}",
        f"- 已标星（深挖）：{starred}",
        f"- 已转写：{transcribed}",
        "",
        "## 按分类",
        "",
    ]
    for name, count in sorted(by_cat.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        stat.append(f"- {name}：{len(count)}")
    stat += ["", "## 按状态", ""]
    for name, count in sorted(status_count.items(), key=lambda kv: (-kv[1], kv[0])):
        stat.append(f"- {name}：{count}")
    stat += ["", "## 按来源", ""]
    for name, count in sorted(source_count.items(), key=lambda kv: (-kv[1], kv[0]))[:30]:
        stat.append(f"- {name}：{count}")
    if common.write_text_if_changed(vault / "统计.md", "\n".join(stat) + "\n"):
        written += 1

    bridge = cfg["lists"]["watch_later_bridge_folder"]
    if common.write_text_if_changed(vault / "开始这里.md", START_HERE.replace("{bridge}", bridge)):
        written += 1
    return written
