import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { ensureDir, log as defaultLog, sleep } from './util.mjs';

export function findEdgeExecutable(configured, log = defaultLog) {
  if (configured) {
    if (fs.existsSync(configured)) return configured;
    throw new Error(`config/settings.yml 中配置的 Edge 路径不存在: ${configured}`);
  }
  const candidates = [
    process.env['ProgramFiles(x86)']
      ? path.join(process.env['ProgramFiles(x86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe')
      : null,
    process.env.ProgramFiles
      ? path.join(process.env.ProgramFiles, 'Microsoft', 'Edge', 'Application', 'msedge.exe')
      : null,
    process.env.LOCALAPPDATA
      ? path.join(process.env.LOCALAPPDATA, 'Microsoft', 'Edge', 'Application', 'msedge.exe')
      : null,
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  try {
    const out = execFileSync(
      'reg',
      ['query', 'HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\msedge.exe', '/ve'],
      { encoding: 'utf8' },
    );
    const match = out.match(/REG_SZ\s+(.+?\.exe)/);
    if (match && fs.existsSync(match[1].trim())) return match[1].trim();
  } catch {
    // 继续抛下面的错误
  }
  throw new Error('找不到 Edge（msedge.exe）。请在 config/settings.yml 的 edge.executable 里手动指定路径。');
}

export async function cdpInfo(port) {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/json/version`, { signal: AbortSignal.timeout(2500) });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function ensureEdge(cfg, { headless = false, openUrl = null, waitMs = 45000, log = defaultLog } = {}) {
  const exe = findEdgeExecutable(cfg.edge.executable, log);
  const existing = await cdpInfo(cfg.edge.port);
  if (existing) {
    log(`Edge 调试端口已就绪: 127.0.0.1:${cfg.edge.port}（${existing.Browser || '未知版本'}）`);
    return { launched: false, child: null, executable: exe, port: cfg.edge.port, info: existing };
  }
  ensureDir(cfg.edge.profile_dir);
  const args = [
    `--remote-debugging-port=${cfg.edge.port}`,
    `--user-data-dir=${cfg.edge.profile_dir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-session-crashed-bubble',
    ...(headless ? ['--headless=new', '--disable-gpu'] : []),
    ...(openUrl ? [openUrl] : ['about:blank']),
  ];
  log(`启动${headless ? '无头' : ''} Edge: ${exe}`);
  const child = spawn(exe, args, { detached: !headless, stdio: 'ignore' });
  if (!headless) child.unref();
  const deadline = Date.now() + waitMs;
  while (Date.now() < deadline) {
    await sleep(600);
    const info = await cdpInfo(cfg.edge.port);
    if (info) return { launched: true, child, executable: exe, port: cfg.edge.port, info };
  }
  throw new Error(
    'Edge 已启动但调试端口未就绪。可尝试：1) 手动关闭该专用 Edge 窗口后重试；2) 修改 config/settings.yml 里的 edge.port；3) 检查杀毒软件是否拦截。',
  );
}

export async function connectBrowser(port, log = defaultLog) {
  const puppeteer = await import('puppeteer-core');
  log(`连接 Edge CDP: 127.0.0.1:${port}`);
  return puppeteer.connect({ browserURL: `http://127.0.0.1:${port}`, defaultViewport: null });
}
