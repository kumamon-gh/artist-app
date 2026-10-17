import json
import os
import re
import sys
import requests

from normalize_artists import normalize, dump_text

# GitHub Actions の Secrets から環境変数として渡される（update.yml 参照）
CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")

def get_spotify_token():
    url = "https://accounts.spotify.com/api/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    res = requests.post(url, headers=headers, data=data)
    if res.status_code == 200:
        return res.json().get("access_token")
    print(f"Token取得失敗: {res.status_code} - {res.text}")
    return None

def search_this_is_playlist(artist_info, token):
    name = artist_info.get("name", "").strip()
    romaji_raw = artist_info.get("romaji", "")
    
    # ローマ字候補を取得（例: "Aimyon" や "Ado"）。"/" 区切りで複数書ける
    romaji_list = [r.strip().lower() for r in romaji_raw.split('/') if r.strip()]
    
    search_url = "https://api.spotify.com/v1/search"
    # 日本語のプレイリスト名で検索結果が返るよう、言語を日本語優先にする
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ja;q=1.0, en;q=0.5"
    }
    
    # 日本語名 → ローマ字名の順に検索する（見つかった時点で返す）
    queries = [f"This Is {name}"]
    for r in romaji_list:
        queries.append(f"This Is {r}")

    for query in queries:
        # market=JP：日本で聴ける公式プレイリストに絞る
        params = {"q": query, "type": "playlist", "limit": 10, "market": "JP"}
        res = requests.get(search_url, headers=headers, params=params)
        if res.status_code != 200:
            continue

        data = res.json()
        playlists = data.get("playlists", {}).get("items", [])

        for pl in playlists:
            if not pl:
                continue
            
            owner_id = pl.get("owner", {}).get("id", "")
            pl_name = pl.get("name", "").strip().lower()

            # 他人が作った似た名前のプレイリストを除くため、
            # Spotify公式（owner_idがspotify）かつ "this is" を含むものだけを採用する
            if owner_id == "spotify" and "this is" in pl_name:
                # 別のアーティストのプレイリストを拾わないよう、
                # プレイリスト名に日本語名またはローマ字名が含まれることも確認する
                check_targets = [name.lower()] + romaji_list
                for target in check_targets:
                    if target and target in pl_name:
                        return pl.get("external_urls", {}).get("spotify")

    return None

def main():
    json_path = "artists.json"
    if not os.path.exists(json_path):
        print(f"{json_path} が見つかりません。")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        original_text = f.read()

    # 採番・検証・ruby順の並び替え。エラーがあれば、壊れたデータを保存・配信しないよう中止する
    artists, errors, warnings, infos = normalize(json.loads(original_text))
    for line in infos:
        print("INFO :", line)
    for line in warnings:
        print("WARN :", line)
    if errors:
        for line in errors:
            print("ERROR:", line)
        sys.exit("artists.json にエラーがあるため中止しました")

    token = get_spotify_token()
    if not token:
        # トークンが取れなくても、整形（採番・並び替え）の結果だけは下で保存する
        print("アクセストークンの取得に失敗したため、URL更新はスキップします。")

    updated_count = 0
    if token:
        for artist in artists:
            name = artist.get("name")
            current_url = artist.get("url")

            if not name:
                continue

            new_url = search_this_is_playlist(artist, token)

            # 見つからなかった場合は、既存のURLをそのまま維持する（空に上書きしない）
            if new_url and new_url != current_url:
                print(f"【更新成功】 {name}: {current_url} -> {new_url}")
                artist["url"] = new_url
                updated_count += 1
            else:
                print(f"【維持】 {name}")

    new_text = dump_text(artists)
    # 内容が同じなら書き込まない（update.yml 側も、差分が無ければコミットしない）
    if new_text != original_text:
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(new_text)
        print(f"保存しました（URL更新 {updated_count} 件／整形を含む）。")
    else:
        print("更新が必要な内容はありませんでした。")

if __name__ == "__main__":
    main()
