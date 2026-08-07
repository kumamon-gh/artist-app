import json
import os
import requests

# Spotify API認証情報（GitHub Secretから取得）
CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")

JSON_FILE_PATH = "artists.json"  # artists.json のパス


def get_access_token():
    """Spotify APIのアクセストークンを取得"""
    auth_url = "https://accounts.spotify.com/api/token"
    response = requests.post(
        auth_url,
        data={"grant_type": "client_credentials"},
        auth=(CLIENT_ID, CLIENT_SECRET),
    )
    return response.json().get("access_token")


def search_this_is_playlist(artist_name, token):
    """アーティスト名で「This Is [アーティスト名]」プレイリストを精密検索"""
    search_url = "https://api.spotify.com/v1/search"
    headers = {"Authorization": f"Bearer {token}"}

    # 検索クエリ: 公式プレイリストを優先的に検索
    query = f"This Is {artist_name}"
    params = {"q": query, "type": "playlist", "limit": 5}

    res = requests.get(search_url, headers=headers, params=params)
    if res.status_code != 200:
        return None

    data = res.json()
    playlists = data.get("playlists", {}).get("items", [])

    for pl in playlists:
        if not pl:
            continue
        # Spotify公式（ownerがspotify）かつタイトルの完全一致判定
        owner_id = pl.get("owner", {}).get("id", "")
        pl_name = pl.get("name", "").strip().lower()
        target_name = f"this is {artist_name}".strip().lower()

        if owner_id == "spotify" and pl_name == target_name:
            return pl.get("external_urls", {}).get("spotify")

    # 完全一致が見つからない場合、Spotify公式の1番目の結果を返す
    for pl in playlists:
        if pl and pl.get("owner", {}).get("id") == "spotify":
            return pl.get("external_urls", {}).get("spotify")

    return None


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Error: Spotify credentials not found.")
        return

    token = get_access_token()
    if not token:
        print("Error: Failed to authenticate with Spotify.")
        return

    # artists.json 読み込み
    with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
        artists = json.load(f)

    updated_count = 0

    for artist in artists:
        name = artist.get("name")
        if not name:
            continue

        print(f"Checking: {name}...")
        new_url = search_this_is_playlist(name, token)

        if new_url:
            current_url = artist.get("url") or artist.get("link")
            if current_url != new_url:
                artist["url"] = new_url
                updated_count += 1
                print(f" -> Updated URL: {new_url}")
        else:
            print(f" -> Playlist not found for {name}")

    # 更新があった場合のみ書き込み
    if updated_count > 0:
        with open(JSON_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(artists, f, ensure_ascii=False, indent=2)
        print(f"Successfully updated {updated_count} artists.")
    else:
        print("All URLs are up to date.")


if __name__ == "__main__":
    main()
