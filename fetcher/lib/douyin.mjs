import { CaptureSink, autoScroll } from './capture.mjs';
import { ensureDir, log as defaultLog, sleep } from './util.mjs';

export const DOUYIN_HOME = 'https://www.douyin.com/';

export const COLLECTION_TAB_URLS = [
  'https://www.douyin.com/user/self?showTab=collection',
  'https://www.douyin.com/user/self?showTab=favorite_collection',
  'https://www.douyin.com/user/self',
];

export const PATTERNS = {
  listcollection: /\/aweme\/v1\/web\/aweme\/listcollection\//,
  collectsList: /\/aweme\/v1\/web\/collects\/list\//,
  collectsVideo: /\/aweme\/v1\/web\/collects\/video\/list\//,
  watchlater: /\/aweme\/v1\/web\/watchlater\/list\//,
};

export async function isLoggedIn(page) {
  const client = await page.createCDPSession();
  try {
    const { cookies } = await client.send('Network.getAllCookies');
    return cookies.some((c) => c.name === 'sessionid' && c.value);
  } finally {
    try {
      await client.detach();
    } catch {
      // ignore
    }
  }
}

export async function clickByText(page, text) {
  return page
    .evaluate((needle) => {
      const all = [...document.querySelectorAll('a, [role="tab"], button, [data-e2e], span, div')];
      const matchText = (own) => own === needle || (own.startsWith(needle) && own.length <= needle.length + 10);
      const candidates = all.filter((el) => {
        const own = (el.textContent || '').trim();
        if (!matchText(own)) return false;
        if (el.children.length === 0) return true;
        return el.hasAttribute('data-e2e') || el.getAttribute('role') === 'tab';
      });
      if (!candidates.length) return false;
      const visible = (el) => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && r.top >= 0 && r.top < 800;
      };
      const el = candidates.find(visible) || candidates[0];
      el.scrollIntoView({ block: 'center' });
      el.click();
      return true;
    }, text)
    .catch(() => false);
}

