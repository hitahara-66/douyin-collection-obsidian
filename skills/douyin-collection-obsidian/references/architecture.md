# 架构与数据契约

## 总览

```
抖音网页版（专用 Edge 实例，复用登录态）
        │  CDP 捕获官方接口响应
        ▼
data\raw\<runid>\*.json ──► processor（Python + SQLite）
                              │  去重入库、状态流转、规则分类
                              │  封面下载压缩 → vault\attachments\covers
                              ▼
                    Obsidian vault\<库目录>\
                      ├─ 条目\YYYY-MM-DD 作者-标题-<id8>.md  （一条一笔记，按发布日期排序）
                      ├─ 分类\*.md / 待看清单.md / 未分类.md / 统计.md / 开始这里.md
                      └─ attachments\covers\*.webp

深挖链路：深挖.cmd → 直链下载原片（media_dir）→ ffmpeg 抽音频 → faster-whisper 转写
          → data\transcripts\<id8>.md → 回填笔记「逐字稿」区块
```

## 组件

| 组件 | 位置 | 职责 |
| --- | --- | --- |
| 采集端 | `fetcher\`（Node 24 + puppeteer-core） | 启动/连接专用 Edge，滚动抓取并保存接口原始 JSON；`spike.mjs` 做页面结构探测；`fetch-item-detail.mjs` 刷新签名直链 |
| 处理端 | `processor\`（Python 3.12） | 解析原始数据 → SQLite → 封面 → 笔记 / 索引；`deepdive.py` 深挖转写；`selfcheck.py` 离线自检 |
| 入口脚本 | 根目录 4 个 `.cmd` | 准备 / 登录 / 同步 / 深挖（双击友好，末尾 pause） |
| 配置 | `config\settings.yml`（本地，不提交）、`config\taxonomy.yml` | 路径、端口、频控、封面规格、深挖策略、分类规则 |

## 抖音接口（网页端）

| 数据 | 接口 | 备注 |
| --- | --- | --- |
| 全量收藏 | `/aweme/v1/web/aweme/listcollection/` | 分页 10 条；`has_more=0` 表示到底 |
| 收藏夹列表 | `/aweme/v1/web/collects/list/` | `total_number=0` 表示没有收藏夹 |
| 收藏夹内容 | `/aweme/v1/web/collects/video/list/` | 按 `collects_id` |
| 稍后再看 | `/aweme/v1/web/watchlater/list/` | `items` 数组；`has_more` 是**布尔值**；`list_num` 含失效条目（`invalid_item_ids`） |

实现要点：

- 请求签名（a_bogus 等）由页面自己完成——工具不去伪造签名，而是驱动真实页面并捕获其接口响应；
- 收藏接口只给发布时间、不给「收藏时间」，所以排序与统计统一用 `首次入库时间`（`first_seen_at`）；
- 封面 / 分享链接 / 直链带随机签名参数，每次抓取都不同：变更检测忽略这些字段，笔记里只保留去掉跟踪参数的稳定分享链接。

## 下载（深挖）

1. 优先用最近 3 次抓取原始 JSON 里的 `video.play_addr*` 直链（带签名，几小时内有效）；
2. 失效（403/410）时用已登录 Edge 打开视频页，捕获 `/aweme/v1/web/aweme/detail/` 响应刷新直链（`fetcher\fetch-item-detail.mjs`）；
3. 用 requests 流式下载（UA + Referer），图集类按 `images[]` 逐张下载；
4. yt-dlp 仅作为历史参考，抖音网页详情接口需要签名，yt-dlp 直连会 403，不作为主路径。

## 数据库（`data\library.db`）

`items` 主要字段：

| 字段 | 说明 |
| --- | --- |
| `aweme_id` | 主键（视频 / 图文唯一 ID） |
| `title / author_name / url / share_url / published_at / duration_sec` | 元数据 |
| `cover_url / cover_path` | 封面（下载签名 URL / 本地 webp 路径） |
| `in_favorites / in_watch_later / in_bridge / folders` | 来源归属（收藏 / 稍后再看 / 桥接收藏夹 / 收藏夹列表） |
| `source` | 展示用来源（如「稍后再看、收藏」） |
| `status / status_override` | 状态及其用户覆盖 |
| `category / category_override` | 分类及其用户覆盖 |
| `tags / tags_override` | 自动标签（来自话题 hashtag）及其用户覆盖 |
| `starred / starred_override` | 深挖标星及其用户覆盖 |
| `deep_state / transcript_path` | 深挖进度（已转写 / 已下载 / 已存图）与逐字稿路径 |
| `note_path / last_auto` | 笔记路径；上次写入的自动字段快照（用于读回用户编辑） |
| `first_seen_at / last_seen_at` | 首次入库 / 最近出现时间 |

`runs` 表记录每次处理的统计与原始数据目录。

## 笔记契约与覆盖机制

- 每个条目生成 `条目\YYYY-MM-DD 作者-标题-<id8>.md`（按发布日期排序），文件名自动剔除 `# ^ [ ]` 等 Obsidian 链接特殊字符（标题原文保留在 frontmatter）：frontmatter（固定 11 个字段）+ 自动正文（封面、元数据、可折叠逐字稿）+ 分界线 + 手动区；旧式命名可用 `python -m processor.reorder --apply` 一次性对齐（只改名，不改内容）；
- 索引页与封面使用 Obsidian 最短路径链接（`[[文件名|标题]]`、`![[<id8>.webp]]`）：`抖音收藏` 放在 vault 的任意层级都能正确跳转，不会跳错或新建空笔记；
- 每次处理前先「读回」用户对 `分类 / 标签 / 状态 / 深挖` 的修改（与 `last_auto` 快照比对），写入对应 `*_override` 列，之后自动值不再覆盖；
- 自动区内容由数据库生成：同一输入重复运行 → 文件字节级不变（幂等）；手动区原样保留。

## 状态流转

- 新条目：在「稍后再看」或桥接收藏夹 → `待看`；否则 `未标记`；
- 从队列消失（**仅当该来源抓取完整**）→ `已离开待看队列`；重新出现 → 回到 `待看`；
- 用户手改状态后，自动流转对该条不再生效。

## 测试与自检

- `fetcher\test-capture.mjs`：本地模拟服务器 + 无头 Edge，验证「滚动 → 捕获 → 到底判定」机制（5 项断言）；
- `processor\selfcheck.py`：纯离线端到端（26 项断言），覆盖导入、分类、封面、幂等、用户覆盖、队列流转、dry-run、frontmatter 契约。
