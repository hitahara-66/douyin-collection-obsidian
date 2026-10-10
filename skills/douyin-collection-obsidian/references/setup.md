# 安装与配置

## 前置条件

| 依赖 | 要求 | 检查命令 |
| --- | --- | --- |
| Windows | 10/11（工具为 Windows 批处理 + PowerShell 环境设计） | — |
| Edge | 已安装（抓取复用其登录态） | `Get-Command msedge` 或看默认安装路径 |
| Python | 3.12+（3.13 亦可） | `python --version` |
| Node.js | 20+ | `node --version` |
| ffmpeg | 在 PATH 中（转写前提取音频用） | `ffmpeg -version` |
| NVIDIA 显卡（可选） | 约 6GB 显存跑 large-v3；更小自动降级 | `nvidia-smi` |

## 安装步骤

1. 克隆仓库并进入根目录（根目录应有 `同步.cmd`、`fetcher\`、`processor\`）：

   ```bat
   gh repo clone hitahara-66/douyin-collection-obsidian
   cd douyin-collection-obsidian
   ```

2. 双击 `准备.cmd`（或命令行运行）。它会：
   - 创建 Python 虚拟环境 `.venv\`；
   - 安装核心依赖（PyYAML / Pillow / requests）与深挖依赖（yt-dlp / faster-whisper / PyAV<19 / CUDA 运行库 `nvidia-cublas-cu12`、`nvidia-cudnn-cu12`）；
   - 安装 `fetcher\` 的 Node 依赖（puppeteer-core / yaml）；
   - 首次自动把 `config\settings.example.yml` 复制为 `config\settings.yml`；
   - pip 默认走清华镜像（设置环境变量 `PIP_INDEX_URL` 可覆盖）。

3. 按需修改 `config\settings.yml`（见下节）。至少确认 `vault_dir` 与 `media_dir`。

4. 双击 `登录抖音.cmd`：会打开一个**专用 Edge 窗口**（独立配置目录，与日常浏览器互不影响），用抖音 App 扫码登录一次。登录态保存在 `%LOCALAPPDATA%\douyin-library\edge-profile`，后续无需重复登录。

5. 双击 `同步.cmd` 首次全量同步。建议同时跑一次 `同步.cmd --spike` 生成 `data\spike\M0-report.md`，记录收藏 / 收藏夹 / 稍后再看三个接口的捕获情况与页面结构探测结果。

## 配置项（config\settings.yml）

| 键 | 说明 | 默认 |
| --- | --- | --- |
| `vault_dir` | Obsidian 库输出目录（vault 内的独立子目录） | 示例值需修改 |
| `media_dir` | 深挖原片 / 图集存放目录 | 示例值需修改 |
| `edge.executable` | Edge 路径，留空自动探测 | `""` |
| `edge.port` | 专用调试端口 | `9333` |
| `edge.profile_dir` | 专用浏览器配置目录（保存登录态） | `%LOCALAPPDATA%\douyin-library\edge-profile` |
| `capture.delay_min_sec` / `delay_max_sec` | 每页随机等待区间（秒） | `2` / `5` |
| `capture.max_idle_scrolls` | 连续无新数据的滚动次数（判到底） | `5` |
| `capture.max_scrolls` | 单次抓取滚动硬上限 | `400` |
| `covers.width` / `max_bytes` | 封面压缩规格（webp） | `480` / `61440` |
| `deepdive.keep_video` | `true` 保留原片；`false` 转写后自动删片只留逐字稿 | `true` |
| `lists.watch_later_bridge_folder` | 备用桥接收藏夹名（仅当稍后再看抓取失败时启用） | `稍后再看·留存` |
| `paths.*` | 分类规则、SQLite、原始数据、日志、探测报告的位置 | 见示例文件 |

## 验证清单

- `登录抖音.cmd` 后：`.\.venv\Scripts\python.exe -m processor.sync --status` 输出 `CDP 就绪`；
- 首次同步输出类似：`[完成] 收藏 N 页 / 收藏夹 M 个 / 稍后再看: K 条`，随后是处理摘要（新增 / 更新 / 未分类 / 封面成败）;
- vault 中出现 `条目\`、`分类\`、`开始这里.md`、`待看清单.md`、`统计.md`；
- 离线自检：`cd fetcher; node test-capture.mjs`（5 项）与 `.\.venv\Scripts\python.exe -m processor.selfcheck`（26 项）全绿。

## 登录机制与安全

- 抓取不保存账号密码；只复用专用 Edge 配置里的登录态（Cookie）。
- `node fetcher\export-cookies.mjs` 可导出 `data\edge-cookies.txt`（Netscape 格式，含登录态）供 `深挖` 下载受限视频使用；**该文件绝不外传、绝不提交**。
- 登录过期时同步会以退出码 2 中止并提示重新扫码，不会静默失败。
- 专用浏览器窗口可以保留常开；关闭也不影响，下次抓取会自动拉起。

## 更新与卸载

- 更新工具：`git pull` 后重跑 `准备.cmd`（会补齐新依赖）。
- 卸载：删除 `.venv\`、`node_modules\` 即可停用；`data\`、媒体目录、vault 是用户数据，按需保留或自行清理。