export function collectFolderCandidates(json) {
  const found = [];
  const walk = (node, depth) => {
    if (!node || typeof node !== 'object' || depth > 8) return;
    if (Array.isArray(node)) {
      for (const item of node) walk(item, depth + 1);
      return;
    }
    const keys = Object.keys(node);
    const idKey = keys.find((k) => /^(collects?_?id|collect_id|folder_id)$/i.test(k));
    const nameKey = keys.find((k) => /(collects?_?name|collect_name|folder_name)$/i.test(k));
    if (idKey && nameKey && typeof node[nameKey] === 'string' && node[nameKey].trim()) {
      found.push({ id: String(node[idKey]), name: String(node[nameKey]).trim() });
    }
    for (const value of Object.values(node)) {
      if (value && typeof value === 'object') walk(value, depth + 1);
    }
  };
  walk(json, 0);
  const seen = new Set();
  return found.filter((f) => {
    const key = `${f.id}|${f.name}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export async function probeWatchLater(pages, endpointPaths) {
  const foundInPages = [];
  for (const page of pages) {
    try {
      const text = await page.evaluate(() => (document.body ? document.body.innerText : ''));
      if (text && text.includes('稍后再看')) foundInPages.push(page.url());
    } catch {
      // ignore
    }
  }
  const candidateEndpoints = [...endpointPaths].filter((p) => /watch|later|history/i.test(p));
  return {
    found_in_pages: foundInPages,
    candidate_endpoints: candidateEndpoints,
    verdict: foundInPages.length || candidateEndpoints.length ? 'found' : 'not_found',
  };
}

export async function captureDouyin({ browser, cfg, outDir, log = defaultLog }) {
  const startedAt = new Date().toISOString();
  const errors = [];
  const endpointPaths = new Set();
  ensureDir(outDir);

  const delay = cfg.capture;
  const sinks = {
    listcollection: new CaptureSink({ outDir, matcher: PATTERNS.listcollection, kind: 'listcollection', log }),
    collectsList: new CaptureSink({ outDir, matcher: PATTERNS.collectsList, kind: 'collects-list', log }),
    collectsVideo: new CaptureSink({
      outDir,
      matcher: PATTERNS.collectsVideo,
      kind: (url) => {
        let id = 'unknown';
        try {
          id = new URL(url).searchParams.get('collects_id') || 'unknown';
        } catch {
          // ignore
        }
        return `collects-video.${id}`;
      },
      log,
    }),
    watchlater: new CaptureSink({ outDir, matcher: PATTERNS.watchlater, kind: 'watchlater', log }),
  };

  const seenPages = new Set();
  const allPages = [];
  const attachPage = (page) => {
    if (!page || seenPages.has(page)) return;
    seenPages.add(page);
    allPages.push(page);
    for (const sink of Object.values(sinks)) sink.attach(page);
    page.on('response', (res) => {
      try {
        endpointPaths.add(new URL(res.url()).pathname);
      } catch {
        // ignore
      }
    });
    page.on('dialog', (dialog) => {
      void dialog.dismiss().catch(() => {});
    });
  };
  for (const p of await browser.pages()) attachPage(p);
  browser.on('targetcreated', (target) => {
    if (target.type() === 'page') {
      void target
        .page()
        .then((p) => attachPage(p))
        .catch(() => {});
    }
  });

  const page = await browser.newPage();
  await page.bringToFront().catch(() => {});
  const timeout = Math.max(15, Number(delay.page_load_timeout_sec) || 60) * 1000;

  log('打开抖音首页，检查登录状态 ...');
  await page
    .goto(DOUYIN_HOME, { waitUntil: 'domcontentloaded', timeout })
    .catch((e) => errors.push(`打开首页失败: ${e.message}`));
  await sleep(3000);
  if (!(await isLoggedIn(page))) {
    return {
      started_at: startedAt,
      ended_at: new Date().toISOString(),
      login_required: true,
      collection: { url: null, pages: 0, exhausted: false, reason: null },
      collects_list: { pages: 0 },
      folders: { discovered: [], results: [], complete: false },
      favorites_complete: false,
      watch_later: { verdict: 'unknown', found_in_pages: [], candidate_endpoints: [] },
      endpoint_paths: [...endpointPaths],
      sink_errors: [],
      errors: [...errors, '未登录：需要在专用 Edge 窗口里扫码登录抖音'],
      partial: true,
    };
  }

  log('登录正常，打开「收藏」列表 ...');
  let collectionUrl = null;
  for (const url of COLLECTION_TAB_URLS) {
    if (sinks.listcollection.captures.length) {
      collectionUrl = collectionUrl || page.url();
      break;
    }
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout });
    } catch (e) {
      errors.push(`打开 ${url} 失败: ${e.message}`);
      continue;
    }
    await sleep(3500);
    if (!sinks.listcollection.captures.length) {
      const clicked = await clickByText(page, '收藏');
      if (clicked) await sleep(3500);
    }
    if (sinks.listcollection.captures.length) {
      collectionUrl = page.url();
      break;
    }
  }

  let favoritesScroll = null;
  if (collectionUrl) {
    log('开始滚动抓取全量收藏 ...');
    favoritesScroll = await autoScroll(page, {
      sink: sinks.listcollection,
      delayMin: delay.delay_min_sec,
      delayMax: delay.delay_max_sec,
      maxIdle: delay.max_idle_scrolls,
      maxScrolls: delay.max_scrolls,
      log,
    });
  } else {
    errors.push('未能打开「收藏」列表页（可能是页面结构变化）。');
  }

  if (!sinks.collectsList.captures.length) {
    const clicked = await clickByText(page, '收藏夹');
    if (clicked) await sleep(3500);
  }
  const folders = [];
  for (const cap of sinks.collectsList.captures) {
    for (const folder of collectFolderCandidates(cap.json)) {
      if (!folders.some((x) => x.id === folder.id)) folders.push(folder);
    }
  }
  if (folders.length) {
    log(`发现 ${folders.length} 个收藏夹：${folders.map((f) => f.name).join('、')}`);
  } else {
    log('未捕获到收藏夹列表（可能没有收藏夹，或页面结构变化）。');
  }

  const folderResults = [];
  for (const folder of folders) {
    const before = sinks.collectsVideo.captures.length;
    try {
      await page.goto(COLLECTION_TAB_URLS[0], { waitUntil: 'domcontentloaded', timeout });
      await sleep(3000);
      const clicked = await clickByText(page, folder.name);
      if (!clicked) {
        folderResults.push({ id: folder.id, name: folder.name, ok: false, reason: 'click-failed', pages: 0, exhausted: false });
        continue;
      }
      await sleep(2500);
      log(`抓取收藏夹「${folder.name}」...`);
      const scroll = await autoScroll(page, {
        sink: sinks.collectsVideo,
        delayMin: delay.delay_min_sec,
        delayMax: delay.delay_max_sec,
        maxIdle: delay.max_idle_scrolls,
        maxScrolls: delay.max_scrolls,
        log,
      });
      const pages = sinks.collectsVideo.captures.length - before;
      if (!pages) errors.push(`收藏夹「${folder.name}」没有捕获到作品列表。`);
      folderResults.push({
        id: folder.id,
        name: folder.name,
        ok: pages > 0,
        reason: pages > 0 ? scroll.reason : 'no-capture',
        pages,
        exhausted: scroll.exhausted,
      });
    } catch (e) {
      errors.push(`收藏夹「${folder.name}」抓取失败: ${e.message}`);
      folderResults.push({ id: folder.id, name: folder.name, ok: false, reason: e.message, pages: 0, exhausted: false });
    }
  }

  const watchLater = await probeWatchLater(allPages, endpointPaths);
  const favoritesComplete = Boolean(favoritesScroll?.exhausted);
  const foldersComplete =
    folders.length > 0 ? folderResults.every((f) => f.ok && f.exhausted) : sinks.collectsList.captures.length > 0;

  log('打开「稍后再看」列表 ...');
  let watchLaterScroll = null;
  try {
    await page.goto('https://www.douyin.com/user/self?showTab=watch_later', { waitUntil: 'domcontentloaded', timeout });
    await sleep(3500);
    if (!sinks.watchlater.captures.length) {
      const clicked = await clickByText(page, '稍后再看');
      if (clicked) await sleep(3500);
    }
    if (sinks.watchlater.captures.length) {
      watchLaterScroll = await autoScroll(page, {
        sink: sinks.watchlater,
        delayMin: delay.delay_min_sec,
        delayMax: delay.delay_max_sec,
        maxIdle: delay.max_idle_scrolls,
        maxScrolls: delay.max_scrolls,
        log,
      });
    } else {
      errors.push('未能捕获「稍后再看」列表数据（可能页面结构变化）。');
    }
  } catch (e) {
    errors.push(`抓取「稍后再看」失败: ${e.message}`);
  }
  let watchLaterStats = { unique: 0, listNum: 0, invalid: 0 };
  if (sinks.watchlater.captures.length) {
    const uniq = new Set();
    const invalids = new Set();
    let listNum = 0;
    for (const cap of sinks.watchlater.captures) {
      const data = cap.json || {};
      const list = Array.isArray(data.items) ? data.items : Array.isArray(data.aweme_list) ? data.aweme_list : [];
      for (const it of list) {
        if (it && it.aweme_id) uniq.add(String(it.aweme_id));
      }
      for (const id of data.invalid_item_ids || []) invalids.add(String(id));
      if (typeof data.list_num === 'number') listNum = Math.max(listNum, data.list_num);
    }
    watchLaterStats = { unique: uniq.size, listNum, invalid: invalids.size };
  }
  const watchLaterComplete =
    Boolean(watchLaterScroll?.exhausted) ||
    (watchLaterStats.listNum > 0 && watchLaterStats.unique + watchLaterStats.invalid >= watchLaterStats.listNum);
  if (watchLaterStats.listNum > 0 && !watchLaterComplete) {
    errors.push(
      `「稍后再看」可能未抓全：捕获 ${watchLaterStats.unique} 条 / 标记总数 ${watchLaterStats.listNum}（含失效 ${watchLaterStats.invalid}）`,
    );
  }

  return {
    started_at: startedAt,
    ended_at: new Date().toISOString(),
    login_required: false,
    collection: {
      url: collectionUrl,
      pages: sinks.listcollection.captures.length,
      exhausted: Boolean(favoritesScroll?.exhausted),
      reason: favoritesScroll?.reason ?? null,
    },
    collects_list: { pages: sinks.collectsList.captures.length },
    folders: { discovered: folders, results: folderResults, complete: foldersComplete },
    favorites_complete: favoritesComplete,
    watch_later: {
      captured: sinks.watchlater.captures.length > 0,
      pages: sinks.watchlater.captures.length,
      exhausted: Boolean(watchLaterScroll?.exhausted),
      complete: watchLaterComplete,
      unique_items: watchLaterStats.unique,
      list_num: watchLaterStats.listNum,
      invalid_items: watchLaterStats.invalid,
      probe: watchLater,
    },
    endpoint_paths: [...endpointPaths],
    sink_errors: Object.values(sinks).flatMap((s) => s.errors),
    body_read_failures: Object.values(sinks).reduce((sum, s) => sum + s.bodyErrors, 0),
    errors,
    partial: !(favoritesComplete && foldersComplete),
  };
}
