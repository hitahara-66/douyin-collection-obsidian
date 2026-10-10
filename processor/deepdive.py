# -*- coding: utf-8 -*-
"""深挖：下载标星条目的原片/图集，并用本地 GPU 转写。"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import requests

from . import common, covers, db, notes, rawimport
from . import run as runmod

# 国内网络访问 HuggingFace 官方源较慢，默认走镜像；设置 HF_ENDPOINT 可覆盖
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")


def _register_cuda_dlls():
    """把 pip 安装的 cuBLAS / cuDNN DLL 目录注册进搜索路径（Windows 上 ctranslate2 需要）。"""
    import glob
    import site

    dirs = []
    bases = set()
    try:
        bases.update(site.getsitepackages())
    except Exception:
        pass
    try:
        bases.add(site.getusersitepackages())
    except Exception:
        pass
    for base in bases:
        dirs.extend(glob.glob(os.path.join(base, "nvidia", "*", "bin")))
    for d in dirs:
        try:
            os.add_dll_directory(d)
        except (AttributeError, OSError):
            pass
    if dirs:
        os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")
    return dirs


CUDA_DLL_DIRS = _register_cuda_dlls()


MEDIA_HEADERS = {
    "User-Agent": covers.HEADERS["User-Agent"],
    "Referer": "https://www.douyin.com/",
}


def _extract_urls(rec):
    video = rec.get("video") or {}
    videos = []

    def push(node):
        for u in (node or {}).get("url_list") or []:
            if isinstance(u, str) and u.startswith("http"):
                videos.append(u)

    for key in ("play_addr_h264", "play_addr", "play_addr_265", "download_addr"):
        push(video.get(key))
    for br in video.get("bit_rate") or []:
        if isinstance(br, dict):
            push(br.get("play_addr"))
    images = []
    for img in rec.get("images") or []:
        for u in (img or {}).get("url_list") or []:
            if isinstance(u, str) and u.startswith("http"):
                images.append(u)
    return {"videos": list(dict.fromkeys(videos)), "images": list(dict.fromkeys(images))}


def media_urls_from_raw(cfg, aweme_id):
    """从最近几次抓取的原始 JSON 里找该条目的直链（签名通常几小时内有效）。"""
    raw_root = Path(cfg["paths"]["raw"])
    if not raw_root.exists():
        return {}
    runs = sorted([d for d in raw_root.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime, reverse=True)
    for run in runs[:3]:
        for pattern in ("watchlater.*.json", "listcollection.*.json", "collects-video.*.json"):
            for f in sorted(run.glob(pattern)):
                for rec in rawimport.extract_aweme_list(f):
                    if str(rec.get("aweme_id")) == str(aweme_id):
                        urls = _extract_urls(rec)
                        if urls["videos"] or urls["images"]:
                            return urls
    return {}


def refresh_media_urls(cfg, aweme_id):
    """原始数据里没找到（或都已过期）时，用 Edge 重新抓一份 detail。"""
    out = Path(cfg["paths"]["raw"]).parent / "deepdive" / f"{aweme_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "node",
        str(Path(cfg["repo_root"]) / "fetcher" / "fetch-item-detail.mjs"),
        "--id",
        str(aweme_id),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, cwd=str(cfg["repo_root"]), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print(f"  ⚠ 刷新直链失败: {(proc.stderr or proc.stdout or '').strip()[-200:]}")
        return {}
    return common.read_json(out, {}) or {}


def download_file(url, dest, label="文件"):
    with requests.get(url, headers=MEDIA_HEADERS, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        last_report = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if total and done - last_report >= 20 * 1024 * 1024:
                    last_report = done
                    print(f"    … {label} {done / 1048576:.0f}/{total / 1048576:.0f} MB")
    if dest.stat().st_size <= 0:
        raise RuntimeError("下载得到空文件")
    return dest


def download_video(item, cfg):
    media = Path(cfg["media_dir"])
    media.mkdir(parents=True, exist_ok=True)
    base = f"{common.id8(item['aweme_id'])}_{common.sanitize_filename(item.get('title') or 'video', 40)}"
    dest = media / f"{base}.mp4"
    if dest.exists() and dest.stat().st_size > 0:
        return dest, None
    last_err = ""
    for round_no in (1, 2):
        urls = media_urls_from_raw(cfg, item["aweme_id"]) if round_no == 1 else refresh_media_urls(cfg, item["aweme_id"])
        candidates = (urls or {}).get("videos") or []
        if not candidates:
            last_err = last_err or "没有找到播放地址"
            continue
        for url in candidates[:8]:
            try:
                print(f"  · 下载直链（{round_no == 1 and '原始数据' or '刷新'}）: {url[:80]}...")
                download_file(url, dest, label="下载")
                return dest, None
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
                dest.unlink(missing_ok=True)
                continue
    return None, f"下载失败: {last_err}"


def cuda_available():
    try:
        import ctranslate2

        return bool(ctranslate2.get_supported_compute_types("cuda"))
    except Exception:
        return False


def download_images(item, cfg):
    out_dir = Path(cfg["media_dir"]) / common.id8(item["aweme_id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    urls = media_urls_from_raw(cfg, item["aweme_id"]).get("images") or []
    if not urls:
        urls = (refresh_media_urls(cfg, item["aweme_id"]) or {}).get("images") or []
    ok = 0
    for i, url in enumerate(urls, 1):
        try:
            resp = requests.get(url, headers=MEDIA_HEADERS, timeout=30)
            resp.raise_for_status()
            (out_dir / f"{i:02d}.jpg").write_bytes(resp.content)
            ok += 1
        except Exception:
            continue
    if ok:
        return out_dir, None
    return None, "图片下载失败"


def transcribe(video_path):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None, "faster-whisper 未安装（重跑「准备.cmd」）"
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None, "PATH 里找不到 ffmpeg"
    audio = Path(video_path).with_suffix(".wav")
    proc = subprocess.run(
        [ffmpeg, "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(audio)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return None, f"ffmpeg 提取音频失败: {(proc.stderr or '')[-300:]}"
    model_pref = (os.environ.get("WHISPER_MODEL") or "").strip() or "large-v3"
    if cuda_available():
        attempts = [(model_pref, "cuda", "int8_float16")]
        if model_pref != "medium":
            attempts.append(("medium", "cuda", "int8_float16"))
        print(f"  · 检测到 CUDA，使用 GPU 转写（{model_pref}）")
    else:
        attempts = [("medium", "cpu", "int8")]
        print("  · 未检测到可用 CUDA，改用 CPU + medium 模型")
    last_err = ""
    for model_name, device, compute in attempts:
        try:
            print(f"  · 加载模型 {model_name}/{device}（首次会自动下载，1.5–3GB）...")
            model = WhisperModel(model_name, device=device, compute_type=compute)
            segments, _info = model.transcribe(
                str(audio),
                language="zh",
                vad_filter=True,
                beam_size=1,
                condition_on_previous_text=False,
            )
            lines = []
            count = 0
            for seg in segments:
                count += 1
                ts = f"[{int(seg.start) // 60:02d}:{int(seg.start) % 60:02d}]"
                lines.append(f"{ts} {seg.text.strip()}")
                if count % 100 == 0:
                    print(f"    … 已转写到 {int(seg.start) // 60} 分钟")
            try:
                audio.unlink()
            except OSError:
                pass
            return "\n".join(lines), None
        except Exception as exc:  # noqa: BLE001
            last_err = f"{model_name}/{device}: {exc}"
    return None, f"转写失败（{last_err}）"


def main(argv=None):
    parser = argparse.ArgumentParser(description="深挖标星条目（下载 + 转写）")
    parser.add_argument("--id", help="只处理指定 aweme_id")
    parser.add_argument("--refresh", action="store_true", help="已完成转写的也重新处理")
    parser.add_argument("--settings")
    args = parser.parse_args(argv)

    cfg = common.load_config(args.settings)
    con = db.connect(cfg["paths"]["db"])
    runmod.adopt_note_edits(con, cfg)

    targets = []
    for row in db.all_items(con):
        starred = row["starred_override"] if row["starred_override"] is not None else row["starred"]
        if args.id and row["aweme_id"] != args.id:
            continue
        if not args.id and not starred:
            continue
        if not args.refresh and not args.id and row["deep_state"] == "已转写":
            continue
        targets.append(row)

    if not targets:
        print("没有待深挖的条目。在 Obsidian 里把想深挖的笔记改成「深挖: true」，再运行本命令。")
        return 0

    print(f"待深挖：{len(targets)} 条")
    transcripts_dir = Path(cfg["paths"]["db"]).parent / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    done = 0
    for row in targets:
        item = runmod.row_to_item(row)
        label = f"{item['title'] or item['aweme_id']}（{item['aweme_id']}）"
        print(f"\n→ {label}")
        state = row["deep_state"] or ""
        if item["kind"] == "images":
            path, err = download_images(item, cfg)
            if err:
                print(f"  ✗ {err}")
                continue
            state = "已存图"
        else:
            video, err = download_video(item, cfg)
            if err:
                print(f"  ✗ 下载失败: {err}")
                continue
            print(f"  ✓ 原片: {video}")
            text, terr = transcribe(video)
            if terr:
                print(f"  ⚠ 转写失败: {terr}")
                state = "已下载"
            else:
                tpath = transcripts_dir / f"{common.id8(item['aweme_id'])}.md"
                tpath.write_text(text, encoding="utf-8", newline="\n")
                db.set_fields(con, item["aweme_id"], transcript_path=str(tpath))
                state = "已转写"
                print(f"  ✓ 逐字稿: {tpath}（{len(text)} 字）")
                if not cfg.get("deepdive", {}).get("keep_video", False):
                    try:
                        video.unlink()
                        print("  ✓ 已删除临时原片（只保留逐字稿）")
                    except OSError:
                        pass
        db.set_fields(con, item["aweme_id"], deep_state=state)
        fresh = db.get_item(con, item["aweme_id"])
        item2 = runmod.row_to_item(fresh)
        transcript = ""
        if fresh["transcript_path"] and Path(fresh["transcript_path"]).exists():
            transcript = Path(fresh["transcript_path"]).read_text(encoding="utf-8")
        notes_status, note_path, fm = notes.write_note(item2, cfg, transcript)
        last_auto = {k: fm[k] for k in ("分类", "标签", "状态", "深挖")}
        db.set_fields(con, item["aweme_id"], note_path=str(note_path), last_auto=json.dumps(last_auto, ensure_ascii=False))
        done += 1

    rows = [runmod.row_to_item(r) for r in db.all_items(con)]
    pending = [it for it in rows if it["deep_state"] == "已转写"]
    out = Path(cfg["paths"]["db"]).parent / "待摘要清单.md"
    lines = ["# 待摘要清单", "", f"共 {len(pending)} 条（逐字稿已就绪，可让 Codex 批量写摘要）", ""]
    for it in pending:
        lines.append(f"- {it['title'] or it['aweme_id']} — {it['author_name']}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"\n深挖完成 {done}/{len(targets)} 条；待摘要清单: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
