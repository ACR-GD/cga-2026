import json
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import quote_plus, urlparse

import requests


OVERRIDES_PATH = Path(__file__).parent / "data" / "manual_overrides.json"
USER_AGENT = "CGA2026AutoFill/1.0 (public metadata enrichment)"

WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_URL = "https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json"
COMMONS_FILE_URL = "https://commons.wikimedia.org/wiki/Special:FilePath/{filename}"


def yt_search_url(title: str) -> str:
    return f"https://www.youtube.com/results?search_query={quote_plus(title + ' official trailer')}"


def metacritic_search_url(title: str) -> str:
    return f"https://www.metacritic.com/search/{quote_plus(title)}/"


def wikidata_search(query: str, entity_type: str) -> Optional[str]:
    # entity_type: "game" or "studio"
    suffix = "video game" if entity_type == "game" else "video game developer"
    params = {
        "action": "wbsearchentities",
        "search": f"{query} {suffix}",
        "language": "en",
        "format": "json",
        "type": "item",
        "limit": 1,
    }
    try:
        response = requests.get(WIKIDATA_SEARCH_URL, params=params, timeout=10, headers={"User-Agent": USER_AGENT})
        if response.status_code != 200:
            return None
        data = response.json()
        results = data.get("search", [])
        if not results:
            return None
        return results[0].get("id")
    except requests.RequestException:
        return None


def get_entity_payload(entity_id: str) -> Optional[dict]:
    try:
        response = requests.get(
            WIKIDATA_ENTITY_URL.format(entity_id=entity_id),
            timeout=10,
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code != 200:
            return None
        return response.json().get("entities", {}).get(entity_id)
    except requests.RequestException:
        return None


def extract_claim_text(entity: dict, claim_id: str) -> Optional[str]:
    claims = entity.get("claims", {}).get(claim_id, [])
    if not claims:
        return None
    try:
        return claims[0]["mainsnak"]["datavalue"]["value"]
    except (KeyError, TypeError):
        return None


def commons_image_url(filename: Optional[str]) -> Optional[str]:
    if not filename:
        return None
    return COMMONS_FILE_URL.format(filename=quote_plus(filename))


def get_en_description(entity: dict) -> Optional[str]:
    return entity.get("descriptions", {}).get("en", {}).get("value")


def normalize_official_site(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme:
        return None
    return url


def enrich_game_record(title: str, current: Dict) -> Tuple[Dict, bool]:
    updated = dict(current)
    changed = False

    if not updated.get("youtube_trailer_url"):
        updated["youtube_trailer_url"] = yt_search_url(title)
        changed = True
    if not updated.get("metacritic_url"):
        updated["metacritic_url"] = metacritic_search_url(title)
        changed = True

    entity_id = wikidata_search(title, "game")
    if not entity_id:
        return updated, changed
    entity = get_entity_payload(entity_id)
    if not entity:
        return updated, changed

    if not updated.get("description"):
        desc = get_en_description(entity)
        if desc:
            updated["description"] = desc
            changed = True

    if not updated.get("cover_image_url"):
        image_filename = extract_claim_text(entity, "P18")
        image_url = commons_image_url(image_filename)
        if image_url:
            updated["cover_image_url"] = image_url
            changed = True

    if not updated.get("official_site_url"):
        website = normalize_official_site(extract_claim_text(entity, "P856"))
        if website:
            updated["official_site_url"] = website
            changed = True

    return updated, changed


def enrich_studio_record(name: str, current: Dict) -> Tuple[Dict, bool]:
    updated = dict(current)
    changed = False

    entity_id = wikidata_search(name, "studio")
    if not entity_id:
        return updated, changed
    entity = get_entity_payload(entity_id)
    if not entity:
        return updated, changed

    if not updated.get("description"):
        desc = get_en_description(entity)
        if desc:
            updated["description"] = desc
            changed = True

    if not updated.get("website_url"):
        website = normalize_official_site(extract_claim_text(entity, "P856"))
        if website:
            updated["website_url"] = website
            changed = True

    if not updated.get("logo_image_url"):
        logo_filename = extract_claim_text(entity, "P154")
        logo_url = commons_image_url(logo_filename)
        if logo_url:
            updated["logo_image_url"] = logo_url
            changed = True
        elif updated.get("website_url"):
            domain = urlparse(updated["website_url"]).netloc
            if domain:
                updated["logo_image_url"] = f"https://logo.clearbit.com/{domain}"
                changed = True

    return updated, changed


def main():
    data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    changed_count = 0

    games = data.get("games", {})
    for title, payload in games.items():
        updated, changed = enrich_game_record(title, payload)
        games[title] = updated
        if changed:
            changed_count += 1

    studios = data.get("studios", {})
    for studio_name, payload in studios.items():
        updated, changed = enrich_studio_record(studio_name, payload)
        studios[studio_name] = updated
        if changed:
            changed_count += 1

    OVERRIDES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Autofill termine. Entrees modifiees: {changed_count}")


if __name__ == "__main__":
    main()
