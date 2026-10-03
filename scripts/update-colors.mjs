import fs from 'node:fs';
import sharp from 'sharp';

const artists = JSON.parse(fs.readFileSync('artists.json', 'utf8'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const hex2 = n => n.toString(16).padStart(2, '0');

function parseHex(h) {
  const m = /^#?([0-9a-f]{6})$/i.exec(h || '');
  if (!m) return null;
  const v = parseInt(m[1], 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

// 画像の代表色：暗すぎ/明るすぎ/くすみすぎの画素を除き、色相ごとに集計して最大グループの平均を返す
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

function distance(a, b) {
  return Math.round(Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]));
}

const rows = [];
let failed = 0, noUrl = 0;
for (const a of artists) {
  const url = a.url || a.link || '';
  if (!url) { noUrl++; continue; }
  try {
    const res = await fetch('https://open.spotify.com/oembed?url=' + encodeURIComponent(url));
    if (!res.ok) throw new Error('oEmbed HTTP ' + res.status);
    const j = await res.json();
    if (!j.thumbnail_url) throw new Error('画像URLなし');
    const calc = await dominantColor(j.thumbnail_url);
    const cur = parseHex(a.color), cal = parseHex(calc);
    if (!calc || !cur || !cal) { rows.push({ name: a.name, cur: a.color, calc: calc || '(算出不可)', d: -1 }); continue; }
    rows.push({ name: a.name, cur: a.color, calc, d: distance(cur, cal) });
  } catch (e) { failed++; console.warn(a.name, e.message); }
  await sleep(300);
}

const ok = rows.filter(r => r.d >= 0).sort((x, y) => y.d - x.d);
console.log('対象', artists.length, '/ 算出成功', ok.length, '/ 算出不可', rows.length - ok.length, '/ 失敗', failed, '/ URLなし', noUrl);
if (ok.length) {
  const ds = ok.map(r => r.d).sort((x, y) => x - y);
  console.log('ずれ(0=完全一致, 441=最大) 中央値', ds[Math.floor(ds.length / 2)], '/ 60以下', ds.filter(d => d <= 60).length + '件', '/ 120超', ds.filter(d => d > 120).length + '件');
  console.log('--- ずれの大きい順 上位30件（名前 | 今の色 | 算出色 | ずれ）---');
  ok.slice(0, 30).forEach(r => console.log(r.name, '|', r.cur, '|', r.calc, '|', r.d));
}
