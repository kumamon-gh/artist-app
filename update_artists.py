import json
import os
import requests

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
    # スラッシュで区切られたローマ字候補をすべて分解して取得
    romaji_list = [r.strip().lower() for r in romaji_raw.split('/') if r.strip()]
    
    search_url = "https://api.spotify.com/v1/search"
    headers = {"Authorization": f"Bearer {token}"}
    
    queries = [f"This Is {name}"]
    for r in romaji_list:
        queries.append(f"This Is {r}")

    for query in queries:
        params = {"q": query, "type": "playlist", "limit": 10}
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

            # Spotify公式制作のプレイリストか
            if owner_id == "spotify" and "this is" in pl_name:
                # 判定対象のリスト（名前本体 ＋ ローマ字全パターン）
                check_targets = [name.lower()] + romaji_list
                for target in check_targets:
                    if target and target in pl_name:
                        return pl.get("external_urls", {}).get("spotify")

    return None

def main():
    token = get_spotify_token()
    if not token:
        print("アクセストークンの取得に失敗したため終了します。")
        return

    json_path = "artists.json"
    if not os.path.exists(json_path):
        print(f"{json_path} が見つかりません。")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        artists = json.load(f)

    updated_count = 0
    for artist in artists:
        name = artist.get("name")
        current_url = artist.get("url")

        if not name:
            continue

        new_url = search_this_is_playlist(artist, token)

        if new_url and new_url != current_url:
            print(f"【更新】 {name}: {current_url} -> {new_url}")
            artist["url"] = new_url
            updated_count += 1
        else:
            print(f"【変更なし/維持】 {name}")

    if updated_count > 0:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(artists, f, ensure_ascii=False, indent=2)
        print(f"合計 {updated_count} 件のアーティストURLを更新しました。")
    else:
        print("更新が必要なURLはありませんでした。")

if __name__ == "__main__":
    main()
