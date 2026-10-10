import { loadConfig } from './lib/config.mjs';
import { cdpInfo, connectBrowser, ensureEdge } from './lib/edge.mjs';
import { DOUYIN_HOME } from './lib/douyin.mjs';

const cfg = loadConfig();
const args = process.argv.slice(2);
const headless = args.includes('--headless');

if (args.includes('--status')) {
  const info = await cdpInfo(cfg.edge.port);
  if (info) {
    console.log(`CDP 就绪: ${info.Browser || 'Edge'} @ 127.0.0.1:${cfg.edge.port}`);
    process.exit(0);
  }
  console.log('CDP 未就绪：专用 Edge 没在运行。双击「登录抖音.cmd」即可启动。');
  process.exit(3);
}

const login = args.includes('--login');
try {
  await ensureEdge(cfg, { headless, openUrl: login && !headless ? DOUYIN_HOME : 'about:blank' });
} catch (err) {
  console.error(`[错误] ${err.message}`);
  process.exit(1);
}

if (login && !headless) {
  try {
    const browser = await connectBrowser(cfg.edge.port);
    const pages = await browser.pages();
    let target = pages.find((p) => p.url().startsWith('https://www.douyin.com'));
    if (!target) {
      target = await browser.newPage();
      await target.goto(DOUYIN_HOME, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
    }
    await target.bringToFront().catch(() => {});
    browser.disconnect();
  } catch (err) {
    console.error(`[警告] 打开抖音页面失败: ${err.message}`);
  }
  console.log('');
  console.log('已打开专用 Edge 窗口（与你的日常浏览器互不影响）。');
  console.log('请在这个窗口里用抖音 App 扫码登录。登录成功后：');
  console.log('  1) 关掉这个提示窗口即可，Edge 保持开着；');
  console.log('  2) 双击「同步.cmd」开始第一次全量抓取。');
  console.log('以后每次同步前不用重新登录，登录态会一直保存在专用配置里。');
}
