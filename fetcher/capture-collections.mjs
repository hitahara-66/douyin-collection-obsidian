import path from 'node:path';
import { loadConfig } from './lib/config.mjs';
import { connectBrowser, ensureEdge } from './lib/edge.mjs';
import { captureDouyin } from './lib/douyin.mjs';
import { log, writeJson } from './lib/util.mjs';

function getArg(name) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : null;
}

const outArg = getArg('--out');
if (!outArg) {
  console.error('用法: node capture-collections.mjs --out <目录> [--headless] [--port N] [--settings 文件]');
  process.exit(1);
}
const outDir = path.resolve(outArg);
const cfg = loadConfig(getArg('--settings') || undefined);
const portArg = getArg('--port');
if (portArg) cfg.edge.port = Number(portArg);
const headless = process.argv.includes('--headless');

log(`采集输出目录: ${outDir}`);
let launch;
try {
  launch = await ensureEdge(cfg, { headless, log });
} catch (err) {
  console.error(`[错误] ${err.message}`);
  writeJson(path.join(outDir, 'manifest.json'), { fatal_error: err.message, ended_at: new Date().toISOString() });
  process.exit(1);
}

let browser;
try {
  browser = await connectBrowser(cfg.edge.port, log);
} catch (err) {
  console.error(`[错误] 无法连接 Edge CDP: ${err.message}`);
  process.exit(1);
}

let result;
try {
  result = await captureDouyin({ browser, cfg, outDir, log });
  writeJson(path.join(outDir, 'manifest.json'), result);
} catch (err) {
  result = { fatal_error: err.message, ended_at: new Date().toISOString() };
  writeJson(path.join(outDir, 'manifest.json'), result);
  console.error(`[错误] 采集失败: ${err.message}`);
} finally {
  if (headless && launch?.launched) {
    try {
      await browser.close();
    } catch {
      // ignore
    }
  } else {
    try {
      browser.disconnect();
    } catch {
      // ignore
    }
  }
}

if (result?.login_required) {
  console.error('[需要登录] 请先双击「登录抖音.cmd」扫码登录，然后重新同步。');
  process.exit(3);
}
if (result?.fatal_error) {
  process.exit(1);
}
console.log(
  `[完成] 收藏 ${result.collection?.pages || 0} 页 / 收藏夹 ${result.folders?.results?.length || 0} 个 / 稍后再看: ${
    result.watch_later?.captured
      ? `${result.watch_later.unique_items || result.watch_later.pages} 条${result.watch_later.complete ? '' : '（未确认到底）'}`
      : '未捕获'
  }${result.partial ? '（部分完成）' : ''}`,
);
process.exit(0);
