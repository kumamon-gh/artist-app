import fs from 'node:fs';
const artists = JSON.parse(fs.readFileSync('artists.json', 'utf8'));
const a = artists.find(x => x.name === 'AI') || artists[0];
const id = (a.url.match(/playlist\/([A-Za-z0-9]+)/) || [])[1];
console.log('対象:', a.name, id);

const res = await fetch(`https://open.spotify.com/embed/playlist/${id}`, { headers: { 'user-agent': 'Mozilla/5.0' } });
const html = await res.text();
console.log('HTTP', res.status, '/ HTML長さ', html.length);

const m = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
if (!m) { console.log('__NEXT_DATA__なし。先頭:', html.slice(0, 300)); process.exit(0); }
const data = JSON.parse(m[1]);

const hits = [];
(function walk(n, path) {
  if (!n || typeof n !== 'object') return;
  for (const [k, v] of Object.entries(n)) {
    const p = path + '.' + k;
    if (typeof v === 'string' && /^#[0-9a-f]{6}$/i.test(v)) hits.push(p + ' = ' + v);
    else if (/color/i.test(k)) hits.push(p + ' -> ' + JSON.stringify(v).slice(0, 120));
    walk(v, p);
  }
})(data, 'root');
console.log('色に関係しそうな項目:', hits.length);
hits.slice(0, 30).forEach(h => console.log(h));
