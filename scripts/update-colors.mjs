import fs from 'node:fs';
const FILE = 'artists.json';
const artists = JSON.parse(fs.readFileSync(FILE, 'utf8'));
const sleep = ms => new Promise(r => setTimeout(r, ms));

function findColor(node) {
  if (!node || typeof node !== 'object') return null;
  if (node.extractedColors) {
    const c = node.extractedColors;
    return (c.colorRaw || c.colorDark || c.colorLight || {}).hex || null;
  }
  for (const v of Object.values(node)) { const r = findColor(v); if (r) return r; }
  return null;
}
async function fetchColor(id) {
  const res = await fetch(`https://open.spotify.com/embed/playlist/${id}`, { headers: { 'user-agent': 'Mozilla/5.0' } });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  const m = (await res.text()).match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  if (!m) throw new Error('__NEXT_DATA__なし');
  return findColor(JSON.parse(m[1]));
}

let changed = 0, failed = 0, same = 0, noId = 0, locked = 0, noColor = 0;
console.log('対象件数:', artists.length);
for (const a of artists) {
  const url = a.url || a.link || '';
  const id = (url.match(/playlist\/([A-Za-z0-9]+)/) || [])[1];
  if (a.colorLock) { locked++; continue; }
  if (!id) { noId++; if (noId <= 3) console.log('URLなし/形式違い:', a.name, '→', url || '(空)'); continue; }
  try {
    const hex = await fetchColor(id);
    if (!hex) { noColor++; if (noColor <= 3) console.log('色が見つからない:', a.name); }
    else if (!/^#[0-9a-f]{6}$/i.test(hex)) { noColor++; console.log('色の形式が想定外:', a.name, hex); }
    else if (hex.toLowerCase() === (a.color || '').toLowerCase()) { same++; }
    else { console.log(a.name, a.color, '->', hex); a.color = hex.toLowerCase(); changed++; }
  } catch (e) { failed++; console.warn(a.name, e.message); }
  await sleep(300);
}
console.log(`結果: 変更${changed} / 同じ色${same} / 色なし${noColor} / URL不正${noId} / ロック${locked} / 失敗${failed}`);
if (failed > artists.length * 0.3) { console.error('失敗が多いため書き込みません'); process.exit(1); }
if (changed) fs.writeFileSync(FILE, JSON.stringify(artists, null, 2) + '\n');
