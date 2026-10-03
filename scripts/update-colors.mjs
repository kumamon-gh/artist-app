import fs from 'node:fs';
const artists = JSON.parse(fs.readFileSync('artists.json', 'utf8'));
for (const name of ['AI', 'IVE', 'I WiSH']) {
  const a = artists.find(x => x.name === name);
  if (!a) { console.log(name, ': artists.jsonに無い'); continue; }
  const url = a.url || a.link || '';
  try {
    const res = await fetch('https://open.spotify.com/oembed?url=' + encodeURIComponent(url));
    const j = await res.json();
    console.log(name, '| HTTP', res.status, '| 現在の色', a.color, '| 画像', j.thumbnail_url, '|', j.thumbnail_width + 'x' + j.thumbnail_height);
  } catch (e) { console.log(name, '失敗:', e.message); }
}
