import datetime
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

try:
    import pykakasi
except ImportError:
    pykakasi = None
try:
    import alkana
except ImportError:
    alkana = None

WISHLIST = "wishlist.txt"
JSON_PATH = "artists.json"
TODAY = datetime.date.today().isoformat()
JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
THIS_IS_RE = re.compile(r"^\s*this\s+is\b[:：]?\s*(.+?)\s*$", re.I)


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[^a-z0-9\u3040-\u30ff\u4e00-\u9fff]", "", s)


def to_kata(s):
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)


def to_hira(s):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def playlist_id(url):
    m = re.search(r"playlist/([A-Za-z0-9]+)", url or "")
    return m.group(1) if m else None


def oembed_title(url):
    """Spotifyの公開情報からタイトルを取得(認証不要)。取得できなければ None"""
    try:
        api = "https://open.spotify.com/oembed?url=" + urllib.parse.quote(url, safe="")
        with urllib.request.urlopen(api, timeout=20) as r:
            return json.load(r).get("title")
    except Exception as e:
        print(f"  (タイトル取得できず: {e})")
        return None


def auto_reading(name):
    if JP_RE.search(name) and pykakasi:
        parts = pykakasi.kakasi().convert(name)
        ruby = "".join(p["hira"] for p in parts)
        romaji = re.sub(r"[^a-z0-9]", "", "".join(p["hepburn"] for p in parts).lower())
        return ruby, to_kata(ruby), romaji
    romaji = re.sub(r"[^a-z0-9]", "", name.lower())
    words = re.findall(r"[A-Za-z0-9]+", name)
    if alkana and words:
        kanas = [alkana.get_kana(w.lower()) for w in words]
        if all(kanas):
            kata = "".join(kanas)
            return to_hira(kata), kata, romaji
    return "", "", romaji


def reading_from_ruby(name, ruby):
    ruby = to_hira(re.sub(r"\s+", "", unicodedata.normalize("NFKC", ruby)))
    if not re.fullmatch(r"[ぁ-ゖー/]+", ruby):
        raise ValueError("読みはひらがな(またはカタカナ)で書いてください")
    if not JP_RE.search(name):
        romaji = re.sub(r"[^a-z0-9]", "", name.lower())
    else:
        first = ruby.split("/")[0]
        if pykakasi:
            parts = pykakasi.kakasi().convert(first)
            romaji = re.sub(r"[^a-z0-9]", "", "".join(p["hepburn"] for p in parts).lower())
        else:
            romaji = ""
    return ruby, to_kata(ruby), romaji


def parse(line):
    m = re.search(r"https?://\S+", line)
    url = m.group(0) if m else None
    head = (line[:m.start()] + line[m.end():]).strip() if m else line.strip()
    parts = [p.strip() for p in re.split(r"[|｜,，、\t]", head) if p.strip()]
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else ""), url


def main():
    if not os.path.exists(WISHLIST):
        print("wishlist.txt がありません。")
        return
    with open(WISHLIST, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        artists = json.load(f)

    ids = {playlist_id(a.get("url")) for a in artists}
    names = {norm(a.get("name")) for a in artists}
    keep, added = [], 0

    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            keep.append(line)
            continue
        name, ruby, url = parse(s)
        if not url:
            keep.append(line)  # URL未入力：まだ探していない行は残す
            continue
        pid = playlist_id(url)
        if not pid:
            print(f"【残す】Spotifyのプレイリストurlではありません: {s}")
            keep.append(line)
            continue
        if pid in ids:
            print(f"【登録済みのため削除】{s}")
            continue
        canon = f"https://open.spotify.com/playlist/{pid}"
        title = oembed_title(canon)
        m = THIS_IS_RE.match(title) if title else None
        if title and not m:
            print(f"【残す】「This Is」のプレイリストではありません({title}): {s}")
            keep.append(line)
            continue
        if not name:
            if not m:
                print(f"【残す】名前を取得できません。名前も書いてください: {s}")
                keep.append(line)
                continue
            name = m.group(1).strip()
        if norm(name) in names:
            print(f"【残す】同名のアーティストが別URLで登録済みです: {name}")
            keep.append(line)
            continue
        try:
            if ruby:
                r, k, ro = reading_from_ruby(name, ruby)
            else:
                r, k, ro = auto_reading(name)
        except ValueError as e:
            print(f"【残す】{e}: {s}")
            keep.append(line)
            continue
        artists.append({
            "id": f"artist-{pid}",
            "name": name,
            "ruby": r,
            "kana": k,
            "romaji": ro,
            "url": canon,
            "official_site": None,
            "description": f"{name}の代表曲をまとめた公式のプレイリスト「This Is {name}」",
            "tags": [],
            "status": "published",
            "added_date": TODAY,
            "updated_date": TODAY,
            "color": "",
        })
        ids.add(pid)
        names.add(norm(name))
        added += 1
        print(f"【追加】{name}（読み: {r or '自動生成できず→その他に表示'}）")

    if added:
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(artists, f, ensure_ascii=False, indent=2)
            f.write("\n")
    with open(WISHLIST, "w", encoding="utf-8") as f:
        f.write("\n".join(keep) + ("\n" if keep else ""))
    print(f"追加 {added} 件 / wishlist に残った行 {len([k for k in keep if k.strip() and not k.strip().startswith('#')])} 件")


if __name__ == "__main__":
    sys.exit(main())
