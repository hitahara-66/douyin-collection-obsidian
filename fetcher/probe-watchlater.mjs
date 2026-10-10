import path from 'node:path';
import { loadConfig } from './lib/config.mjs';
import { connectBrowser, ensureEdge } from './lib/edge.mjs';
import { ensureDir, log, sleep, writeJson } from './lib/util.mjs';

const cfg = loadConfig();
const outDir = path.join(cfg.paths.spike, 'watchlater');
ensureDir(outDir);

await ensureEdge(cfg, { headless: false, log });
const browser = await connectBrowser(cfg.edge.port, log);
const page = await browser.newPage();

const events = [];
page.on('response', (res) => {
  let p = '';
  try {
    p = new URL(res.url()).pathname;
  } catch {
    return;
  }
  if (/\/aweme\/v1\/web\//.test(p)) {
    const record = { t: Date.now(), path: p, url: res.url() };
    events.push(record);
    res
      .text()
      .then((body) => {
        record.bytes = body.length;
        const seq = String(events.filter((e) => e.path === p).length).padStart(3, '0');
        const file = path.join(outDir, `${p.replace(/[^a-z0-9]+/gi, '_')}.${seq}.json`);
        import('node:fs').then((fs) => fs.writeFileSync(file, body, 'utf8'));
        record.file = file;
      })
      .catch(() => {
        record.bytes = -1;
      });
  }
});

try {
  await page.goto('https://www.douyin.com/user/self?showTab=collection', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await sleep(4000);

  const dump = await page.evaluate(() => {
    const out = { matches: [], tabs: [] };
    for (const el of document.querySelectorAll('*')) {
      const own = (el.textContent || '').trim();
      if (own.includes('稍后再看') && own.length < 40 && el.children.length === 0) {
        const r = el.getBoundingClientRect();
        out.matches.push({
          tag: el.tagName,
          cls: el.className ? String(el.className).slice(0, 100) : '',
          e2e: el.getAttribute('data-e2e'),
          role: el.getAttribute('role'),
          text: own,
          top: Math.round(r.top),
          left: Math.round(r.left),
          html: el.outerHTML.slice(0, 400),
        });
      }
    }
    for (const el of document.querySelectorAll('[role="tab"], [data-e2e], a')) {
      const t = (el.textContent || '').trim();
      if (t && t.length < 30) {
        out.tabs.push({ tag: el.tagName, text: t, e2e: el.getAttribute('data-e2e'), href: el.getAttribute('href') });
      }
    }
    return out;
  });
  writeJson(path.join(outDir, 'dom.json'), dump);
  console.log('页面上含「稍后再看」的叶子元素：');
  for (const m of dump.matches) console.log(' ', JSON.stringify(m));

  const clickTime = Date.now();
  const clicked = await page.evaluate(() => {
    const els = [...document.querySelectorAll('*')];
    const el = els.find((e) => {
      const t = (e.textContent || '').trim();
      return t.includes('稍后再看') && (e.children.length === 0 || e.getAttribute('role') === 'tab');
    });
    if (!el) return false;
    el.scrollIntoView({ block: 'center' });
    el.click();
    return true;
  });
  await sleep(5000);
  const after = {
    clicked,
    url: page.url(),
    newEndpoints: events.filter((e) => e.t >= clickTime).map((e) => ({ path: e.path, bytes: e.bytes, file: e.file })),
  };
  writeJson(path.join(outDir, 'after-click.json'), after);
  console.log('');
  console.log('点击「稍后再看」结果: clicked =', clicked);
  console.log('点击后 URL:', after.url);
  console.log('点击后的新接口:');
  for (const e of after.newEndpoints) console.log(' ', e.path, e.bytes ?? '');
  const text = await page.evaluate(() => (document.body ? document.body.innerText.slice(0, 1200) : ''));
  console.log('');
  console.log('点击后页面文本前 1200 字:');
  console.log(text);
} finally {
  browser.disconnect();
}
