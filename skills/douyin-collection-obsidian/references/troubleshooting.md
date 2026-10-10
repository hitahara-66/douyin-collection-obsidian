# 故障排查

## 同步相关

| 症状 | 处理 |
| --- | --- |
| `同步.cmd` 提示「需要登录」（退出码 2） | 双击 `登录抖音.cmd` 重新扫码；登录态一般能保持很久 |
| 调试端口起不来 / `--status` 报未就绪 | 关掉专用 Edge 窗口后重试；端口冲突就改 `config\settings.yml` 的 `edge.port`；检查安全软件拦截 |
| 抓取 0 页 / 结果异常少 | 先跑 `同步.cmd --spike`，把 `data\spike\M0-report.md` 发给 Codex 迭代（页面结构可能变化） |
| 出现验证码 / 风控提示 | 脚本会中止并保留上次数据；在专用 Edge 里手动处理，调大 `capture.delay_min_sec/delay_max_sec` 后重试 |
| 「稍后再看」没抓到 | 确认网页端收藏页仍能打开「稍后再看」；失败时启用备用方案：在 App 里建 `稍后再看·留存` 收藏夹，把想留的移进去（脚本按收藏夹抓取） |
| 摘要显示「抓取不完整」 | 本次跳过「离开待看」判定属预期行为；直接在稳定网络下重跑一次 |
| 收藏数量与 App 显示不一致 | 抖音接口会过滤失效 / 私密条目（返回 `invalid_item_count`），以接口返回为准 |

## 深挖 / 转写相关

| 症状 | 处理 |
| --- | --- |
| 下载 403 / 链接失效 | 工具会先用最近抓取的签名直链，再自动用已登录 Edge 刷新（`fetcher\fetch-item-detail.mjs`）；仍失败多为视频已删或受限，换条目即可 |
| 报 `cublas64_12.dll is not found` | 缺 CUDA 运行库：重跑 `准备.cmd`（安装 `nvidia-cublas-cu12` / `nvidia-cudnn-cu12`，代码会自动注册 DLL 路径） |
| 报 `open() got an unexpected keyword argument 'metadata_errors'` | PyAV 太新：`pip install "av<19"`（`requirements-deep.txt` 已锁定） |
| 模型下载慢 / 中断 | 默认走 hf-mirror（`HF_ENDPOINT`）；失败可重跑（huggingface_hub 支持断点续传），或设置其它镜像 |
| 显存不足 / 想更快 | 自动降级 `large-v3 → medium → CPU`；也可设置环境变量 `WHISPER_MODEL=medium`（或 small 等）后重跑，速度更快、精度略降 |
| ffmpeg 缺失 | 安装 ffmpeg 并确保在 PATH 中（`ffmpeg -version`） |
| 想只留逐字稿 | `config\settings.yml` 里 `deepdive.keep_video: false`，转写成功后自动删原片 |
| 想清掉模型缓存（约 4.4GB） | 删除 `%USERPROFILE%\.cache\huggingface\hub\models--Systran--faster-whisper-*`；下次深挖需重新下载，属用户明确要求才做 |
| 转写中途中断 | 直接重跑 `深挖.cmd`：已转写条目会跳过，未完成的会重试（原片仍在则复用） |

## 库 / 文件相关

| 症状 | 处理 |
| --- | --- |
| 提示「库目录不存在」/ 一跑同步就中止 | 库被移动或改名：把 `config\settings.yml` 的 `vault_dir` 改成现有库路径后重跑（脚本拒绝在别处另建空库）；想重建整库才删 `data\library.db` |
| 笔记被误改 / 想重生成 | 删除对应笔记后重跑 `同步.cmd --skip-fetch`；手动区内容会随文件一起丢失，先自行备份 |
| 文件名太长 / 特殊字符 | 命名已做清洗与截断；如遇系统级长路径限制，缩短 vault 路径 |
| 封面缺失 | 单条封面下载失败会在摘要计入「封面失败」；重跑同步会自动补 |
| `pause` 卡住自动化 | 双击场景保留；脚本场景用 `cmd /c ".\\同步.cmd <nul"` |
| 想看历史运行记录 | `data\logs\run-*.md`；数据库 `data\library.db` 的 `runs` 表 |

## 快速定位

- 最近一次抓取的原始数据：`data\raw\<时间戳>\`（`manifest.json` 记录了完整性、接口、错误）；
- 运行报告：`data\logs\`；
- 页面结构探测：`data\spike\`（含「稍后再看」接口探测结果 `watchlater\` 子目录）；
- 数据库速查：

  ```bat
  .\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data/library.db'); print(c.execute('select count(*) from items').fetchone())"
  ```
