# 日常操作

## 每周流程（用户视角，约 10 分钟）

1. 双击 `同步.cmd`：抓取收藏 + 稍后再看 → 更新笔记 / 封面 / 索引；
2. 浏览新增笔记，把想深挖的条目 frontmatter 改成 `深挖: true`；
3. 双击 `深挖.cmd`：下载原片 + GPU 转写逐字稿写回笔记。

## 定时同步（Windows 计划任务）

让电脑每周自动跑两次，不需要打开 Codex：

```powershell
# 注册（默认每周三、周日 19:30）
powershell -NoProfile -ExecutionPolicy Bypass -File "skills\douyin-collection-obsidian\scripts\register-scheduled-task.ps1"
# 自定义时间（例：周三、周五 21:00）
powershell -NoProfile -ExecutionPolicy Bypass -File "skills\douyin-collection-obsidian\scripts\register-scheduled-task.ps1" -Days Wednesday,Friday -At 21:00
# 移除
powershell -NoProfile -ExecutionPolicy Bypass -File "skills\douyin-collection-obsidian\scripts\register-scheduled-task.ps1" -Remove
```

要点：

- 任务名 `DouyinToObsidian-Sync`，执行 `定时同步.cmd`（无 pause）；输出追加到 `data\logs\scheduled.log`；
- 登录 Windows 后才会运行（`Interactive`），勾选了「错过触发后尽快补跑」（`StartWhenAvailable`），电脑关机/休眠错过也会在开机后补上；
- 运行时会自动拉起专用 Edge 窗口（保持打开，可随手关掉）；登录过期时退出码为 2，会在日志与下一条记录中体现；
- 只做「同步」；深挖（下载原片 + 转写）仍按需手动运行，避免占用 GPU。

## 同步命令与输出解读

```bat
同步.cmd                :: 抓取 + 处理（全量扫描）
同步.cmd --dry-run      :: 只抓取和计算，不写入任何文件
同步.cmd --skip-fetch   :: 跳过抓取，用最近一次原始数据重新处理
同步.cmd --spike        :: M0 探测，输出 data\spike\M0-report.md
同步.cmd --status       :: 检查专用 Edge 调试端口
同步.cmd --login        :: 等同 登录抖音.cmd
```

摘要字段含义：

- **新增 / 更新 / 未变**：相对数据库的去重统计；「更新」只统计稳定字段（标题 / 作者 / 链接 / 发布时间 / 时长）的变化，签名 URL 的轮换不计入。
- **离开待看**：从「稍后再看」（或备用桥接收藏夹）消失的条目，状态自动改为 `已离开待看队列`；**仅当本次抓取完整时才会判定**，不完整时跳过。
- **未分类**：没有命中 `config\taxonomy.yml` 规则的条目数。
- **封面 成功/失败**、**笔记 写入/未变**：文件层面的落盘统计；第二次同样输入应为「未变」全量、写入 0。

退出码：`0` 成功；`1` 出错（细节在 `data\logs\run-*.md` 与控制台）；`2` 需要登录；`3` 调试端口未就绪。

## 分类体系

规则文件 `config\taxonomy.yml`：

```yaml
default: "未分类"
categories:
  - name: "AI技术与工具"
    priority: 100
    keywords: ["codex", "github", "教程"]
    authors: ["某作者"]
```

匹配逻辑：按 `priority` 从高到低逐条检查；标题或标签包含任一 `keyword`（不区分大小写），或作者命中 `authors`，即归入该类；全部未命中 → `default`。

推荐的分类调优流程（数据驱动，避免拍脑袋）：

1. 导出样本：`.\.venv\Scripts\python.exe -m processor.run --export-samples` → `data\samples\samples.jsonl`（最多 300 条，含标题 / 作者 / 标签 / 分类）；
2. 让 Codex 依据样本聚类出 8–12 个一级分类草案（附样例）；
3. 把定稿规则写入 `config\taxonomy.yml`，重跑 `同步.cmd --skip-fetch` 即可生效。

**用户覆盖优先**：单篇笔记的 frontmatter 被用户改过（分类 / 标签 / 状态 / 深挖）时，脚本读回并保持，不再自动覆盖；想恢复自动化就把该字段改回与脚本生成值一致或直接删除对应键。

## 深挖与转写

```bat
深挖.cmd                 :: 处理所有 深挖: true 且未转写的条目
深挖.cmd --id <aweme_id> :: 只处理某一条（无论是否已转写）
深挖.cmd --refresh       :: 已转写的也重新处理
```

流程：读回标星 → 下载原片（优先用最近抓取的签名直链；失效时用已登录 Edge 打开视频页刷新直链）→ ffmpeg 抽音频 → faster-whisper 转写（优先 `large-v3/cuda`，显存不足自动降级 `medium/cuda` → `medium/cpu`）→ 逐字稿写入 `data\transcripts\<id8>.md` 并回填到笔记的「逐字稿」折叠区块 → `deep_state` 更新为 `已转写`。

要点：

- `deepdive.keep_video: false` 时，转写成功后自动删除临时原片，只留逐字稿；
- 首次运行会下载模型（约 3GB，默认走 hf-mirror），之后离线可用；模型缓存在 `%USERPROFILE%\.cache\huggingface`，不要清理；
- 转写速度参考：RTX 4050 上约为实时的 6–7 倍（16 分钟视频约 3 分钟）；
- `data\待摘要清单.md` 会列出已转写条目——让 Codex 读 `data\transcripts\*.md` 生成摘要，写入对应笔记的手动区即可（脚本不会覆盖手动区）。

## 状态语义

| 状态 | 含义 |
| --- | --- |
| 待看 | 在「稍后再看」或备用桥接收藏夹中 |
| 已离开待看队列 | 已从队列消失（抓取完整时自动标记）；可在笔记里手改为 已看 / 弃看 |
| 未标记 | 普通收藏条目 |

## 笔记契约

frontmatter 字段（固定）：`标题 / 作者 / 链接 / 来源 / 分类 / 标签 / 状态 / 发布时间 / 首次入库 / 深挖 / aweme_id`。

- 文件名：`作者-标题-<id8>.md`，首次生成后不随标题变化（可自行改名，脚本按 `aweme_id` 认领）；
- 一键改 `深挖` / `状态` / `分类` / `标签` 即可，脚本下次运行读回；
- `<!-- 自动生成结束 · 以下为手动区，脚本不会修改 -->` 以下为手动区；分界线以上由脚本维护。

## 备份与维护

- 需要备份的是：vault（或至少 `抖音收藏\` 子目录）、`config\settings.yml`、`config\taxonomy.yml`；`data\` 里也有数据库与逐字稿，可按需保留。
- 想重新整理：`同步.cmd --skip-fetch` 可基于最近一次抓取重算分类 / 索引，不会重新抓取。
