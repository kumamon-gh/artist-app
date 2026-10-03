import fs from 'node:fs';
import sharp from 'sharp';

const FILE = 'artists.json';
const artists = JSON.parse(fs.readFileSync(FILE, 'utf8'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const hex2 = n => n.toString(16).padStart(2, '0');
const THRESHOLD = 6; // これ以下のずれは書き換えない

function parseHex(h) {
  const m = /^#?([0-9a-f]{6})$/i.exec(h || '');
  if (!m) return null;
  const v = parseInt(m[1], 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

async function dominantColor(imageUrl) {
  const res = await fetch(imageUrl);
  if (!res.ok) throw new Error('画像HTTP ' + res.status);
  const buf = Buffer.from(await res.arrayBuffer());
  const { data, info } = await sharp(buf).resize(64, 64, { fit: 'cover' }).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  const bins = new Map();
  for (let i = 0; i < data.length; i += info.channels) {
    const r = data[i], g = data[i + 1], b = data[i + 2];
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const sat = max === 0 ? 0 : (max - min) / max;
    if (max < 40 || min > 235 || sat < 0.2) continue;
    const key = (r >> 5) + ',' + (g >> 5) + ',' + (b >> 5);
    const e = bins.get(key) || { n: 0, r: 0, g: 0, b: 0 };
    e.n++; e.r += r; e.g += g; e.b += b;
    bins.set(key, e);
  }
  let best = null;
  for (const e of bins.values()) if (!best || e.n > best.n) best = e;
  if (!best) return null;
  return '#' + hex2(Math.round(best.r / best.n)) + hex2(Math.round(best.g / best.n)) + hex2(Math.round(best.b / best.n));
}

const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

async function fetchJson(url, tries = 3) {
  let last;
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return await res.json();
    } catch (e) { last = e; await sleep(1000 * (i + 1)); }
  }
  throw last;
}

let changed = 0, same = 0, failed = 0, skipped = 0;
for (const a of artists) {
  const url = a.url || a.link || '';
  if (!url || a.colorLock) { skipped++; continue; }
  try {
    const j = await fetchJson('https://open.spotify.com/oembed?url=' + encodeURIComponent(url));
    if (!j.thumbnail_url) throw new Error('画像URLなし');
    const calc = await dominantColor(j.thumbnail_url);
    if (!calc) { skipped++; continue; }
    const cur = parseHex(a.color);
    if (cur && dist(cur, parseHex(calc)) <= THRESHOLD) { same++; }
    else { console.log(a.name, a.color, '->', calc); a.color = calc; changed++; }
  } catch (e) { failed++; console.warn(a.name, e.message); }
  await sleep(300);
}
console.log(`結果: 変更${changed} / ほぼ同じ${same} / 対象外${skipped} / 失敗${failed}`);
if (failed > artists.length * 0.3) { console.error('失敗が多いため書き込みません'); process.exit(1); }
if (changed) fs.writeFileSync(FILE, JSON.stringify(artists, null, 2) + '\n');
