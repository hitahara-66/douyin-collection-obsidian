# -*- coding: utf-8 -*-
"""离线自检：不依赖抖音登录，验证处理管线的全部关键行为。"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from . import common, db
from . import run as runmod

BRIDGE = "稍后再看·留存"
PASS = 0
FAIL = 0


def check(name, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS - {name}")
    else:
        FAIL += 1
        print(f"FAIL - {name}" + (f"（{extra}）" if extra else ""))


def build_workspace(root: Path):
    vault = root / "vault"
    media = root / "media"
    data = root / "data"
    settings = root / "settings.yml"
    tax = root / "taxonomy.yml"
    tax.write_text(
        'default: "未分类"\ncategories:\n  - name: "学习"\n    keywords: ["教程"]\n    priority: 10\n',
        encoding="utf-8",
    )
    settings.write_text(
        "\n".join(
            [
                f'vault_dir: "{vault.as_posix()}"',
                f'media_dir: "{media.as_posix()}"',
                "paths:",
                f'  taxonomy: "{tax.as_posix()}"',
                f'  db: "{(data / "library.db").as_posix()}"',
                f'  raw: "{(data / "raw").as_posix()}"',
                f'  logs: "{(data / "logs").as_posix()}"',
                f'  spike: "{(data / "spike").as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return settings


def aweme(aweme_id, title, author, kind="video", tags=("教程",), duration=63000):
    rec = {
        "aweme_id": aweme_id,
        "desc": title,
        "create_time": 1700000000,
        "author": {"nickname": author, "uid": "u-" + aweme_id},
        "text_extra": [{"hashtag_name": t} for t in tags],
        "share_info": {"share_url": f"https://www.iesdouyin.com/share/video/{aweme_id}/?region=CN&mid=123&u_code=abc"},
    }
    if kind == "video":
        rec["video"] = {"duration": duration, "cover": {"url_list": [f"https://example.invalid/{aweme_id}.jpg"]}}
    else:
        rec["images"] = [{"url_list": [f"https://example.invalid/{aweme_id}-1.jpg"]}]
    return rec


def write_raw(raw_root: Path, name: str, bridge_ids, watchlater_ids=("3001", "3002")):
    folder = raw_root / name
    folder.mkdir(parents=True, exist_ok=True)
    base_items = [
        aweme("1001", "Python 教程 入门", "张三"),
        aweme("1002", "家常菜 做饭", "李四", tags=("做饭",)),
        aweme("1003", "图集测试", "王五", kind="images", tags=()),
    ]
    (folder / "listcollection.0001.json").write_text(
        json.dumps({"aweme_list": base_items, "has_more": 0}, ensure_ascii=False), encoding="utf-8"
    )
    (folder / "collects-video.f_learn.0001.json").write_text(
        json.dumps({"aweme_list": [base_items[0]], "has_more": 0}, ensure_ascii=False), encoding="utf-8"
    )
    bridge_items = [aweme(i, f"待看视频 {i}" + (" #标签测试" if i == "2002" else ""), "赵六", tags=()) for i in bridge_ids]
    (folder / "collects-video.f_bridge.0001.json").write_text(
        json.dumps({"aweme_list": bridge_items, "has_more": 0}, ensure_ascii=False), encoding="utf-8"
    )
    later_items = [aweme(i, f"稍后看视频 {i}", "钱七", tags=()) for i in watchlater_ids]
    (folder / "watchlater.0001.json").write_text(
        json.dumps({"items": later_items, "has_more": False, "offset": 0, "list_num": len(later_items)}, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest = {
        "favorites_complete": True,
        "watch_later": {"complete": True, "pages": 1, "captured": True},
        "folders": {
            "complete": True,
            "discovered": [{"id": "f_bridge", "name": BRIDGE}, {"id": "f_learn", "name": "学习"}],
            "results": [],
        },
        "partial": False,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return folder


def snapshot(vault: Path):
    result = {}
    for path in sorted(vault.rglob("*")):
        if path.is_file():
            result[path.relative_to(vault).as_posix()] = common.sha256_file(path)
    return result


def run_tests(root: Path):
    settings = build_workspace(root)
    cfg = common.load_config(settings)
    raw_root = Path(cfg["paths"]["raw"])

    r1 = write_raw(raw_root, "run1", ["2001", "2002"])
    s1 = runmod.run_pipeline(cfg, raw_dir=r1, offline_covers=True)
    check("首次导入 7 条", s1["new"] == 7, f"实际 {s1['new']}")
    check("未分类计数正确", s1["uncategorized"] == 6, f"实际 {s1['uncategorized']}")
    con = db.connect(cfg["paths"]["db"])
    row_2001 = db.get_item(con, "2001")
    check("桥接条目状态=待看", row_2001["status"] == "待看", str(row_2001["status"]))
    check("桥接条目来源正确", row_2001["source"] == BRIDGE, str(row_2001["source"]))
    row_3001 = db.get_item(con, "3001")
    check("稍后再看条目状态=待看", row_3001["status"] == "待看", str(row_3001["status"]))
    check("稍后再看条目来源正确", row_3001["source"] == "稍后再看", str(row_3001["source"]))
    con.close()

    vault = Path(cfg["vault_dir"])
    snap1 = snapshot(vault)
    check("笔记生成 7 篇", len([p for p in snap1 if p.startswith("条目/")]) == 7)
    check("封面生成 7 张", len([p for p in snap1 if p.startswith("attachments/covers/")]) == 7)
    check(
        "索引文件齐全",
        all((vault / f).exists() for f in ("开始这里.md", "统计.md", "未分类.md", "待看清单.md", "分类/学习.md")),
    )
    note_names = [p.split("/", 1)[1] for p in snap1 if p.startswith("条目/")]
    check("文件名剔除链接特殊字符", all(not any(c in n for c in "#^[]") for n in note_names), str(note_names))
    links = []
    for page in ("分类/学习.md", "待看清单.md", "未分类.md"):
        for m in re.finditer(r"\[\[([^|\]]+)\|", (vault / page).read_text(encoding="utf-8")):
            links.append(m.group(1))
    ok_links = bool(links) and all(
        "/" not in t and "#" not in t and (vault / "条目" / f"{t}.md").is_file() for t in links
    )
    check("索引链接为可解析的最短路径", ok_links, f"{len(links)} 条链接")
    con = db.connect(cfg["paths"]["db"])
    note_1001_path = Path(db.get_item(con, "1001")["note_path"])
    con.close()
    note_text = note_1001_path.read_text(encoding="utf-8")
    check("分享链接已去掉跟踪参数", "分享链接" in note_text and "?region=" not in note_text)

    s2 = runmod.run_pipeline(cfg, raw_dir=r1, offline_covers=True)
    check("重复运行零新增", s2["new"] == 0 and s2["notes_written"] == 0)
    check("重复运行字节级幂等", snapshot(vault) == snap1)

    con = db.connect(cfg["paths"]["db"])
    note_path = Path(db.get_item(con, "1001")["note_path"])
    con.close()
    text = note_path.read_text(encoding="utf-8")
    text = text.replace("深挖: false", "深挖: true").replace("状态: 未标记", "状态: 已看")
    text += "\n我的手动笔记：这段不能丢\n"
    note_path.write_text(text, encoding="utf-8", newline="\n")

    runmod.run_pipeline(cfg, raw_dir=r1, offline_covers=True)
    con = db.connect(cfg["paths"]["db"])
    row_1001 = db.get_item(con, "1001")
    check("读回用户标星", int(row_1001["starred"]) == 1 and int(row_1001["starred_override"] or 0) == 1)
    check("读回用户状态", row_1001["status"] == "已看", str(row_1001["status"]))
    con.close()
    text3 = note_path.read_text(encoding="utf-8")
    check("手动区保留", "我的手动笔记：这段不能丢" in text3)
    check("深挖字段保留", "深挖: true" in text3)

    snap3 = snapshot(vault)
    s4 = runmod.run_pipeline(cfg, raw_dir=r1, offline_covers=True)
    check("编辑后再次同步幂等", snapshot(vault) == snap3, f"新增{s4['new']} 写{s4['notes_written']}")

    # 保险：数据库已有条目但库目录不见了 → 必须中止报错，而不是另建一套空库
    moved = root / "vault-moved"
    bad_settings = root / "settings-moved.yml"
    bad_settings.write_text(
        "\n".join(
            f'vault_dir: "{moved.as_posix()}"' if line.startswith("vault_dir:") else line
            for line in settings.read_text(encoding="utf-8").splitlines()
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        runmod.run_pipeline(common.load_config(bad_settings), raw_dir=r1, offline_covers=True)
        guard_raised = False
    except SystemExit:
        guard_raised = True
    check("库被移动时中止并报错", guard_raised and not moved.exists())

    r2 = write_raw(raw_root, "run2", ["2001"], ["3001"])
    s5 = runmod.run_pipeline(cfg, raw_dir=r2, offline_covers=True)
    con = db.connect(cfg["paths"]["db"])
    row_2002 = db.get_item(con, "2002")
    check("离开待看自动标记", row_2002["status"] == "已离开待看队列", str(row_2002["status"]))
    row_3002 = db.get_item(con, "3002")
    check("稍后再看离开自动标记", row_3002["status"] == "已离开待看队列", str(row_3002["status"]))
    check("离开计数=2", s5["left"] == 2, str(s5["left"]))
    con.close()
    todo = (vault / "待看清单.md").read_text(encoding="utf-8")
    check("待看清单移除已离开条目", "待看视频 2002" not in todo)
    check("待看清单移除稍后再看条目", "稍后看视频 3002" not in todo)

    r3 = write_raw(raw_root, "run3", ["2001", "2002"], ["3001", "3002"])
    runmod.run_pipeline(cfg, raw_dir=r3, offline_covers=True)
    con = db.connect(cfg["paths"]["db"])
    row_2002 = db.get_item(con, "2002")
    check("回归待看队列", row_2002["status"] == "待看", str(row_2002["status"]))
    row_3002 = db.get_item(con, "3002")
    check("稍后再看回归队列", row_3002["status"] == "待看", str(row_3002["status"]))
    con.close()

    snap5 = snapshot(vault)
    s7 = runmod.run_pipeline(cfg, raw_dir=r3, dry_run=True, offline_covers=True)
    check("dry-run 不写文件", snapshot(vault) == snap5 and s7["dry_run"] is True)

    fm, _ = common.parse_frontmatter(note_path.read_text(encoding="utf-8"))
    expected = {"标题", "作者", "链接", "来源", "分类", "标签", "状态", "发布时间", "首次入库", "深挖", "aweme_id"}
    check("frontmatter 字段齐全", set(fm or {}) == expected, str(sorted((fm or {}).keys())))


def main():
    root = Path(tempfile.mkdtemp(prefix="dylib-selfcheck-"))
    run_tests(root)
    print("")
    print(f"自检结果: {PASS} 项通过 / {FAIL} 项失败")
    print(f"测试目录: {root}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
