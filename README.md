# 抖音收藏 → Obsidian 本地库

把抖音账号的「收藏 / 稍后再看 / 收藏夹」整理成本地 Obsidian 知识库的 **Codex 技能 + 完整工具**：
一条视频一篇笔记（本地封面、自动分类、全文可搜），标星条目可下载原片并用本机 GPU 生成逐字稿。

> 抖音官方收藏夹不能批量整理、稍后再看不能分类、视频里的内容更是完全搜不到。
> 这套工具把「收藏」从"再也想不起来"变成"随时搜得到"。

本仓库同时是两样东西：

- `skills/douyin-collection-obsidian/` —— **Codex 技能**：操作说明书，让 AI 会安装、运行、维护这套流程；
- 仓库根目录 —— **工具本体**：一键脚本 + 采集端（Edge CDP）+ 处理端（Python + SQLite），克隆后双击 `准备.cmd` 即用。

## 它能做什么

- **同步**：收藏（含收藏夹）+「稍后再看」全量抓取，一条视频一篇笔记；自动去重；
- **幂等**：同一份输入重复运行不会改动文件；抖音签名 URL 的轮换也不会造成重写；
- **分类**：`config/taxonomy.yml` 规则引擎（关键词 / 作者 / 优先级）；也可让 Codex 按真实数据聚类出分类草案；
- **检索**：Obsidian 全文搜索标题 / 作者 / 标签 / 分类 / 逐字稿；自带分类清单、待看清单、统计页，零插件依赖；
- **深挖**：标 `深挖: true` 的条目 → 下载原片（防下架；可配置为"只留逐字稿"）+ GPU 逐字稿写回笔记；
- **手写内容受保护**：笔记有手动区，脚本永不触碰；你改过的分类 / 标签 / 状态 / 深挖会被读回并保持；
- **低侵入**：抓取复用独立 Edge 配置的登录态（不碰日常浏览器），单线程 + 每页 2–5 秒随机间隔，手动触发。

## 工作原理

```
抖音网页版（专用 Edge 实例，复用登录态）
        │  CDP 捕获官方接口响应
        ▼
data\raw\<runid>\*.json ──► processor（Python + SQLite）
                              │  去重入库、状态流转、规则分类
                              │  封面下载压缩 → vault\attachments\covers
                              ▼
                    Obsidian vault：<你的库目录>\
                      ├─ 条目\作者-标题-<id8>.md   （一条一笔记，含手动区）
                      ├─ 分类\*.md / 待看清单.md / 未分类.md / 统计.md / 开始这里.md
                      └─ attachments\covers\*.webp

深挖：深挖.cmd → 直链下载原片 → ffmpeg 抽音频 → faster-whisper（GPU）
      → data\transcripts\<id8>.md → 回填笔记「逐字稿」区块
```

## 安装

### 1）装 Codex 技能（让 AI 会操作这套工具）

对 Codex 说：

> 从 GitHub 仓库 hitahara-66/douyin-collection-obsidian 安装 skills/douyin-collection-obsidian 技能

它会用 `skill-installer` 装到 `~/.codex/skills/douyin-collection-obsidian`，下一轮对话即可生效。
也可以手动把 `skills/douyin-collection-obsidian` 整个文件夹复制到：

