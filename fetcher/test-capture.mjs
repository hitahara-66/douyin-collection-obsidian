import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { CaptureSink, autoScroll } from './lib/capture.mjs';
import { loadConfig } from './lib/config.mjs';
import { connectBrowser, ensureEdge } from './lib/edge.mjs';

function check(name, ok, extra = '') {
  console.log(`${ok ? 'PASS' : 'FAIL'} - ${name}${extra ? `（${extra}）` : ''}`);
  if (!ok) process.exitCode = 1;
}

const html = `<!doctype html><html><head><meta charset="utf-8"><title>mock</title></head><body>
<div id="list" style="height:420px;overflow-y:auto;border:1px solid #ccc"><div style="height:2600px"></div></div>
<script>
let n = 0;
const el = () => document.getElementById('list');
async function loadNext() {
  if (n >= 3) return;
  n += 1;
  try {
    const data = await fetch('/api/page/' + n).then((r) => r.json());
    const filler = document.createElement('div');
    filler.style.height = '900px';
    filler.textContent = data.items.join(',');
    el().appendChild(filler);
  } catch (e) {}
}
setTimeout(loadNext, 200);
el().addEventListener('scroll', () => { if (el().scrollTop + el().clientHeight > el().scrollHeight - 60) loadNext(); });
</script></body></html>`;

const server = http.createServer((req, res) => {
  if (req.url === '/') {
    res.setHeader('content-type', 'text/html; charset=utf-8');
    res.end(html);
    return;
  }
  const match = req.url.match(/^\/api\/page\/(\d+)$/);
  if (match) {
    const n = Number(match[1]);
    res.setHeader('content-type', 'application/json');
    // 最后一页故意用布尔 false（真实 watchlater 接口就是这么返回的）
    res.end(JSON.stringify({ page: n, has_more: n < 3, items: [`item-${n}-a`, `item-${n}-b`] }));
    return;
  }
  res.statusCode = 404;
  res.end('not found');
});

await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const webPort = server.address().port;
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dylib-capture-out-'));
const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dylib-capture-profile-'));
const cfg = loadConfig();
cfg.edge.port = 9357;
cfg.edge.profile_dir = profileDir;

let browser = null;
try {
  await ensureEdge(cfg, { headless: true });
  browser = await connectBrowser(cfg.edge.port);
  const page = await browser.newPage();
  const sink = new CaptureSink({ outDir, matcher: /\/api\/page\//, kind: 'page' });
  sink.attach(page);
  await page.goto(`http://127.0.0.1:${webPort}/`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  const scroll = await autoScroll(page, { sink, delayMin: 0.15, delayMax: 0.3, maxIdle: 4, maxScrolls: 80 });
  const files = fs
    .readdirSync(outDir)
    .filter((f) => f.startsWith('page.'))
    .sort();
  check('捕获到 3 页数据', files.length === 3, `实际 ${files.length}`);
  const last = files.length ? JSON.parse(fs.readFileSync(path.join(outDir, files[files.length - 1]), 'utf8')) : null;
  check('最后一页 has_more=false（布尔）', last?.has_more === false);
  check('自动滚动判定到底', scroll.exhausted === true, scroll.reason);
  const items = files.flatMap((f) => JSON.parse(fs.readFileSync(path.join(outDir, f), 'utf8')).items || []);
  check('条目总数正确（6 条）', items.length === 6, `实际 ${items.length}`);
  check('没有采集错误', sink.errors.length === 0, sink.errors.join('; '));
} catch (err) {
  check('测试过程无异常', false, err.message);
} finally {
  if (browser) {
    try {
      await browser.close();
    } catch {
      // ignore
    }
  }
  server.close();
}

console.log(process.exitCode ? '\n测试失败' : '\n全部通过');
process.exit(process.exitCode || 0);
