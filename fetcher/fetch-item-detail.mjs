// 用已登录的 Edge 打开视频页，捕获官方 detail 接口里带签名的播放地址。
// 用途：深挖时原始抓取数据里的直链已过期（返回 403）时，刷新一份新的地址。
import path from 'node:path';
import { loadConfig } from './lib/config.mjs';
import { connectBrowser, ensureEdge } from './lib/edge.mjs';
import { ensureDir, log, sleep, writeJson } from './lib/util.mjs';

function getArg(name) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : null;
}

const awemeId = getArg('--id');
const outFile = getArg('--out');
if (!awemeId || !outFile) {
  console.error('用法: node fetch-item-detail.mjs --id <aweme_id> --out <文件>');
  process.exit(1);
}

const cfg = loadConfig(getArg('--settings') || undefined);
await ensureEdge(cfg, { headless: false, log });
const browser = await connectBrowser(cfg.edge.port, log);
const page = await browser.newPage();
await page.bringToFront().catch(() => {});

let detail = null;
page.on('response', (res) => {
  if (detail) return;
  const url = res.url();
  if (!/\/aweme\/v1\/web\/aweme\/detail\//.test(url)) return;
  res
    .json()
    .then((data) => {
      detail = data;
    })
    .catch(() => {});
});

await page.goto(`https://www.douyin.com/video/${awemeId}`, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
for (let i = 0; i < 24 && !detail; i++) await sleep(500);
await page.close().catch(() => {});

if (!detail) {
  browser.disconnect();
  console.error('[错误] 未能捕获 aweme detail 接口（页面结构变化或未登录）');
  process.exit(2);
}

const d = detail.aweme_detail || detail.aweme || detail;
const video = d.video || {};
const videos = [];
const push = (node) => {
  for (const u of (node && node.url_list) || []) {
    if (typeof u === 'string' && u.startsWith('http')) videos.push(u);
  }
};
for (const key of ['play_addr_h264', 'play_addr', 'play_addr_265', 'download_addr']) push(video[key]);
for (const br of video.bit_rate || []) push(br.play_addr);
function pushImages(node) {
  for (const u of (node && node.url_list) || []) {
    if (typeof u === 'string' && u.startsWith('http')) images.push(u);
  }
}
const images = [];
for (const img of d.images || []) pushImages(img);

ensureDir(path.dirname(outFile));
writeJson(outFile, {
  aweme_id: awemeId,
  captured_at: Date.now(),
  videos: [...new Set(videos)],
  images: [...new Set(images)],
});
console.log(`[完成] detail 捕获成功：${[...new Set(videos)].length} 个视频地址 / ${[...new Set(images)].length} 个图片地址`);
browser.disconnect();
