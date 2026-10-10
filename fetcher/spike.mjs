import fs from 'node:fs';
import path from 'node:path';
import { loadConfig } from './lib/config.mjs';
import { connectBrowser, ensureEdge } from './lib/edge.mjs';
import { captureDouyin } from './lib/douyin.mjs';
import { ensureDir, log, writeJson } from './lib/util.mjs';

const cfg = loadConfig();
const rawDir = path.join(cfg.paths.spike, 'raw');
ensureDir(rawDir);

let result;
try {
  const launch = await ensureEdge(cfg, { headless: false, log });
  const browser = await connectBrowser(cfg.edge.port, log);
  try {
    result = await captureDouyin({ browser, cfg, outDir: rawDir, log });
  } finally {
    try {
      browser.disconnect();
    } catch {
      // ignore
    }
    if (launch?.launched && launch.child) {
      // 保留窗口给用户继续操作，不主动关闭
    }
  }
} catch (err) {
  result = { fatal_error: err.message };
}

const lines = [];
lines.push('# M0 Spike 报告');
lines.push('');
lines.push(`- 时间：${new Date().toLocaleString('zh-CN')}`);
lines.push(`- 登录状态：${result.login_required ? '未登录（先跑 登录抖音.cmd 扫码）' : result.fatal_error ? '出错' : '已登录'}`);
if (result.collection) lines.push(`- 收藏列表页：${result.collection.url || '未打开'}`);
lines.push(`- 收藏接口捕获：${result.collection?.pages ?? 0} 页（完整到底：${result.favorites_complete ? '是' : '否'}）`);
lines.push(`- 收藏夹列表捕获：${result.collects_list?.pages ?? 0} 页；发现收藏夹 ${result.folders?.discovered?.length ?? 0} 个`);
for (const folder of result.folders?.results || []) {
  lines.push(`  - ${folder.name}：${folder.ok ? `已抓取 ${folder.pages} 页（${folder.reason}）` : `失败（${folder.reason}）`}`);
}
lines.push(`- 稍后再看探测：${result.watch_later?.verdict ?? 'unknown'}`);
if (result.watch_later?.found_in_pages?.length) lines.push(`  - 页面文本命中：${result.watch_later.found_in_pages.join(', ')}`);
if (result.watch_later?.candidate_endpoints?.length) lines.push(`  - 候选接口：${result.watch_later.candidate_endpoints.join(', ')}`);
if (result.endpoint_paths) {
  const interesting = result.endpoint_paths.filter((p) => /collect|watch|later|history/i.test(p));
  lines.push(`- 相关接口路径（共 ${interesting.length} 个）：`);
  for (const p of interesting.slice(0, 40)) lines.push(`  - ${p}`);
}
if (result.errors?.length) {
  lines.push('- 错误：');
  for (const e of result.errors) lines.push(`  - ${e}`);
}
lines.push('');
lines.push(`原始样本目录：${rawDir}`);

const report = lines.join('\n');
ensureDir(cfg.paths.spike);
fs.writeFileSync(path.join(cfg.paths.spike, 'M0-report.md'), report, 'utf8');
writeJson(path.join(cfg.paths.spike, 'spike-result.json'), result);
console.log(report);
console.log(`\n报告已写入: ${path.join(cfg.paths.spike, 'M0-report.md')}`);
process.exit(result.fatal_error ? 1 : 0);
