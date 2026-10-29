// 各アーティストの「THIS IS」プレイリストのジャケット画像から代表色を取り出し、
// artists.json の color（1つ目のプレイリスト）と extra_colors（2つ目以降・URLごと）を更新する。
// colors.yml（scripts/update-colors.mjs）から毎日実行される。
// colorLock を付けたアーティストは、手動で決めた色を守るため（color・extra_colors とも）対象外。
import fs from 'node:fs';
import sharp from 'sharp';

const FILE = 'artists.json';
const artists = JSON.parse(fs.readFileSync(FILE, 'utf8'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const hex2 = n => n.toString(16).padStart(2, '0');
const THRESHOLD = 6; // 色の距離がこれ以下なら「ほぼ同じ」として書き換えない（毎日の微小な差分コミットを防ぐ）

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
  // 64x64 に縮小して画素数を減らす（計算を軽くし、細かいノイズも均す）
  const { data, info } = await sharp(buf).resize(64, 64, { fit: 'cover' }).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  const bins = new Map();
  for (let i = 0; i < data.length; i += info.channels) {
    const r = data[i], g = data[i + 1], b = data[i + 2];
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const sat = max === 0 ? 0 : (max - min) / max;
    // 黒っぽい・白っぽい・彩度の低い画素は、アクセントカラーに向かないため数えない
    if (max < 40 || min > 235 || sat < 0.2) continue;
    // 各チャンネル上位3bit（8段階）に丸めて集計し、似た色を同じ箱にまとめる
    const key = (r >> 5) + ',' + (g >> 5) + ',' + (b >> 5);
    const e = bins.get(key) || { n: 0, r: 0, g: 0, b: 0 };
    e.n++; e.r += r; e.g += g; e.b += b;
    bins.set(key, e);
  }
  // 画素数が最も多い箱を選び、その箱の平均色を返す
  let best = null;
  for (const e of bins.values()) if (!best || e.n > best.n) best = e;
  if (!best) return null;
  return '#' + hex2(Math.round(best.r / best.n)) + hex2(Math.round(best.g / best.n)) + hex2(Math.round(best.b / best.n));
}

const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

// 一時的な通信エラーに備え、待ち時間を延ばしながら最大 tries 回まで取得し直す
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

const isSpotifyPlaylist = u => typeof u === 'string' && /^https:\/\/open\.spotify\.com\/playlist\/[A-Za-z0-9]+/.test(u);

// プレイリストURLから代表色を求める（oEmbed でジャケット画像のURLを得る。認証不要）
async function colorOf(url) {
  const j = await fetchJson('https://open.spotify.com/oembed?url=' + encodeURIComponent(url));
  if (!j.thumbnail_url) throw new Error('画像URLなし');
  return await dominantColor(j.thumbnail_url);
}

// afterKey の直後に key を置く（無ければ末尾）。artists.json のキー順を normalize_artists.py と揃えて、無駄な差分を出さない
function setAfter(obj, afterKey, key, value) {
  if (key in obj) { obj[key] = value; return; }
  const entries = Object.entries(obj);
  for (const k of Object.keys(obj)) delete obj[k];
  let placed = false;
  for (const [k, v] of entries) {
    obj[k] = v;
    if (k === afterKey) { obj[key] = value; placed = true; }
  }
  if (!placed) obj[key] = value;
}

let changed = 0, extraChanged = 0, same = 0, failed = 0, skipped = 0;
for (const a of artists) {
  if (a.colorLock) { skipped++; continue; }

  // 1つ目のプレイリスト → color
  const url = a.url || a.link || '';
  if (url) {
    try {
      const calc = await colorOf(url);
      if (!calc) {
        skipped++;
      } else {
        const cur = parseHex(a.color);
        if (cur && dist(cur, parseHex(calc)) <= THRESHOLD) { same++; }
        else { console.log(a.name, a.color, '->', calc); a.color = calc; changed++; }
      }
    } catch (e) { failed++; console.warn(a.name, e.message); }
    await sleep(300); // 連続アクセスで制限されないよう間隔を空ける
  } else {
    skipped++;
  }

  // 2つ目以降のプレイリスト → extra_colors（URLごと）
  const extras = Array.isArray(a.extra_urls) ? a.extra_urls.filter(isSpotifyPlaylist) : [];
  if (extras.length === 0) {
    if (a.extra_colors !== undefined) { delete a.extra_colors; extraChanged++; }
    continue;
  }
  const map = (a.extra_colors && typeof a.extra_colors === 'object' && !Array.isArray(a.extra_colors)) ? { ...a.extra_colors } : {};
  let mapChanged = false;
  for (const u of extras) {
    try {
      const calc = await colorOf(u);
      if (calc) {
        const cur = parseHex(map[u]);
        if (cur && dist(cur, parseHex(calc)) <= THRESHOLD) { same++; }
        else { console.log(a.name, u, map[u], '->', calc); map[u] = calc; mapChanged = true; }
      }
    } catch (e) { failed++; console.warn(a.name, u, e.message); }
    await sleep(300);
  }
  // extra_urls から無くなったURLの色は取り除く
  for (const k of Object.keys(map)) {
    if (!extras.includes(k)) { delete map[k]; mapChanged = true; }
  }
  if (mapChanged) { setAfter(a, 'extra_urls', 'extra_colors', map); extraChanged++; }
}
console.log(`結果: 変更${changed} / 2つ目以降の変更${extraChanged} / ほぼ同じ${same} / 対象外${skipped} / 失敗${failed}`);
// 失敗が多い時は、Spotify側の障害などで色が部分的にしか更新されていない可能性があるため書き込まない
if (failed > artists.length * 0.3) { console.error('失敗が多いため書き込みません'); process.exit(1); }
if (changed || extraChanged) fs.writeFileSync(FILE, JSON.stringify(artists, null, 2) + '\n');
