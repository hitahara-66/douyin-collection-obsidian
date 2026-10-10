# -*- coding: utf-8 -*-
"""核心流水线：原始 JSON → SQLite → 封面 → Obsidian 笔记 → 索引。"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

from . import common, covers, db, notes, rawimport
from . import taxonomy as tax


def latest_raw_dir(cfg):
    root = Path(cfg["paths"]["raw"])
    if not root.exists():
        return None
    dirs = [d for d in root.iterdir() if d.is_dir() and (d / "manifest.json").exists()]
    if not dirs:
        return None
    return max(dirs, key=lambda d: d.stat().st_mtime)


def build_note_index(vault):
    base = Path(vault) / "条目"
    index = {}
    if not base.exists():
        return index
    for path in base.glob("*.md"):
        try:
            fm, _ = common.parse_frontmatter(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if fm and fm.get("aweme_id"):
            index[str(fm["aweme_id"])] = path
    return index


def adopt_note_edits(con, cfg):
    """把用户在笔记 frontmatter 里的修改（分类/标签/状态/深挖）收进 DB。"""
    index = build_note_index(cfg["vault_dir"])
    changes = 0
    for row in db.all_items(con):
        path = None
        if row["note_path"] and Path(row["note_path"]).exists():
            path = Path(row["note_path"])
        if path is None:
            path = index.get(row["aweme_id"])
            if path is not None:
                db.set_fields(con, row["aweme_id"], note_path=str(path))
        if path is None:
            continue
        try:
            fm, _ = common.parse_frontmatter(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not fm:
            continue
        try:
            last = json.loads(row["last_auto"] or "{}")
        except Exception:
            last = {}
        updates = {}
        cur_cat = fm.get("分类")
        if cur_cat is not None and str(cur_cat) != str(last.get("分类")) and row["category_override"] != str(cur_cat):
            updates["category_override"] = str(cur_cat)
        cur_status = fm.get("状态")
        if cur_status is not None and str(cur_status) != str(last.get("状态")) and row["status_override"] != str(cur_status):
            updates["status_override"] = str(cur_status)
        cur_tags = fm.get("标签")
        if cur_tags is not None:
            cur_list = [str(x) for x in cur_tags] if isinstance(cur_tags, list) else ([str(cur_tags)] if cur_tags else [])
            prev_list = [str(x) for x in (last.get("标签") or [])]
            if cur_list != prev_list:
                updates["tags_override"] = json.dumps(cur_list, ensure_ascii=False)
        cur_star = fm.get("深挖")
        if cur_star is not None:
            cur_b = 1 if cur_star else 0
            prev_b = 1 if last.get("深挖") else 0
            if cur_b != prev_b and row["starred_override"] != cur_b:
                updates["starred_override"] = cur_b
        if updates:
            db.set_fields(con, row["aweme_id"], **updates)
            changes += len(updates)
    return changes


def row_to_item(row):
    override_tags = db.override_tags_of(row)
    tags = override_tags if override_tags is not None else db.tags_of(row)
    starred = row["starred_override"] if row["starred_override"] is not None else row["starred"]
    return {
        "aweme_id": row["aweme_id"],
        "kind": row["kind"],
        "title": row["title"],
        "author_name": row["author_name"],
        "author_id": row["author_id"],
        "url": row["url"],
        "share_url": row["share_url"],
        "cover_url": row["cover_url"],
        "cover_path": row["cover_path"],
        "images_json": row["images_json"],
        "published_at": row["published_at"],
        "duration_sec": row["duration_sec"],
        "first_seen_at": row["first_seen_at"],
        "folders": db.folders_of(row),
        "source": row["source"],
        "status": row["status"],
        "category": row["category"],
        "tags_list": tags,
        "starred": bool(starred),
        "deep_state": row["deep_state"],
        "transcript_path": row["transcript_path"],
        "note_path": row["note_path"],
    }


def run_pipeline(cfg, raw_dir=None, dry_run=False, offline_covers=False, export_samples=False, limit=None):
    t0 = time.time()
    raw_path = Path(raw_dir) if raw_dir else latest_raw_dir(cfg)
    if raw_path is None or not raw_path.exists():
        raise SystemExit(f"找不到原始数据目录：{raw_dir or cfg['paths']['raw']}。请先运行「同步.cmd」。")

    tmp_dir = None
    work_db = Path(cfg["paths"]["db"])
    if dry_run:
        tmp_dir = Path(tempfile.mkdtemp(prefix="dylib-dryrun-"))
        work_db = tmp_dir / "library.db"
        if Path(cfg["paths"]["db"]).exists():
            shutil.copy2(cfg["paths"]["db"], work_db)

    con = db.connect(work_db)
    rules = tax.load_rules(cfg["paths"]["taxonomy"])
    known = db.all_items(con)
    vault_dir = Path(cfg["vault_dir"])
    if known and not vault_dir.exists():
        sample = next((row["note_path"] for row in known if row["note_path"]), "")
        msg = [
            f"⚠ 库目录不存在：{vault_dir}",
            f"   数据库里已有 {len(known)} 条记录，说明库被移动或改名了。",
        ]
        if sample:
            msg.append(f"   上次写入的笔记：{sample}")
        msg += [
            "   请改 config\\settings.yml 的 vault_dir 指向现有库后重跑；",
            "   想重建整个库：先删掉 data\\library.db 再跑（原始数据仍在，可重放）。",
        ]
        raise SystemExit("\n".join(msg))
    adopted = adopt_note_edits(con, cfg)
    previous_bridge = {row["aweme_id"] for row in db.all_items(con) if row["in_bridge"]}
    previous_watch_later = {row["aweme_id"] for row in db.all_items(con) if row["in_watch_later"]}
    # 先清空"是否仍在队列"标记，再由本次抓取结果重新标记；
    # 否则本轮没出现的条目会残留旧标记，导致离开判定被误跳过。
    con.execute("UPDATE items SET in_bridge = 0, in_watch_later = 0")
    con.commit()
    raw = rawimport.load_raw(raw_path, cfg["lists"]["watch_later_bridge_folder"])
    now = common.now_iso()
    counts = dict(
        new=0,
        updated=0,
        unchanged=0,
        left=0,
        uncategorized=0,
        cover_ok=0,
        cover_fail=0,
        notes_written=0,
        notes_unchanged=0,
    )
    items = raw["items"][:limit] if limit else raw["items"]
    for rec in items:
        row = db.get_item(con, rec["aweme_id"])
        tags_json = json.dumps(rec.get("hashtags") or [], ensure_ascii=False)
        if row is None:
            rec2 = dict(rec)
            rec2.update(
                first_seen_at=now,
                last_seen_at=now,
                updated_at=now,
                status="待看" if (rec["in_bridge"] or rec.get("in_watch_later")) else "未标记",
                category="",
                category_override=None,
                tags=tags_json,
                tags_override=None,
                starred=0,
                starred_override=None,
                deep_state="",
                transcript_path="",
                note_path="",
                last_auto="{}",
                in_favorites=1 if rec["in_favorites"] else 0,
                in_watch_later=1 if rec.get("in_watch_later") else 0,
                in_bridge=1 if rec["in_bridge"] else 0,
                folders=json.dumps(rec["folders"], ensure_ascii=False),
            )
            db.insert_item(con, rec2)
            counts["new"] += 1
        else:
            changed = any(
                str(row[k] or "") != str(rec.get(k) or "")
                for k in ("title", "author_name", "url", "published_at", "duration_sec", "kind")
            )
            db.set_fields(
                con,
                rec["aweme_id"],
                last_seen_at=now,
                updated_at=now,
                in_favorites=1 if rec["in_favorites"] else 0,
                in_watch_later=1 if rec.get("in_watch_later") else 0,
                in_bridge=1 if rec["in_bridge"] else 0,
                folders=json.dumps(rec["folders"], ensure_ascii=False),
                source=rec["source"],
                title=rec["title"],
                author_name=rec["author_name"],
                author_id=rec["author_id"],
                url=rec["url"],
                share_url=rec["share_url"],
                cover_url=rec["cover_url"],
                images_json=rec["images_json"],
                published_at=rec["published_at"],
                duration_sec=rec["duration_sec"],
                kind=rec["kind"],
                tags=tags_json,
            )
            counts["updated" if changed else "unchanged"] += 1

    queues = []
    if raw["watch_later_complete"]:
        queues.append((previous_watch_later, raw["seen_in_watch_later"]))
    if raw["folders_complete"]:
        queues.append((previous_bridge, raw["seen_in_bridge"]))
    for previous, still in queues:
        for row in db.all_items(con):
            if row["aweme_id"] in previous and row["aweme_id"] not in still:
                fresh = db.get_item(con, row["aweme_id"])
                if fresh["in_bridge"] or fresh["in_watch_later"]:
                    continue  # 还留在另一个待看队列里
                if fresh["status_override"] is None and (fresh["status"] or "") == "待看":
                    db.set_fields(con, fresh["aweme_id"], status="已离开待看队列", updated_at=now)
                    counts["left"] += 1
        for row in db.all_items(con):
            if row["aweme_id"] in still and row["status_override"] is None and (row["status"] or "") == "已离开待看队列":
                db.set_fields(con, row["aweme_id"], status="待看", updated_at=now)

    for row in db.all_items(con):
        auto_tags = db.tags_of(row)
        category = row["category_override"] or tax.classify(row["title"], auto_tags, row["author_name"], rules)
        status = row["status_override"] if row["status_override"] is not None else row["status"]
        starred = row["starred_override"] if row["starred_override"] is not None else row["starred"]
        db.set_fields(con, row["aweme_id"], category=category, status=status, starred=1 if starred else 0, updated_at=now)
        if category == rules["default"]:
            counts["uncategorized"] += 1

    if not dry_run:
        for row in db.all_items(con):
            item = row_to_item(row)
            ok, path, _err = covers.ensure_cover(item, cfg, offline=offline_covers)
            if ok:
                counts["cover_ok"] += 1
                db.set_fields(con, item["aweme_id"], cover_path=str(path))
            else:
                counts["cover_fail"] += 1

        transcripts_dir = Path(cfg["paths"]["db"]).parent / "transcripts"
        for row in db.all_items(con):
            row = db.get_item(con, row["aweme_id"])
            item = row_to_item(row)
            transcript = ""
            tpath = Path(item["transcript_path"]) if item.get("transcript_path") else transcripts_dir / f"{common.id8(item['aweme_id'])}.md"
            if tpath.exists():
                transcript = tpath.read_text(encoding="utf-8")
            status, path, fm = notes.write_note(item, cfg, transcript)
            counts["notes_written" if status == "written" else "notes_unchanged"] += 1
            last_auto = {k: fm[k] for k in ("分类", "标签", "状态", "深挖")}
            db.set_fields(con, item["aweme_id"], note_path=str(path), last_auto=json.dumps(last_auto, ensure_ascii=False))

        index_items = [row_to_item(row) for row in db.all_items(con)]
        notes.write_indexes(index_items, cfg, rules)

    if export_samples:
        out_dir = Path(cfg["paths"]["db"]).parent / "samples"
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = [row_to_item(r) for r in db.all_items(con)][:300]
        with open(out_dir / "samples.jsonl", "w", encoding="utf-8", newline="\n") as f:
            for it in rows:
                f.write(
                    json.dumps(
                        {
                            "aweme_id": it["aweme_id"],
                            "标题": it["title"],
                            "作者": it["author_name"],
                            "标签": it["tags_list"],
                            "分类": it["category"],
                            "时长秒": it["duration_sec"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        print(f"样本已导出: {out_dir / 'samples.jsonl'}（{len(rows)} 条，供 Codex 聚类分类草案）")

    manifest = raw.get("manifest") or {}
    partial = bool(manifest.get("partial"))
    wl_meta = manifest.get("watch_later") if isinstance(manifest.get("watch_later"), dict) else {}
    elapsed = round(time.time() - t0, 1)
    if not dry_run:
        db.insert_run(
            con,
            {
                "id": common.run_id(),
                "started_at": now,
                "ended_at": common.now_iso(),
                "mode": "sync",
                "partial": 1 if partial else 0,
                "new_count": counts["new"],
                "updated_count": counts["updated"],
                "unchanged_count": counts["unchanged"],
                "left_count": counts["left"],
                "uncategorized_count": counts["uncategorized"],
                "cover_ok": counts["cover_ok"],
                "cover_fail": counts["cover_fail"],
                "notes_written": counts["notes_written"],
                "notes_unchanged": counts["notes_unchanged"],
                "raw_dir": str(raw_path),
                "error": "",
            },
        )
    con.close()
    if tmp_dir:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return {
        **counts,
        "adopted_overrides": adopted,
        "partial": partial,
        "watch_later_complete": raw["watch_later_complete"],
        "watch_later_pages": wl_meta.get("pages", 0),
        "elapsed_sec": elapsed,
        "raw_dir": str(raw_path),
        "dry_run": dry_run,
    }


def print_summary(summary, cfg=None):
    print("")
    print(
        f"【本次处理】新增 {summary['new']} · 更新 {summary['updated']} · 未变 {summary['unchanged']} · "
        f"离开待看 {summary['left']} · 未分类 {summary['uncategorized']}"
    )
    print(
        f"         封面 成功{summary['cover_ok']}/失败{summary['cover_fail']} · "
        f"笔记 写入{summary['notes_written']}/未变{summary['notes_unchanged']} · 覆盖项 {summary['adopted_overrides']}"
    )
    if summary.get("partial"):
        print("         ⚠ 本次抓取不完整：已跳过「离开待看」判定（避免误标）")
    elif not summary.get("watch_later_complete", True):
        print("         ⚠ 本次未抓全「稍后再看」：已跳过它的离开判定（避免误标）")
    tail = "（dry-run：未写入任何文件）" if summary.get("dry_run") else ""
    print(f"         用时 {summary['elapsed_sec']} 秒{tail}")
    if cfg is not None:
        print(f"         原始数据: {summary['raw_dir']}")
        print(f"         Obsidian 库: {cfg['vault_dir']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="处理原始 JSON → 本地库（一般由 同步.cmd 调用）")
    parser.add_argument("--raw-dir")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--offline-covers", action="store_true")
    parser.add_argument("--export-samples", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--settings")
    args = parser.parse_args(argv)
    cfg = common.load_config(args.settings)
    summary = run_pipeline(
        cfg,
        raw_dir=args.raw_dir,
        dry_run=args.dry_run,
        offline_covers=args.offline_covers,
        export_samples=args.export_samples,
        limit=args.limit,
    )
    print_summary(summary, cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
