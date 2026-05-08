import os
import re
from urllib.parse import quote_plus
from typing import Optional, Tuple
from pathlib import Path
import json

import requests

from db import get_connection


WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKI_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "CGA2026DataBot/1.0 (research app)"
MANUAL_OVERRIDES_PATH = Path(__file__).parent / "data" / "manual_overrides.json"


def slugify_for_wiki(name: str) -> str:
    return name.replace(":", "").replace("'", "")


def youtube_search_url(game_title: str) -> str:
    query = quote_plus(f"{game_title} official trailer")
    return f"https://www.youtube.com/results?search_query={query}"


def metacritic_search_url(game_title: str) -> str:
    query = quote_plus(game_title)
    return f"https://www.metacritic.com/search/{query}/"


def fetch_best_wikipedia_title(name: str, entity_hint: str) -> Optional[str]:
    # entity_hint: "video game" or "video game developer"
    params = {
        "action": "query",
        "list": "search",
        "format": "json",
        "srlimit": 1,
        "srsearch": f"{name} {entity_hint}",
    }
    try:
        response = requests.get(
            WIKI_SEARCH_URL,
            params=params,
            timeout=8,
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code != 200:
            return None
        results = response.json().get("query", {}).get("search", [])
        if not results:
            return None
        return results[0].get("title")
    except requests.RequestException:
        return None


def fetch_wikipedia_summary(title: str, entity_hint: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    best_title = fetch_best_wikipedia_title(title, entity_hint) or title
    wiki_title = slugify_for_wiki(best_title)
    url = WIKI_SUMMARY_URL.format(title=quote_plus(wiki_title))
    try:
        response = requests.get(url, timeout=8, headers={"User-Agent": USER_AGENT})
        if response.status_code != 200:
            return None, None, None
        data = response.json()
        extract = data.get("extract")
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page")
        image_url = (
            data.get("originalimage", {}).get("source")
            or data.get("thumbnail", {}).get("source")
        )
        return extract, page_url, image_url
    except requests.RequestException:
        return None, None, None


def parse_score_from_text(text: str) -> Optional[int]:
    match = re.search(r"\b([1-9][0-9]|100)\b", text or "")
    if not match:
        return None
    score = int(match.group(1))
    if score < 30:
        return None
    return score


def is_low_quality_description(text: Optional[str]) -> bool:
    if not text:
        return True
    lowered = text.lower()
    bad_patterns = [
        "may refer to",
        "this list of",
        "disambiguation",
    ]
    return any(pattern in lowered for pattern in bad_patterns)


def enrich_games():
    with get_connection() as conn:
        games = conn.execute("SELECT id, title, description, cover_image_url FROM games ORDER BY title").fetchall()

        for game in games:
            title = game["title"]
            summary, wiki_url, image_url = fetch_wikipedia_summary(title, "video game")
            guessed_score = parse_score_from_text(summary) if summary else None
            chosen_description = summary if is_low_quality_description(game["description"]) else game["description"]
            chosen_image = game["cover_image_url"] or image_url

            conn.execute(
                """
                UPDATE games
                SET description = ?,
                    wikipedia_url = COALESCE(wikipedia_url, ?),
                    cover_image_url = ?,
                    youtube_trailer_url = COALESCE(youtube_trailer_url, ?),
                    metacritic_url = COALESCE(metacritic_url, ?),
                    metacritic_score = COALESCE(metacritic_score, ?)
                WHERE id = ?
                """,
                (
                    chosen_description,
                    wiki_url,
                    chosen_image,
                    youtube_search_url(title),
                    metacritic_search_url(title),
                    guessed_score,
                    game["id"],
                ),
            )


def enrich_studios():
    with get_connection() as conn:
        studios = conn.execute("SELECT id, name, description, logo_image_url FROM studios ORDER BY name").fetchall()
        for studio in studios:
            summary, wiki_url, image_url = fetch_wikipedia_summary(studio["name"], "video game developer")
            chosen_description = summary if is_low_quality_description(studio["description"]) else studio["description"]
            chosen_logo = studio["logo_image_url"] or image_url
            conn.execute(
                """
                UPDATE studios
                SET description = ?,
                    logo_image_url = ?,
                    wikipedia_url = COALESCE(wikipedia_url, ?)
                WHERE id = ?
                """,
                (chosen_description, chosen_logo, wiki_url, studio["id"]),
            )


def main():
    if os.getenv("SKIP_ENRICHMENT") == "1":
        print("Enrichissement ignore (SKIP_ENRICHMENT=1).")
        return
    enrich_games()
    enrich_studios()
    apply_manual_overrides()
    print("Enrichissement public termine.")


def apply_manual_overrides():
    if not MANUAL_OVERRIDES_PATH.exists():
        return
    payload = json.loads(MANUAL_OVERRIDES_PATH.read_text(encoding="utf-8"))
    with get_connection() as conn:
        for game_title, attrs in payload.get("games", {}).items():
            conn.execute(
                """
                UPDATE games
                SET description = COALESCE(?, description),
                    cover_image_url = COALESCE(?, cover_image_url),
                    youtube_trailer_url = COALESCE(?, youtube_trailer_url),
                    metacritic_url = COALESCE(?, metacritic_url),
                    metacritic_score = COALESCE(?, metacritic_score),
                    wikipedia_url = COALESCE(?, wikipedia_url),
                    official_site_url = COALESCE(?, official_site_url)
                WHERE title = ?
                """,
                (
                    attrs.get("description"),
                    attrs.get("cover_image_url"),
                    attrs.get("youtube_trailer_url"),
                    attrs.get("metacritic_url"),
                    attrs.get("metacritic_score"),
                    attrs.get("wikipedia_url"),
                    attrs.get("official_site_url"),
                    game_title,
                ),
            )

        for studio_name, attrs in payload.get("studios", {}).items():
            conn.execute(
                """
                UPDATE studios
                SET description = COALESCE(?, description),
                    logo_image_url = COALESCE(?, logo_image_url),
                    website_url = COALESCE(?, website_url),
                    wikipedia_url = COALESCE(?, wikipedia_url),
                    country = COALESCE(?, country)
                WHERE name = ?
                """,
                (
                    attrs.get("description"),
                    attrs.get("logo_image_url"),
                    attrs.get("website_url"),
                    attrs.get("wikipedia_url"),
                    attrs.get("country"),
                    studio_name,
                ),
            )


if __name__ == "__main__":
    main()
