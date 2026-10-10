import fs from 'node:fs';
import path from 'node:path';
import { ensureDir, sleepRandom } from './util.mjs';

export function normalizeHasMore(value) {
  if (value === false) return 0;
  if (value === true) return 1;
  if (typeof value === 'string') {
    const s = value.trim().toLowerCase();
    if (s === '' || s === 'false' || s === '0') return 0;
    if (s === 'true' || s === '1') return 1;
  }
  return value;
}

export function findHasMore(json, depth = 0) {
  if (!json || typeof json !== 'object' || depth > 6) return null;
  if (Object.prototype.hasOwnProperty.call(json, 'has_more')) return normalizeHasMore(json.has_more);
  for (const value of Object.values(json)) {
    if (value && typeof value === 'object') {
      const found = findHasMore(value, depth + 1);
      if (found !== null) return found;
    }
  }
  return null;
}

export class CaptureSink {
  constructor({ outDir, matcher, kind, log = console.log }) {
    this.outDir = outDir;
    this.matcher = matcher;
    this.kindOf = typeof kind === 'function' ? kind : () => kind;
    this.log = log;
    this.captures = [];
    this.lastHasMore = null;
    this.errors = [];
    this.bodyErrors = 0;
  }

  attach(page) {
    page.on('response', (response) => {
      void this.handle(response);
    });
  }

  async handle(response) {
    const url = response.url();
    if (!this.matcher.test(url)) return;
    try {
      const body = await response.text();
      let json = null;
      try {
        json = JSON.parse(body);
      } catch {
        json = null;
      }
      const base = this.kindOf(url, json);
      ensureDir(this.outDir);
      const seq = String(this.captures.length + 1).padStart(4, '0');
      const file = path.join(this.outDir, `${base}.${seq}.json`);
      fs.writeFileSync(file, body, 'utf8');
      this.lastHasMore = json ? findHasMore(json) : null;
      this.captures.push({ url, file, seq, hasMore: this.lastHasMore, bytes: body.length, json });
      this.log(`  ↳ 捕获 ${base} 第 ${this.captures.length} 页（${body.length} 字节）`);
    } catch (err) {
      // 请求被取消/预检等场景读不到 body 属正常现象，只计数不刷屏
      this.bodyErrors += 1;
    }
  }
}

export async function scrollAll(page) {
  await page.mouse.wheel({ deltaY: 900 }).catch(() => {});
  return page
    .evaluate(() => {
      let atBottom = true;
      const elements = [document.scrollingElement, ...document.querySelectorAll('div')].filter(Boolean);
      for (const el of elements) {
        let style;
        try {
          style = getComputedStyle(el);
        } catch {
          continue;
        }
        if (!/(auto|scroll)/.test(style.overflowY || '')) continue;
        const max = el.scrollHeight - el.clientHeight;
        if (max <= 120) continue;
        const step = Math.max(300, Math.floor(el.clientHeight * 0.9));
        if (el.scrollTop < max - 4) el.scrollTop = Math.min(el.scrollTop + step, max);
        if (el.scrollTop < max - 4) atBottom = false;
        try {
          el.dispatchEvent(new Event('scroll'));
        } catch {
          // ignore
        }
      }
      const doc = document.scrollingElement || document.documentElement;
      const wmax = doc.scrollHeight - doc.clientHeight;
      if (wmax > 120) {
        const step = Math.max(300, Math.floor(window.innerHeight * 0.9));
        if (window.scrollY < wmax - 4) window.scrollTo(0, Math.min(window.scrollY + step, wmax));
        if (window.scrollY < wmax - 4) atBottom = false;
        try {
          window.dispatchEvent(new Event('scroll'));
        } catch {
          // ignore
        }
      }
      return { atBottom };
    })
    .catch(() => ({ atBottom: false }));
}

export async function autoScroll(page, { sink, delayMin, delayMax, maxIdle, maxScrolls, log = console.log }) {
  let idle = 0;
  let stall = 0;
  let lastCount = sink.captures.length;
  for (let i = 0; i < maxScrolls; i++) {
    const { atBottom } = await scrollAll(page);
    await sleepRandom(delayMin, delayMax);
    const now = sink.captures.length;
    const gotNew = now > lastCount;
    if (gotNew) {
      idle = 0;
      stall = 0;
    } else {
      stall += 1;
      if (atBottom) idle += 1;
    }
    lastCount = now;
    if (sink.lastHasMore === 0) {
      log(`  ✓ 已到达列表末尾（has_more=0，共 ${now} 页）`);
      return { exhausted: true, reason: 'has_more=0', pages: now };
    }
    if (idle >= maxIdle) {
      log(`  ⚠ 已滚动到底，连续 ${idle} 次没有新数据（共 ${now} 页）`);
      return { exhausted: false, reason: 'idle', pages: now };
    }
    if (stall >= maxIdle * 4) {
      log(`  ⚠ 连续 ${stall} 次滚动没有任何新数据，提前停止（共 ${now} 页，可能页面结构变化）`);
      return { exhausted: false, reason: 'stalled', pages: now };
    }
    if ((i + 1) % 10 === 0) log(`  … 已滚动 ${i + 1} 次，捕获 ${now} 页`);
  }
  log(`  ⚠ 达到滚动次数上限（${maxScrolls}），共捕获 ${sink.captures.length} 页`);
  return { exhausted: false, reason: 'max-scrolls', pages: sink.captures.length };
}
