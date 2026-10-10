# -*- coding: utf-8 -*-
"""按发布日期重整「条目」文件名：`YYYY-MM-DD 作者-标题-<id8>.md`（只改名，不动内容）。

用途：把历史生成的旧式文件名一次性对齐到当前命名规则，让 Obsidian 的
文件列表按发布时间排列。默认只预览；加 `--apply` 才真正改名。

安全性：同步脚本按 frontmatter 的 `aweme_id` 认领笔记，改名不影响后续同步；
`--apply` 时会同步更新数据库里记录的笔记路径。索引页（分类 / 待看清单等）
里的链接会在下次 `同步.cmd --skip-fetch` 时刷新，建议改名后顺手跑一次。
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import common, db, notes


def build_plan(vault):
    base = Path(vault) / "条目"
    plan = []
    skipped = []
    if not base.exists():
        return plan, skipped
    targets_used = {}
    for path in sorted(base.glob("*.md")):
        try:
            fm, _ = common.parse_frontmatter(path.read_text(encoding="utf-8"))
        except OSError as exc:
            skipped.append((path, f"读取失败：{exc}"))
            continue
        if not fm or not fm.get("aweme_id"):
            skipped.append((path, "没有 frontmatter / aweme_id，跳过"))
            continue
        item = {
            "author_name": fm.get("作者"),
            "title": fm.get("标题"),
            "published_at": fm.get("发布时间"),
            "aweme_id": fm.get("aweme_id"),
        }
        target = base / notes.default_filename(item)
        if target.name == path.name:
            continue  # 已符合命名规则
        if target.name in targets_used:
            skipped.append((path, f"目标名冲突：{target.name}"))
            continue
        if target.exists() and target != path:
            skipped.append((path, f"目标已存在：{target.name}"))
            continue
        targets_used[target.name] = path
        plan.append((path, target, str(fm["aweme_id"])))
    return plan, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(description="按发布日期重整「条目」文件名（默认只预览）")
    parser.add_argument("--apply", action="store_true", help="真正执行改名")
    parser.add_argument("--settings")
    args = parser.parse_args(argv)
    cfg = common.load_config(args.settings)
    vault = Path(cfg["vault_dir"])
    if not vault.exists():
        print(f"库目录不存在：{vault}")
        return 1
    plan, skipped = build_plan(vault)
    for old, new, _ in plan:
        print(f"{old.name}\n  → {new.name}")
    for path, why in skipped:
        print(f"[跳过] {path.name}：{why}")
    if not plan:
        print(f"没有需要改名的文件（跳过 {len(skipped)} 个）。")
        return 0
    if not args.apply:
        print(f"\n预览：将改 {len(plan)} 个文件名，跳过 {len(skipped)} 个。确认后加 --apply 执行。")
        return 0
    renamed = []
    for old, new, aweme_id in plan:
        try:
            old.rename(new)
            renamed.append((aweme_id, str(new)))
        except OSError as exc:
            print(f"[失败] {old.name} → {new.name}：{exc}")
    db_path = Path(cfg["paths"]["db"])
    if renamed and db_path.exists():
        try:
            con = db.connect(db_path)
            for aweme_id, new_path in renamed:
                db.set_fields(con, aweme_id, note_path=new_path)
            con.close()
        except Exception as exc:  # 数据库未更新也不阻塞改名，下次同步会自动认领
            print(f"[提示] 数据库路径未更新（{exc}）；下次同步会自动认领。")
    print(f"\n完成：已改 {len(renamed)}/{len(plan)} 个文件名，跳过 {len(skipped)} 个。")
    print("建议接着运行 `同步.cmd --skip-fetch`，刷新索引页里的链接。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