- Windows：`%USERPROFILE%\.codex\skills\`
- macOS / Linux：`~/.codex/skills/`

### 2）装工具本体（首次使用）

```bat
gh repo clone hitahara-66/douyin-collection-obsidian
cd douyin-collection-obsidian
准备.cmd
```

依赖：Windows + Edge + Python 3.12+ + Node 20+ + ffmpeg（转写需在 PATH 中）；NVIDIA 显卡可选。
`准备.cmd` 会自动建 venv、装依赖、npm install，并首次生成 `config\settings.yml`
（默认输出到 `D:\Obsidian\抖音收藏`，按需修改 `vault_dir` / `media_dir`）。

### 3）登录 + 首次同步

```bat
登录抖音.cmd         :: 打开专用 Edge 扫码一次（独立配置目录，登录态只保存在本机）
同步.cmd             :: 全量抓取 + 生成笔记 / 封面 / 索引
同步.cmd --spike     :: 可选：页面结构探测，报告在 data\spike\M0-report.md
```

## 使用（每周约 10 分钟）

1. 双击 `同步.cmd`（自动抓收藏 + 稍后再看，更新队列状态）；
2. 浏览新增笔记，把想深挖的条目 frontmatter 改成 `深挖: true`；
3. （可选）双击 `深挖.cmd`，等它下载 + 转写。

### 命令速查

| 目标 | 命令 |
| --- | --- |
| 首次安装 / 修复依赖 | `准备.cmd` |
| 登录（首次或过期） | `登录抖音.cmd` |
| 同步 | `同步.cmd` |
| 只抓不写（调试） | `同步.cmd --dry-run` |
| 不抓取，重算最近数据 | `同步.cmd --skip-fetch` |
| 页面结构探测 | `同步.cmd --spike` |
| Edge 登录态检查 | `.\.venv\Scripts\python.exe -m processor.sync --status` |
| 深挖标星条目 | `深挖.cmd`（`--id <aweme_id>` 单条、`--refresh` 强制重跑） |
| 导出分类样本（给 Codex 聚类） | `.\.venv\Scripts\python.exe -m processor.run --export-samples` |
| 离线自检 | `cd fetcher && node test-capture.mjs`；`.\.venv\Scripts\python.exe -m processor.selfcheck` |

退出码：`0` 成功；`1` 出错；`2` 需要登录；`3` 调试端口未就绪。

## 分类体系

`config\taxonomy.yml` 按 `priority` 从高到低匹配 `keywords`（标题/标签）与 `authors`，未命中进入 `default`（默认"未分类"）。

推荐的数据驱动调优流程：

1. `processor.run --export-samples` 导出 `data\samples\samples.jsonl`；
2. 让 Codex 基于样本聚类出 8–12 个一级分类草案；
3. 定稿写回 `taxonomy.yml`，跑 `同步.cmd --skip-fetch` 生效。

你直接在笔记 frontmatter 里改的分类 / 标签 / 状态 / 深挖，会被脚本读回并优先于规则。

## 目录结构

```text
<仓库>\
├── LICENSE / README.md
├── 准备.cmd / 登录抖音.cmd / 同步.cmd / 深挖.cmd
├── config\ settings.example.yml（模板）· settings.yml（本地，不提交）· taxonomy.yml（分类规则）
├── fetcher\ Node 采集端（Edge CDP；含 spike / 直链刷新 / 自测）
├── processor\ Python 处理端（SQLite → 封面 → 笔记 / 索引；深挖转写；自检）
└── skills\douyin-collection-obsidian\   Codex 技能（SKILL.md + references）

运行期生成（不入库）：data\（原始 JSON / 数据库 / 逐字稿 / 日志 / 样本）、媒体目录、vault 输出
```

## 常见问题

- **提示需要登录**：双击 `登录抖音.cmd` 重新扫码，登录态一般能保持很久；
- **抓取异常 / 0 页**：先 `同步.cmd --spike`，把 `data\spike\M0-report.md` 交给 Codex 迭代；
- **转写报 `cublas64_12.dll is not found`**：重跑 `准备.cmd`（自动安装 CUDA 运行库）；
- **下载 403**：工具会自动用已登录 Edge 刷新签名直链；仍失败多为视频被删或受限；
- 更多见 [故障排查](skills/douyin-collection-obsidian/references/troubleshooting.md)。

## 文档

- 技能说明（AI 操作手册）：[SKILL.md](skills/douyin-collection-obsidian/SKILL.md)
- [安装与配置](skills/douyin-collection-obsidian/references/setup.md)
- [日常操作](skills/douyin-collection-obsidian/references/operations.md)
- [故障排查](skills/douyin-collection-obsidian/references/troubleshooting.md)
- [架构与数据契约](skills/douyin-collection-obsidian/references/architecture.md)

## 数据与隐私

- 所有数据（登录态、原始 JSON、数据库、原片、逐字稿）都在本机，不上传任何服务器；
- 仓库不包含任何个人数据：`data\`、`config\settings.yml`、`.venv\`、`node_modules\` 均已排除；
- `data\edge-cookies.txt`（若导出）含登录态，请勿分享或提交；
- 抓取频率保守（手动触发 + 随机延时）；请遵守抖音相关条款，下载与转写内容版权归原作者，建议仅作个人整理与学习用途。

## 更新与卸载

- 更新：`git pull` → 重跑 `准备.cmd`；技能按同样方式重新安装 / 覆盖；
- 卸载工具：删除 `.venv\`、`node_modules\` 即可停用；`data\`、媒体目录与 vault 是用户数据，按需保留。

## 许可证

MIT License，详见 [LICENSE](LICENSE)。
