import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from urllib.parse import quote_plus

import requests
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*args, **kwargs):
        return False

from db import get_connection


YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_BASE_URL = "https://api.igdb.com/v4"
WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKI_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
REQUEST_TIMEOUT = 12
_IGDB_ERROR_SEEN = set()


def non_empty(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def pick_best(current: Optional[str], candidate: Optional[str]) -> Optional[str]:
    return non_empty(current) or non_empty(candidate)


def better_text(current: Optional[str], candidate: Optional[str]) -> Optional[str]:
    current_clean = non_empty(current)
    candidate_clean = non_empty(candidate)
    if not current_clean:
        return candidate_clean
    if not candidate_clean:
        return current_clean
    if len(candidate_clean) > len(current_clean):
        return candidate_clean
    return current_clean


def build_search_variants(name: str) -> List[str]:
    variants = [name]
    if ":" in name:
        variants.append(name.split(":", 1)[0].strip())
    no_apostrophe = name.replace("'", "")
    variants.append(no_apostrophe)
    no_symbols = re.sub(r"[^A-Za-z0-9 ]+", " ", name).strip()
    variants.append(no_symbols)
    compact = re.sub(r"\s+", " ", no_symbols).strip()
    variants.append(compact)

    unique = []
    seen = set()
    for value in variants:
        cleaned = value.strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            unique.append(cleaned)
    return unique


def score_match(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def load_env_file_fallback(env_path: Path):
    # Fallback when python-dotenv is unavailable or not active.
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def fetch_youtube_trailer(game_title: str, api_key: str) -> Optional[str]:
    params = {
        "part": "snippet",
        "q": f"{game_title} official trailer",
        "type": "video",
        "maxResults": 1,
        "key": api_key,
    }
    try:
        response = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return None
        items = response.json().get("items", [])
        if not items:
            return None
        video_id = items[0].get("id", {}).get("videoId")
        if not video_id:
            return None
        return f"https://www.youtube.com/watch?v={video_id}"
    except requests.RequestException:
        return None


def igdb_image_to_https(url: Optional[str], size: str = "t_cover_big") -> Optional[str]:
    if not url:
        return None
    result = url.replace("//", "https://", 1)
    return result.replace("t_thumb", size)


def get_twitch_app_token(client_id: str, client_secret: str) -> Optional[str]:
    params = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }
    try:
        response = requests.post(TWITCH_TOKEN_URL, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            details = response.text.strip().replace("\n", " ")
            print(f"[AUTH][TWITCH] Echec token HTTP {response.status_code}: {details[:300]}")
            return None
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            print(f"[AUTH][TWITCH] Reponse sans access_token: {payload}")
            return None
        return token
    except requests.RequestException:
        print("[AUTH][TWITCH] Erreur reseau pendant la recuperation du token.")
        return None


def igdb_post(path: str, body: str, client_id: str, access_token: str) -> list:
    url = f"{IGDB_BASE_URL}/{path}"
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    try:
        response = requests.post(url, data=body, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            details = response.text.strip().replace("\n", " ")
            signature = f"{path}:{response.status_code}:{details[:120]}"
            if signature not in _IGDB_ERROR_SEEN:
                _IGDB_ERROR_SEEN.add(signature)
                print(f"[IGDB] {path} HTTP {response.status_code}: {details[:240]}")
            return []
        data = response.json()
        return data if isinstance(data, list) else []
    except requests.RequestException:
        print(f"[IGDB] Erreur reseau sur endpoint {path}.")
        return []


def fetch_best_wikipedia_title(name: str, entity_hint: str) -> Optional[str]:
    queries = [
        f"{name} {entity_hint}",
        f"{name} video game company",
        f"{name} game studio",
        name,
    ]
    for query in queries:
        params = {
            "action": "query",
            "list": "search",
            "format": "json",
            "srlimit": 3,
            "srsearch": query,
        }
        try:
            response = requests.get(WIKI_SEARCH_URL, params=params, timeout=8)
            if response.status_code != 200:
                continue
            results = response.json().get("query", {}).get("search", [])
            if not results:
                continue
            # Favor titles closest to target name when possible.
            ranked = sorted(
                results,
                key=lambda r: score_match(name, r.get("title", "")),
                reverse=True,
            )
            best_title = ranked[0].get("title")
            if best_title:
                return best_title
        except requests.RequestException:
            continue
    return None


def fetch_wikipedia_summary(name: str, entity_hint: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    title = fetch_best_wikipedia_title(name, entity_hint) or name
    url = WIKI_SUMMARY_URL.format(title=quote_plus(title))
    try:
        response = requests.get(url, timeout=8)
        if response.status_code != 200:
            return None, None, None
        data = response.json()
        summary = data.get("extract")
        image_url = (
            data.get("originalimage", {}).get("source")
            or data.get("thumbnail", {}).get("source")
        )
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page")
        return summary, image_url, page_url
    except requests.RequestException:
        return None, None, None


def pick_best_result_by_name(results: list, target_name: str) -> Optional[dict]:
    if not results:
        return None
    scored = []
    for item in results:
        candidate_name = item.get("name") or ""
        scored.append((score_match(target_name, candidate_name), item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else None


def fetch_igdb_game(game_title: str, client_id: str, access_token: str) -> Dict[str, Optional[str]]:
    default = {
        "description": None,
        "cover_image_url": None,
        "metacritic_score": None,
        "official_site_url": None,
        "youtube_trailer_url": None,
        "igdb_url": None,
    }

    all_results = []
    for variant in build_search_variants(game_title):
        safe_title = variant.replace('"', '\\"')
        body = (
            "fields name,summary,aggregated_rating,url,"
            "websites.url,websites.category,cover.url,videos.video_id;"
            f' search "{safe_title}"; limit 5;'
        )
        results = igdb_post("games", body, client_id, access_token)
        if results:
            all_results.extend(results)
            break

    game = pick_best_result_by_name(all_results, game_title)
    if not game:
        return default

    trailer = None
    for video in game.get("videos", []) or []:
        video_id = video.get("video_id")
        if video_id:
            trailer = f"https://www.youtube.com/watch?v={video_id}"
            break

    official_site = None
    for website in game.get("websites", []) or []:
        url = website.get("url")
        if url:
            official_site = url
            break

    score = game.get("aggregated_rating")
    score_int = int(round(score)) if isinstance(score, (int, float)) else None

    return {
        "description": game.get("summary"),
        "cover_image_url": igdb_image_to_https((game.get("cover") or {}).get("url"), size="t_cover_big"),
        "metacritic_score": score_int,
        "official_site_url": official_site,
        "youtube_trailer_url": trailer,
        "igdb_url": game.get("url"),
    }


def fetch_igdb_studio(studio_name: str, client_id: str, access_token: str) -> Dict[str, Optional[str]]:
    default = {
        "description": None,
        "logo_image_url": None,
        "website_url": None,
        "country": None,
    }
    all_results = []
    for variant in build_search_variants(studio_name):
        safe_name = variant.replace('"', '\\"')
        body = (
            "fields name,description,url,logo.url;"
            f' search "{safe_name}"; limit 5;'
        )
        results = igdb_post("companies", body, client_id, access_token)
        if results:
            all_results.extend(results)
            break

    studio = pick_best_result_by_name(all_results, studio_name)
    if not studio:
        return default
    return {
        "description": studio.get("description"),
        "logo_image_url": igdb_image_to_https((studio.get("logo") or {}).get("url"), size="t_logo_med"),
        "website_url": studio.get("url"),
        "country": None,
    }


def fallback_metacritic_url(game_title: str) -> str:
    return f"https://www.metacritic.com/search/{quote_plus(game_title)}/"


def sync_games(
    youtube_api_key: Optional[str],
    igdb_client_id: Optional[str],
    igdb_access_token: Optional[str],
    limit: Optional[int],
) -> int:
    updated = 0
    with get_connection() as conn:
        games = conn.execute("SELECT * FROM games ORDER BY title").fetchall()
        if limit:
            games = games[:limit]
        for game in games:
            title = game["title"]
            trailer_url = None
            igdb_data = {}

            if youtube_api_key:
                trailer_url = fetch_youtube_trailer(title, youtube_api_key)
            if igdb_client_id and igdb_access_token:
                igdb_data = fetch_igdb_game(title, igdb_client_id, igdb_access_token)

            wiki_summary, wiki_image, _wiki_page = fetch_wikipedia_summary(title, "video game")

            description = better_text(
                pick_best(game["description"], igdb_data.get("description") if igdb_data else None),
                wiki_summary,
            )
            cover_image_url = pick_best(
                pick_best(game["cover_image_url"], igdb_data.get("cover_image_url") if igdb_data else None),
                wiki_image,
            )
            official_site = pick_best(game["official_site_url"], igdb_data.get("official_site_url") if igdb_data else None)
            youtube_url = pick_best(game["youtube_trailer_url"], trailer_url)
            if not youtube_url and igdb_data:
                youtube_url = pick_best(youtube_url, igdb_data.get("youtube_trailer_url"))
            metacritic_score = game["metacritic_score"] or (igdb_data.get("metacritic_score") if igdb_data else None)
            metacritic_url = pick_best(game["metacritic_url"], fallback_metacritic_url(title))

            conn.execute(
                """
                UPDATE games
                SET description = ?,
                    cover_image_url = ?,
                    official_site_url = ?,
                    youtube_trailer_url = ?,
                    metacritic_score = ?,
                    metacritic_url = ?
                WHERE id = ?
                """,
                (
                    description,
                    cover_image_url,
                    official_site,
                    youtube_url,
                    metacritic_score,
                    metacritic_url,
                    game["id"],
                ),
            )
            updated += 1
    return updated


def sync_studios(igdb_client_id: Optional[str], igdb_access_token: Optional[str], limit: Optional[int]) -> int:
    if not igdb_client_id or not igdb_access_token:
        return 0
    updated = 0
    with get_connection() as conn:
        studios = conn.execute("SELECT * FROM studios ORDER BY name").fetchall()
        if limit:
            studios = studios[:limit]
        for studio in studios:
            igdb_data = fetch_igdb_studio(studio["name"], igdb_client_id, igdb_access_token)
            wiki_summary, wiki_logo, wiki_page = fetch_wikipedia_summary(studio["name"], "video game developer")
            description = better_text(pick_best(studio["description"], igdb_data.get("description")), wiki_summary)
            logo = pick_best(pick_best(studio["logo_image_url"], igdb_data.get("logo_image_url")), wiki_logo)
            website = pick_best(studio["website_url"], igdb_data.get("website_url"))
            website = pick_best(website, wiki_page)
            country = pick_best(studio["country"], igdb_data.get("country"))

            conn.execute(
                """
                UPDATE studios
                SET description = ?,
                    logo_image_url = ?,
                    website_url = ?,
                    country = ?
                WHERE id = ?
                """,
                (description, logo, website, country, studio["id"]),
            )
            updated += 1
    return updated


def main():
    env_path = Path(__file__).parent / ".env"
    load_dotenv(dotenv_path=env_path)
    load_env_file_fallback(env_path)
    youtube_api_key = non_empty(os.getenv("YOUTUBE_API_KEY"))
    igdb_client_id = non_empty(os.getenv("IGDB_CLIENT_ID"))
    igdb_client_secret = non_empty(os.getenv("IGDB_CLIENT_SECRET"))
    limit_raw = non_empty(os.getenv("SYNC_LIMIT"))
    limit = int(limit_raw) if limit_raw and limit_raw.isdigit() else None

    igdb_access_token = None
    if igdb_client_id and igdb_client_secret:
        igdb_access_token = get_twitch_app_token(igdb_client_id, igdb_client_secret)

    games_updated = sync_games(youtube_api_key, igdb_client_id, igdb_access_token, limit)
    studios_updated = sync_studios(igdb_client_id, igdb_access_token, limit)

    print("Sync metadata termine.")
    print(f"Games traites: {games_updated}")
    print(f"Studios traites: {studios_updated}")
    if not youtube_api_key:
        print("Note: YOUTUBE_API_KEY absent, trailers YouTube non enrichis via API.")
    if not igdb_client_id or not igdb_client_secret:
        print("Note: IGDB_CLIENT_ID/IGDB_CLIENT_SECRET absents, metadata IGDB non enrichie.")
    elif not igdb_access_token:
        print("Note: token Twitch IGDB impossible a recuperer, verifier les credentials.")


if __name__ == "__main__":
    main()
