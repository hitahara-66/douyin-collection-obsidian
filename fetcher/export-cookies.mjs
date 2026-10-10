import fs from 'node:fs';
import path from 'node:path';
import { loadConfig } from './lib/config.mjs';
import { connectBrowser, ensureEdge } from './lib/edge.mjs';
import { DOUYIN_HOME } from './lib/douyin.mjs';
import { ensureDir, log } from './lib/util.mjs';

const cfg = loadConfig();
await ensureEdge(cfg, { headless: false, log });
const browser = await connectBrowser(cfg.edge.port, log);
const page = await browser.newPage();
await page.goto(DOUYIN_HOME, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
const client = await page.createCDPSession();
const { cookies } = await client.send('Network.getAllCookies');
const douyinCookies = cookies.filter((c) => /douyin\.com$/i.test(c.domain.replace(/^\./, '')));
const lines = ['# Netscape HTTP Cookie File', '# 仅供本机降级方案使用，含登录凭据，请勿分享或提交到任何仓库！'];
for (const c of douyinCookies) {
  lines.push(
    [
      c.domain,
      c.domain.startsWith('.') ? 'TRUE' : 'FALSE',
      c.path,
      c.secure ? 'TRUE' : 'FALSE',
      Math.floor(c.expires > 0 ? c.expires : 0),
      c.name,
      c.value,
    ].join('\t'),
  );
}
const out = path.join(cfg.repoRoot, 'data', 'edge-cookies.txt');
ensureDir(path.dirname(out));
fs.writeFileSync(out, lines.join('\n'), 'utf8');
console.log(`已导出 ${douyinCookies.length} 个抖音 Cookie → ${out}`);
try {
  await client.detach();
} catch {
  // ignore
}
browser.disconnect();
