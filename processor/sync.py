# -*- coding: utf-8 -*-
"""同步入口：Edge 抓取 → 本地处理。双击「同步.cmd」执行这里。"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from . import common
from . import run as runmod


def _node(script, *args):
    cmd = ["node", str(Path(common.REPO_ROOT) / "fetcher" / script), *args]
    return subprocess.run(cmd, cwd=str(common.REPO_ROOT), check=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description="抖音收藏同步")
    parser.add_argument("--dry-run", action="store_true", help="只抓取和计算，不写入任何文件")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过抓取，直接处理最近一次原始数据")
    parser.add_argument("--raw-dir", help="指定要处理的原始数据目录")
    parser.add_argument("--headless", action="store_true", help="用无头模式抓取（调试用）")
    parser.add_argument("--login", action="store_true", help="启动专用 Edge 并打开抖音登录页")
    parser.add_argument("--status", action="store_true", help="检查专用 Edge 调试端口状态")
    parser.add_argument("--spike", action="store_true", help="运行 M0 可行性探测并生成报告")
    parser.add_argument("--settings")
    args = parser.parse_args(argv)

    cfg = common.load_config(args.settings)

    if args.status:
        return _node("edge-launch.mjs", "--status").returncode
    if args.login:
        return _node("edge-launch.mjs", "--login").returncode
    if args.spike:
        return _node("spike.mjs").returncode

    raw_dir = args.raw_dir
    if not args.skip_fetch and not raw_dir:
        rid = common.run_id()
        raw_dir = str(Path(cfg["paths"]["raw"]) / rid)
        common.ensure_dirs(raw_dir, cfg["paths"]["logs"])
        print(f"运行编号: {rid}")
        cmd_args = ["--out", raw_dir]
        if args.headless:
            cmd_args.append("--headless")
        if args.settings:
            cmd_args += ["--settings", str(cfg["settings_path"])]
        rc = _node("capture-collections.mjs", *cmd_args).returncode
        if rc == 3:
            print("")
            print("⚠ 还没有登录抖音。请先双击「登录抖音.cmd」扫码登录，然后重新运行「同步.cmd」。")
            return 2
        if rc != 0:
            print("")
            print("⚠ 抓取失败（详见上面日志和 data\\raw 里的 manifest.json）。")
            return 1

    summary = runmod.run_pipeline(cfg, raw_dir=raw_dir, dry_run=args.dry_run)
    runmod.print_summary(summary, cfg)

    log_dir = Path(cfg["paths"]["logs"])
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / f"run-{common.run_id()}.md"
    logfile.write_text(
        f"# 同步记录\n\n- 时间：{common.now_iso()}\n- 原始数据：{summary['raw_dir']}\n"
        f"- 新增 {summary['new']} / 更新 {summary['updated']} / 未变 {summary['unchanged']} / "
        f"离开待看 {summary['left']} / 未分类 {summary['uncategorized']}\n"
        f"- 封面 成功{summary['cover_ok']}/失败{summary['cover_fail']}；"
        f"笔记 写入{summary['notes_written']}/未变{summary['notes_unchanged']}\n"
        f"- 抓取完整：{'否（已跳过离开待看判定）' if summary['partial'] else '是'}\n"
        f"- 用时：{summary['elapsed_sec']} 秒\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"运行记录: {logfile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
