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
    if not name:
        return None

    headers = {"Authorization": f"Bearer {token}"}

    # 1. まずアーティスト自体を検索して正確な名前（Aimyon等）を取得
    artist_search_url = "https://api.spotify.com/v1/search"
    artist_params = {"q": name, "type": "artist", "limit": 1}
    a_res = requests.get(artist_search_url, headers=headers, params=artist_params)
    
    spotify_artist_name = name
    if a_res.status_code == 200:
        artists_items = a_res.json().get("artists", {}).get("items", [])
        if artists_items:
            spotify_artist_name = artists_items[0].get("name", name)

    # 2. プレイリスト検索（日本語名・Spotify上の名前の両方で検索）
    queries = [f"This Is {name}", f"This Is {spotify_artist_name}"]
    
    # 重複を除外して検索実行
    for query in list(dict.fromkeys(queries)):
        pl_params = {"q": query, "type": "playlist", "limit": 10}
        pl_res = requests.get("https://api.spotify.com/v1/search", headers=headers, params=pl_params)
        if pl_res.status_code != 200:
            continue

        playlists = pl_res.json().get("playlists", {}).get("items", [])
        for pl in playlists:
            if not pl:
                continue
            
            owner_id = pl.get("owner", {}).get("id", "")
            pl_name = pl.get("name", "").strip().lower()

            # Spotify公式制作（owner_id == 'spotify'）かつ 'this is' が含まれる場合
            if owner_id == "spotify" and "this is" in pl_name:
                # アーティスト名（日本語 or Spotify公式名）が含まれるか判定
                if name.lower() in pl_name or spotify_artist_name.lower() in pl_name:
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
        elif new_url:
            print(f"【維持（最新）】 {name}")
        else:
            print(f"【未発見】 {name}")

    if updated_count > 0:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(artists, f, ensure_ascii=False, indent=2)
        print(f"合計 {updated_count} 件のアーティストURLを更新しました。")
    else:
        print("更新が必要なURLはありませんでした。")

if __name__ == "__main__":
    main()
