#!/usr/bin/env python3
"""artists.json を 採番 → 項目の補完 → 検証 → ruby順に並び替え → キー順統一 する。
単体実行: python normalize_artists.py [artists.json]
update_artists.py（自動更新）から使われる。"""
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
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


# ---------------------------------------------------------------------------
# ruby（ひらがな）から kana / romaji を作る
# ---------------------------------------------------------------------------
# 各かなの (ヘボン式, 訓令式)。違いのあるものだけを後で上書きする
_BASE = {}
for _c, _chars in {"": "あいうえお", "k": "かきくけこ", "s": "さしすせそ", "t": "たちつてと",
                   "n": "なにぬねの", "h": "はひふへほ", "m": "まみむめも", "r": "らりるれろ",
                   "g": "がぎぐげご", "z": "ざじずぜぞ", "d": "だぢづでど",
                   "b": "ばびぶべぼ", "p": "ぱぴぷぺぽ"}.items():
    for _ch, _v in zip(_chars, "aiueo"):
        _BASE[_ch] = (_c + _v, _c + _v)
_BASE.update({
    "し": ("shi", "si"), "ち": ("chi", "ti"), "つ": ("tsu", "tu"), "ふ": ("fu", "hu"),
    "じ": ("ji", "zi"), "ぢ": ("ji", "zi"), "づ": ("zu", "zu"),
    "や": ("ya", "ya"), "ゆ": ("yu", "yu"), "よ": ("yo", "yo"),
    "わ": ("wa", "wa"), "を": ("o", "o"), "ん": ("n", "n"), "ゔ": ("vu", "vu"),
})
_SMALL_Y = {"ゃ": "a", "ゅ": "u", "ょ": "o"}
_SMALL_V = {"ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o"}
_YOUON_BASE = set("きしちにひみりぎじぢびぴゔ")


def _combine(syl, vowel, small_y, kunrei):
    """拗音（きゃ・しゃ…）と小さい母音（ふぁ・てぃ…）を1音にまとめる"""
    if small_y:
        if not kunrei and syl in ("shi", "chi", "ji"):
            return syl[:-1] + vowel          # sha / cha / ja
        return syl[:-1] + "y" + vowel        # kya / sya(訓令式) など
    if syl == "u":
        return "w" + vowel                   # うぃ → wi
    return syl[:-1] + vowel


def _romaji(ruby, kunrei):
    s = re.sub(r"\s+", "", ruby)
    s = "".join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in s)
    idx = 1 if kunrei else 0
    out, geminate, i = [], False, 0
    while i < len(s):
        ch = s[i]
        if ch == "っ":
            geminate = True
            i += 1
            continue
        if ch == "ー":                       # 長音は直前の母音を重ねる（記号は残さない）
            if out:
                out.append(out[-1][-1])
            i += 1
            continue
        if ch not in _BASE:
            i += 1
            continue
        syl = _BASE[ch][idx]
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if nxt in _SMALL_Y and ch in _YOUON_BASE:
            syl = _combine(syl, _SMALL_Y[nxt], True, kunrei)
            i += 2
        elif nxt in _SMALL_V:
            syl = _combine(syl, _SMALL_V[nxt], False, kunrei)
            i += 2
        else:
            i += 1
        if geminate and syl[0] not in "aiueon":
            syl = ("t" if syl.startswith("ch") else syl[0]) + syl
        geminate = False
        out.append(syl)
    return "".join(out)


def romaji_variants(ruby):
    """[ヘボン式, 訓令式]。小文字の英数字のみ。同じ綴りなら1つにまとめる"""
    result = []
    for kunrei in (False, True):
        r = re.sub(r"[^a-z0-9]", "", _romaji(ruby, kunrei).lower())
        if r and r not in result:
            result.append(r)
    return result


def kana_of(ruby):
    """ひらがな → カタカナ。長音ー以外の記号・空白は除く"""
    out = []
    for ch in re.sub(r"\s+", "", str(ruby or "")):
        if 0x3041 <= ord(ch) <= 0x3096:
            ch = chr(ord(ch) + 0x60)
        if "\u30A1" <= ch <= "\u30FA" or ch == "ー":
            out.append(ch)
    return "".join(out)


def fill_defaults(a, today):
    """name と ruby から、空の項目だけを補う（既にある値は上書きしない）。
    補った項目名のリストを返す"""
    filled = []

    def put(key, val):
        a[key] = val
        filled.append(key)

    name = a.get("name").strip() if isinstance(a.get("name"), str) else ""
    ruby = a.get("ruby") if isinstance(a.get("ruby"), str) else ""
    ruby_ok = bool(RUBY_RE.match(ruby))

    if ruby_ok and not a.get("kana"):
        k = kana_of(ruby)
        if k:
            put("kana", k)
    if ruby_ok and not a.get("romaji"):
        r = romaji_variants(ruby)
        if r:
            put("romaji", r)
    if a.get("aliases") is None:
        put("aliases", [])
    if "url" not in a and "link" not in a:
        put("url", "")          # 空のまま。自動更新で公式プレイリストが見つかれば入る
    if "official_site" not in a:
        put("official_site", None)
    if name and not a.get("description"):
        put("description", f"{name}の代表曲をまとめた公式のプレイリスト「This Is {name}」")
    if a.get("tags") is None:
        put("tags", [])         # 区分タグは自動判定できないため手動で入れる
    if not a.get("status"):
        put("status", "published")
    if not a.get("added_date"):
        put("added_date", today)
    if not a.get("updated_date"):
        put("updated_date", a.get("added_date") or today)
    if "color" not in a:
        put("color", "")        # 色は update-colors.mjs が自動で入れる
    return filled


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

    # 2.5) 空の項目を補完し、Spotify の url は ? 以降（共有用の追跡パラメータ）を省略する
    today = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")  # 日本時間
    for a in data:
        filled = fill_defaults(a, today)
        if filled:
            infos.append(f"補完: {a.get('name')} -> {', '.join(filled)}")
        u = a.get("url")
        if isinstance(u, str) and "?" in u:
            a["url"] = u.split("?", 1)[0]

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
