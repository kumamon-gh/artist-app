#!/usr/bin/env python3
"""artists.json を 採番 → 検証 → ruby順に並び替え → キー順統一 する。
単体実行: python normalize_artists.py [artists.json]
update_artists.py（毎日の自動更新）と normalize.yml（artists.json の push 時）から使われる。"""
import json
import re
import sys
import unicodedata
from pathlib import Path

# 保存時のキーの並び。ここに無いキーは、この並びの後ろに元の順で付く
KEY_ORDER = [
    "id", "name", "ruby", "kana", "romaji", "aliases", "url",
    "spotify_artist_id", "official_site", "description", "tags",
    "status", "added_date", "updated_date", "color",
]
ID_RE = re.compile(r"^artist-(\d+)$")
OLD_ID_RE = re.compile(r"^artist-[A-Za-z]+(\d+)$")  # artist-a181 → artist-181
SPOTIFY_RE = re.compile(r"^[A-Za-z0-9]{22}$")
RUBY_RE = re.compile(r"^[ぁ-ゖー]+$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _is_blank_id(s):
    # 新しく追加する行は、id を空欄か "artist-new" にしておけば自動で採番される
    return s in ("", "artist-new")


SMALL_KANA = {"ぁ": "あ", "ぃ": "い", "ぅ": "う", "ぇ": "え", "ぉ": "お", "っ": "つ",
              "ゃ": "や", "ゅ": "ゆ", "ょ": "よ", "ゎ": "わ", "ゕ": "か", "ゖ": "け"}


def sort_ruby(s):
    """アプリの cleanRubyOf と同じ：空白と長音を除き、カタカナ→ひらがな、ゔ→う"""
    s = re.sub(r"\s+", "", str(s or "")).replace("ー", "")
    out = []
    for ch in s:
        o = ord(ch)
        if 0x30A1 <= o <= 0x30F6:
            ch = chr(o - 0x60)
        out.append(ch)
    return "".join(out).replace("ゔ", "う")


def ruby_sort_key(s):
    """アプリの rubySortKey と同じ：読み → 濁点/半濁点 → 小書き文字 の順に比較。
    端末の照合順序(ICU)に依存せず、画面と同じ並びにするための規則。
    どちらかを変える時は、アプリ側(index.html のスクリプト)も必ず同じに変える"""
    p, v, sm = [], [], []
    for ch in unicodedata.normalize("NFD", sort_ruby(s)):
        if ch == "\u3099":  # 濁点 → 直前の文字の「濁点あり」印を 1 にする
            if v: v[-1] = "1"
            else: v.append("1")
            continue
        if ch == "\u309A":  # 半濁点 → 同じく 2
            if v: v[-1] = "2"
            else: v.append("2")
            continue
        small = SMALL_KANA.get(ch)
        p.append(small or ch)
        v.append("0")
        sm.append("1" if small else "0")
    return "".join(p), "".join(v), "".join(sm)


def normalize(data):
    """戻り値: (整形済みデータ, errors, warnings, infos)
    errors が1件でもあれば、呼び出し側は保存せずに中止する。
    warnings は表示するだけで保存は止めない"""
    errors, warnings, infos = [], [], []
    if not isinstance(data, list):
        return data, ["artists.json は配列(リスト)である必要があります"], warnings, infos
    for i, a in enumerate(data):
        if not isinstance(a, dict):
            return data, [f"{i + 1}番目の要素がオブジェクトではありません"], warnings, infos

    # 1) 旧形式ID(artist-a181)を数字だけへ。重複があれば中止
    ids = []
    for a in data:
        raw = str(a.get("id") or "").strip()
        m = OLD_ID_RE.match(raw)
        ids.append(f"artist-{int(m.group(1))}" if m else raw)
    seen = {}
    for a, new_id in zip(data, ids):
        if _is_blank_id(new_id):
            continue
        if new_id in seen:
            errors.append(f"id が重複しています: {new_id} ({seen[new_id]} / {a.get('name')})")
        else:
            seen[new_id] = a.get("name")
    if errors:
        return data, errors, warnings, infos

    # 2) 新規(idが空 / 未設定 / artist-new)に 最大番号+1 を採番。既存IDは変更しない
    #    （IDはお気に入り等の保存データから参照され得るため、一度付けたら変えない）
    nums = [int(ID_RE.match(i).group(1)) for i in ids if ID_RE.match(i)]
    nxt = (max(nums) if nums else 0) + 1
    for a, new_id in zip(data, ids):
        if _is_blank_id(new_id):
            new_id = f"artist-{nxt}"
            nxt += 1
            infos.append(f"採番: {a.get('name')} -> {new_id}")
        elif new_id != a.get("id"):
            infos.append(f"ID形式を変更: {a.get('id')} -> {new_id}")
        a["id"] = new_id

    # 3) 検証。壊れたデータをアプリに配信しないよう、致命的なもの(ID形式・name・Spotify ID)は
    #    errors、表示には影響しないもの(ruby・color の書式)は warnings にする
    seen_sp = {}
    for a in data:
        label = f"{a['id']} ({a.get('name')})"
        if not ID_RE.match(a["id"]):
            errors.append(f"{label}: id は artist-数字 の形式にしてください")
        if not isinstance(a.get("name"), str) or not a["name"].strip():
            errors.append(f"{label}: name が空です")
        if not RUBY_RE.match(str(a.get("ruby", ""))):
            warnings.append(f"{label}: ruby はひらがな(と長音ー)のみにしてください: {a.get('ruby')!r}")
        sp = a.get("spotify_artist_id")
        if isinstance(sp, str):
            sp = sp.strip() or None
        if sp is not None:
            if not (isinstance(sp, str) and SPOTIFY_RE.match(sp)):
                errors.append(f"{label}: spotify_artist_id は22文字の英数字です: {sp!r}")
            elif sp in seen_sp:
                errors.append(f"{label}: spotify_artist_id が {seen_sp[sp]} と重複しています")
            else:
                seen_sp[sp] = a.get("name")
        a["spotify_artist_id"] = sp
        if a.get("color") and not COLOR_RE.match(str(a["color"])):
            warnings.append(f"{label}: color は #RRGGBB 形式にしてください: {a['color']!r}")
    if errors:
        return data, errors, warnings, infos

    # 4) キー順を統一（差分が読みやすくなり、不要な更新も減る）
    def ordered(a):
        head = {k: a[k] for k in KEY_ORDER if k in a}
        tail = {k: v for k, v in a.items() if k not in head}
        return {**head, **tail}

    # 5) ruby順に並び替え（アプリの rubySortKey と同じ規則。同じ読みは name 順）
    data = [ordered(a) for a in data]
    data.sort(key=lambda a: (*ruby_sort_key(a.get("ruby", "")), str(a.get("name", ""))))
    return data, errors, warnings, infos


def dump_text(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "artists.json")
    original = path.read_text(encoding="utf-8")
    try:
        data = json.loads(original)
    except json.JSONDecodeError as e:
        sys.exit(f"JSONの書式エラー: {e}")
    data, errors, warnings, infos = normalize(data)
    for line in infos:
        print("INFO :", line)
    for line in warnings:
        print("WARN :", line)
    if errors:
        for line in errors:
            print("ERROR:", line)
        sys.exit("エラーがあるため保存しませんでした")
    out = dump_text(data)
    # 内容が同じなら書き込まない（余計なコミットを作らない）
    if out != original:
        path.write_text(out, encoding="utf-8")
        print(f"保存しました: {len(data)}件")
    else:
        print(f"変更なし: {len(data)}件")


if __name__ == "__main__":
    main()
