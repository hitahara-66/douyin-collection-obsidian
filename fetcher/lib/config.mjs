import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import YAML from 'yaml';

export const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

function expandEnvString(value) {
  if (typeof value !== 'string') return value;
  return value.replace(/%([^%]+)%/g, (whole, name) => {
    const v = process.env[name];
    return v === undefined ? whole : v;
  });
}

function deepExpand(value) {
  if (Array.isArray(value)) return value.map(deepExpand);
  if (value && typeof value === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(value)) out[k] = deepExpand(v);
    return out;
  }
  return expandEnvString(value);
}

export function loadConfig(settingsPath) {
  const file = settingsPath ? path.resolve(settingsPath) : path.join(repoRoot, 'config', 'settings.yml');
  const raw = YAML.parse(fs.readFileSync(file, 'utf8')) || {};
  const cfg = deepExpand(raw);
  cfg.repoRoot = repoRoot;
  cfg.settingsPath = file;
  cfg.edge = Object.assign(
    {
      executable: '',
      port: 9333,
      profile_dir: path.join(process.env.LOCALAPPDATA || repoRoot, 'douyin-library', 'edge-profile'),
    },
    cfg.edge,
  );
  cfg.capture = Object.assign(
    { delay_min_sec: 2, delay_max_sec: 5, max_idle_scrolls: 5, max_scrolls: 400, page_load_timeout_sec: 60 },
    cfg.capture,
  );
  cfg.covers = Object.assign({ width: 480, max_bytes: 61440, format: 'webp' }, cfg.covers);
  cfg.lists = Object.assign({ watch_later_bridge_folder: '稍后再看·留存' }, cfg.lists);
  const paths = Object.assign(
    { taxonomy: 'config/taxonomy.yml', db: 'data/library.db', raw: 'data/raw', logs: 'data/logs', spike: 'data/spike' },
    cfg.paths,
  );
  cfg.paths = {};
  for (const [k, v] of Object.entries(paths)) {
    cfg.paths[k] = path.isAbsolute(v) ? v : path.join(repoRoot, v);
  }
  for (const k of ['vault_dir', 'media_dir']) {
    if (cfg[k]) cfg[k] = path.resolve(String(cfg[k]));
  }
  return cfg;
}
