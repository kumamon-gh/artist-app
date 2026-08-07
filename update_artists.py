def search_this_is_playlist(artist_name, token):
  """アーティスト名で「This Is [アーティスト名]」プレイリストを精密検索"""
  search_url = "https://api.spotify.com/v1/search"
  headers = {"Authorization": f"Bearer {token}"}

  # 検索クエリ: 公式プレイリストを優先的に検索
  query = f"This Is {artist_name}"
  params = {"q": query, "type": "playlist", "limit": 10}

  res = requests.get(search_url, headers=headers, params=params)
  if res.status_code != 200:
    return None

  data = res.json()
  playlists = data.get("playlists", {}).get("items", [])

  for pl in playlists:
    if not pl:
      continue
    owner_id = pl.get("owner", {}).get("id", "")
    pl_name = pl.get("name", "").strip().lower()
    target_name = f"this is {artist_name}".strip().lower()

    # オーナーがspotify、または名前に完全一致、あるいは部分一致するもの許容
    if owner_id == "spotify" and target_name in pl_name:
      return pl.get("external_urls", {}).get("spotify")

  # Spotify公式のものが見つからない場合、最初に出てきたヒット率の高い公式系をフォールバック
  for pl in playlists:
    if pl and pl.get("owner", {}).get("id") == "spotify":
      return pl.get("external_urls", {}).get("spotify")

  # どうしても公式が見つからない場合は検索結果の1番目を返す（リンク切れ防止）
  if playlists and playlists[0]:
    return playlists[0].get("external_urls", {}).get("spotify")

  return None
