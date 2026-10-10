---
name: douyin-collection-obsidian
description: 把抖音「收藏 / 稍后再看 / 收藏夹」整理成本地 Obsidian 知识库：抓取元数据与封面、自动分类、增量同步，以及对标星条目下载原片并用本机 GPU 生成逐字稿。当用户提到「抖音收藏整理 / 稍后再看导出 / 抖音转 Obsidian / 深挖转写 / 同步抖音收藏」，或需要安装、维护、排查这套工具（未登录、抓取失败、转写报错、调整分类）时使用。
metadata:
  short-description: 抖音收藏 → Obsidian 本地库（自动分类 + GPU 逐字稿）
---

# 抖音收藏 → Obsidian 本地库

把抖音账号的收藏整理成本地 Obsidian 库的完整工具与操作方法：一条视频一篇笔记（封面本地化、规则分类、可全文检索）；标星（`深挖: true`）的条目额外下载原片并做 GPU 逐字稿。工具本体随本仓库分发（仓库根目录含 `同步.cmd` 等一键脚本）。

## 第一步：定位工具根目录

工具根目录 = 包含 `同步.cmd` 的目录。按顺序查找：

1. 若本技能随仓库分发/克隆（技能目录向上两级或同层能找到 `同步.cmd`），那就是仓库根；
2. 否则在用户目录里限深度搜索：
   ```powershell
   Get-ChildItem $HOME -Recurse -Depth 4 -Filter '同步.cmd' -ErrorAction SilentlyContinue | Select-Object -First 5 -ExpandProperty FullName
   ```
3. 仍找不到 → 询问用户是否有既有安装；没有则克隆并初始化：
   `gh repo clone hitahara-66/douyin-collection-obsidian` → 进入该目录运行 `准备.cmd`。

开始操作前先读 `config\settings.yml`：`vault_dir` / `media_dir` 决定产物位置，向用户汇报时要用这里的真实路径。

## 环境要求

- Windows + Edge（唯一浏览器依赖；工具用独立配置目录，不干扰用户日常浏览器）
- Python 3.12+、Node 20+、ffmpeg（在 PATH 中）
- 深挖转写（可选）：NVIDIA 显卡。约 6GB 显存可跑 large-v3（int8），更小自动降级 medium / CPU；模型约 3GB，缓存于 `%USERPROFILE%\.cache\huggingface`（保留，重建成本高）

## 常用操作（在工具根目录执行）

| 目标 | 命令 |
| --- | --- |
| 首次安装 / 修复依赖 | `准备.cmd` |
| 登录（首次或过期） | `登录抖音.cmd` |
| 同步（每周一次） | `同步.cmd` |
| 只抓不写（调试） | `同步.cmd --dry-run` |
| 重新处理最近一次抓取 | `同步.cmd --skip-fetch` |
| 页面结构探测（M0） | `同步.cmd --spike` → 报告在 `data\spike\M0-report.md` |
| Edge 登录态检查 | `.\.venv\Scripts\python.exe -m processor.sync --status` |
| 深挖（下载 + 转写标星条目） | `深挖.cmd`（单条 `--id <aweme_id>`；强制重跑 `--refresh`） |
| 注册每周自动同步（计划任务） | `powershell -NoProfile -ExecutionPolicy Bypass -File "skills\douyin-collection-obsidian\scripts\register-scheduled-task.ps1"`（默认周三/周日 19:30；`-Remove` 移除） |
| 导出分类样本 | `.\.venv\Scripts\python.exe -m processor.run --export-samples` |
| 重整条目文件名（按发布日期对齐） | `.\.venv\Scripts\python.exe -m processor.reorder`（预览；确认后加 `--apply`） |
| 自检（无需登录） | `cd fetcher; node test-capture.mjs`；`.\.venv\Scripts\python.exe -m processor.selfcheck` |

退出码：`0` 成功；`1` 出错（看 `data\logs\`）；`2` 需要登录（先跑 `登录抖音.cmd`）；`3` 调试端口/登录态未就绪。脚本末尾带 `pause`（双击友好）；自动化场景用 `cmd /c ".\\同步.cmd <nul"`。

## 操作纪律

- **手动区不可动**：笔记里 `<!-- 自动生成结束 · 以下为手动区，脚本不会修改 -->` 以下为用户手写内容，只能改分界线以上的自动区。
- **同步幂等**：同一份原始数据重复处理不会改动文件；不要把生成文件手工挪走（笔记可改名/移动，脚本按 frontmatter 的 `aweme_id` 认领）。
- **抓取不完整时**（输出出现 ⚠ 或 manifest 里 `partial=true`）：已跳过「离开待看队列」判定，不要据此改状态，重跑同步再说。
- **尊重用户覆盖**：用户改过的 `分类 / 标签 / 状态 / 深挖` 会被读回并保持；`taxonomy.yml` 改动只影响未覆盖条目。
- **不要清理运行数据**：`data\`、媒体目录、HF 模型缓存都不要删除，除非用户明确要求。
- **库路径必须真实存在**：`config\settings.yml` 的 `vault_dir` 指向的库被移动/改名后，同步会中止报错而不是另建空库；改配置指向现有库即可恢复。
- **频控与账号安全**：单线程、每页随机 2–5 秒；不要并发跑多个同步/深挖；`data\edge-cookies.txt` 含登录态，绝不外传或提交。

## 参考文档

- 安装、配置、登录、验证：[references/setup.md](references/setup.md)
- 日常操作、分类体系、深挖与摘要、状态语义：[references/operations.md](references/operations.md)
- 故障排查（未登录 / 403 / cublas / 显存 / 镜像）：[references/troubleshooting.md](references/troubleshooting.md)
- 架构与数据契约（目录、数据库、frontmatter、接口）：[references/architecture.md](references/architecture.md)
