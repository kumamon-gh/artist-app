import json
import os
import re
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

def clean_text(text):
    if not text:
        return ""
    # 記号や空白を除去して小文字化
    return re.sub(r'[\s\-_/\u3000]', '', text).lower()

def search_this_is_playlist(artist_info, token):
    name = artist_info.get("name", "").strip()
    romaji_raw = artist_info.get("romaji", "")
    
    # ローマ字（/区切り）を配列化
    romaji_list = [r.strip() for r in romaji_raw.split('/') if r.strip()]
    
    # 検索候補リストの構築（日本語名、ローマ字名）
    search_keywords = [name] + romaji_list
    
    search_url = "https://api.spotify.com/v1/search"
    headers = {"Authorization": f"Bearer {token}"}
    
    for kw in search_keywords:
        if not kw:
            continue
        query = f"This Is {kw}"
        params = {"q": query, "type": "playlist", "limit": 15}
        
        res = requests.get(search_url, headers=headers, params=params)
        if res.status_code != 200:
            continue

        data = res.json()
        playlists = data.get("playlists", {}).get("items", [])

        # 1. Spotify公式 (owner_id == 'spotify') かつ 「this is」が含まれるものを検証
        for pl in playlists:
            if not pl:
                continue
            
            owner_id = pl.get("owner", {}).get("id", "")
            pl_name = pl.get("name", "").strip()
            pl_name_clean = clean_text(pl_name)

            if owner_id == "spotify" and "thisis" in pl_name_clean:
                # アーティスト名、またはローマ字表記のいずれかがプレイリスト名に含まれているかチェック
                for check_kw in search_keywords:
                    clean_kw = clean_text(check_kw)
                    if clean_kw and clean_kw in pl_name_clean:
                        raw_url = pl.get("external_urls", {}).get("spotify", "")
                        # ?si= 等の不要なパラメータを除去して標準URL化
                        return raw_url.split('?')[0]

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
        current_url = artist.get("url", "")
        # パラメータが付いている場合は比較用に標準化
        clean_current_url = current_url.split('?')[0] if current_url else ""

        if not name:
            continue

        new_url = search_this_is_playlist(artist, token)

        if new_url and new_url != clean_current_url:
            print(f"【更新】 {name}: {current_url} -> {new_url}")
            artist["url"] = new_url
            updated_count += 1
        else:
            print(f"【維持/変化なし】 {name}")

    if updated_count > 0:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(artists, f, ensure_ascii=False, indent=2)
        print(f"合計 {updated_count} 件のアーティストURLを更新しました。")
    else:
        print("更新が必要なURLはありませんでした。")

if __name__ == "__main__":
    main()
