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
  if (!m) throw new Error('no data');
  return findColor(JSON.parse(m[1]));
}

let changed = 0, failed = 0;
for (const a of artists) {
  const id = ((a.url || a.link || '').match(/playlist\/([A-Za-z0-9]+)/) || [])[1];
  if (!id || a.colorLock) continue;           // colorLock:true を付けた人は手動色を維持
  try {
    const hex = await fetchColor(id);
    if (hex && /^#[0-9a-f]{6}$/i.test(hex) && hex.toLowerCase() !== (a.color || '').toLowerCase()) {
      console.log(a.name, a.color, '->', hex);
      a.color = hex.toLowerCase(); changed++;
    }
  } catch (e) { failed++; console.warn(a.name, e.message); }
  await sleep(300);
}
if (failed > artists.length * 0.3) { console.error('失敗が多いため書き込みません'); process.exit(1); }
if (changed) fs.writeFileSync(FILE, JSON.stringify(artists, null, 2) + '\n');
