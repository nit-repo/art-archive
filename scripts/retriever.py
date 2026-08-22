"""
Retriever — Stage 1 of the Research pipeline.
Pulls raw, structured facts about an artwork from free public sources.
No AI model involved. No API key required for this stage.

Usage:
    python retriever.py "Mérode Altarpiece"

Output:
    Writes archive/<slug>/raw_sources.json
"""

import sys
import json
import requests
from datetime import datetime, timezone

from common import (
    RAW_SOURCES_FILENAME,
    artwork_dir,
    require_artwork_name,
    title_match_score,
    write_text,
)

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIPEDIA_EXTRACT_URL = "https://en.wikipedia.org/w/api.php"
MET_SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"

HEADERS = {
    "User-Agent": "ArtArchiveResearchBot/1.0 (personal research project)"
}

# A Met search result must share at least this fraction of the query's
# identifying words with its title before we treat it as the same artwork.
MET_TITLE_MATCH_THRESHOLD = 0.6
# How many search hits to inspect before giving up.
MET_MAX_CANDIDATES = 10

# Wikidata sometimes returns skolemised blank nodes ("some value" statements)
# instead of a real entity. They carry no information and must not reach the model.
_BLANK_NODE_MARKER = "/.well-known/genid/"


def _escape_sparql_literal(value: str) -> str:
    """Escape a string for safe use inside a SPARQL double-quoted literal."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _is_usable_value(value) -> bool:
    return bool(value) and _BLANK_NODE_MARKER not in str(value)


def fetch_wikidata(artwork_name: str) -> dict | None:
    """Query Wikidata for structured facts about the artwork via its label."""
    literal = _escape_sparql_literal(artwork_name)
    query = f"""
    SELECT ?item ?itemLabel ?creatorLabel ?inception ?mediumLabel ?locationLabel ?movementLabel WHERE {{
      ?item rdfs:label|skos:altLabel "{literal}"@en.
      OPTIONAL {{ ?item wdt:P170 ?creator. }}
      OPTIONAL {{ ?item wdt:P571 ?inception. }}
      OPTIONAL {{ ?item wdt:P186 ?medium. }}
      OPTIONAL {{ ?item wdt:P276 ?location. }}
      OPTIONAL {{ ?item wdt:P135 ?movement. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 1
    """
    try:
        resp = requests.get(
            WIKIDATA_SPARQL_URL,
            params={"query": query, "format": "json"},
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        bindings = resp.json().get("results", {}).get("bindings", [])
        if not bindings:
            return None
        b = bindings[0]

        def get(key):
            value = b.get(key, {}).get("value")
            return value if _is_usable_value(value) else None

        labelled_fields = [
            ("Creator", "creatorLabel"),
            ("Inception date", "inception"),
            ("Medium", "mediumLabel"),
            ("Current location", "locationLabel"),
            ("Movement", "movementLabel"),
        ]
        raw_text_parts = [
            f"{label}: {get(key)}" for label, key in labelled_fields if get(key)
        ]

        if not raw_text_parts:
            return None

        return {
            "source_id": "wikidata_001",
            "origin": "Wikidata",
            "url": get("item"),
            "raw_text": "; ".join(raw_text_parts),
        }
    except requests.RequestException:
        return None


def fetch_wikipedia_summary(artwork_name: str) -> tuple[dict | None, list]:
    """
    Get the short summary from Wikipedia's REST API.
    Returns (source, images) — the REST response carries the lead image,
    which the reel brief needs, so we keep it rather than discarding it.
    """
    try:
        url = WIKIPEDIA_SUMMARY_URL.format(title=artwork_name.replace(" ", "_"))
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return None, []
        data = resp.json()
        extract = data.get("extract")
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page")
        if not extract:
            return None, []

        images = []
        original = data.get("originalimage") or {}
        thumbnail = data.get("thumbnail") or {}
        if original.get("source"):
            images.append(
                {
                    "url": original["source"],
                    "width": original.get("width"),
                    "height": original.get("height"),
                    "role": "full_resolution",
                    "source_id": "wikipedia_summary_001",
                    "credit": "Wikipedia / Wikimedia Commons",
                }
            )
        if thumbnail.get("source"):
            images.append(
                {
                    "url": thumbnail["source"],
                    "width": thumbnail.get("width"),
                    "height": thumbnail.get("height"),
                    "role": "thumbnail",
                    "source_id": "wikipedia_summary_001",
                    "credit": "Wikipedia / Wikimedia Commons",
                }
            )

        source = {
            "source_id": "wikipedia_summary_001",
            "origin": "Wikipedia (summary)",
            "url": page_url,
            "raw_text": extract,
        }
        return source, images
    except requests.RequestException:
        return None, []


def fetch_wikipedia_full_extract(artwork_name: str) -> dict | None:
    """Get a longer plaintext extract via the Wikipedia action API."""
    try:
        params = {
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "titles": artwork_name,
            "format": "json",
            "exintro": 0,
            "exchars": 4000,
        }
        resp = requests.get(WIKIPEDIA_EXTRACT_URL, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for _, page in pages.items():
            extract = page.get("extract")
            if extract:
                return {
                    "source_id": "wikipedia_full_001",
                    "origin": "Wikipedia (full extract)",
                    "url": f"https://en.wikipedia.org/wiki/{artwork_name.replace(' ', '_')}",
                    "raw_text": extract,
                }
        return None
    except requests.RequestException:
        return None


def _met_search_ids(artwork_name: str) -> list:
    """Search the Met twice — title-scoped first, then general — and merge hits."""
    object_ids = []
    for params in (
        {"q": artwork_name, "title": "true"},
        {"q": artwork_name, "hasImages": "true"},
    ):
        try:
            resp = requests.get(MET_SEARCH_URL, params=params, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            for object_id in resp.json().get("objectIDs") or []:
                if object_id not in object_ids:
                    object_ids.append(object_id)
        except requests.RequestException:
            continue
    return object_ids


def fetch_met_object(artwork_name: str) -> tuple[dict | None, list]:
    """
    Search the Met's Open Access API for an object whose title actually
    matches the artwork we asked about.

    The previous version took objectIDs[0] unconditionally, which returned
    an unrelated painting (Memling's "The Annunciation" for a "Mérode
    Altarpiece" query) and fed it to the model as an authoritative source.
    """
    object_ids = _met_search_ids(artwork_name)
    if not object_ids:
        return None, []

    best_obj = None
    best_score = 0.0

    for object_id in object_ids[:MET_MAX_CANDIDATES]:
        try:
            obj_resp = requests.get(
                MET_OBJECT_URL.format(object_id=object_id), headers=HEADERS, timeout=20
            )
            obj_resp.raise_for_status()
            obj = obj_resp.json()
        except requests.RequestException:
            continue

        score = title_match_score(artwork_name, obj.get("title") or "")
        if score > best_score:
            best_obj, best_score = obj, score
        if best_score >= 1.0:
            break

    if best_obj is None or best_score < MET_TITLE_MATCH_THRESHOLD:
        print(
            f"  Met: no object title matched '{artwork_name}' "
            f"(best score {best_score:.2f} < {MET_TITLE_MATCH_THRESHOLD}); skipping this source."
        )
        return None, []

    fields = {
        "Title": best_obj.get("title"),
        "Artist": best_obj.get("artistDisplayName"),
        "Date": best_obj.get("objectDate"),
        "Medium": best_obj.get("medium"),
        "Dimensions": best_obj.get("dimensions"),
        "Department": best_obj.get("department"),
        "Credit line": best_obj.get("creditLine"),
    }
    raw_text = "; ".join(f"{k}: {v}" for k, v in fields.items() if v)
    if not raw_text:
        return None, []

    images = []
    if best_obj.get("primaryImage"):
        images.append(
            {
                "url": best_obj["primaryImage"],
                "role": "full_resolution",
                "source_id": "met_001",
                "credit": best_obj.get("creditLine") or "The Metropolitan Museum of Art",
            }
        )
    if best_obj.get("primaryImageSmall"):
        images.append(
            {
                "url": best_obj["primaryImageSmall"],
                "role": "thumbnail",
                "source_id": "met_001",
                "credit": best_obj.get("creditLine") or "The Metropolitan Museum of Art",
            }
        )
    for extra in (best_obj.get("additionalImages") or [])[:5]:
        images.append(
            {
                "url": extra,
                "role": "detail",
                "source_id": "met_001",
                "credit": best_obj.get("creditLine") or "The Metropolitan Museum of Art",
            }
        )

    source = {
        "source_id": "met_001",
        "origin": "Met Open Access API",
        "url": best_obj.get("objectURL"),
        "raw_text": raw_text,
        "title_match_score": round(best_score, 2),
    }
    return source, images


def retrieve(artwork_name: str) -> dict:
    sources = []
    images = []

    wikidata = fetch_wikidata(artwork_name)
    if wikidata:
        sources.append(wikidata)

    wiki_summary, summary_images = fetch_wikipedia_summary(artwork_name)
    if wiki_summary:
        sources.append(wiki_summary)
    images.extend(summary_images)

    wiki_full = fetch_wikipedia_full_extract(artwork_name)
    if wiki_full:
        sources.append(wiki_full)

    met, met_images = fetch_met_object(artwork_name)
    if met:
        sources.append(met)
    images.extend(met_images)

    return {
        "artwork_query": artwork_name,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "images": images,
        "status": "retrieved" if sources else "no_sources_found",
    }


def main():
    artwork_name = require_artwork_name(sys.argv, "retriever.py")

    bundle = retrieve(artwork_name)

    out_path = artwork_dir(artwork_name) / RAW_SOURCES_FILENAME
    write_text(out_path, json.dumps(bundle, indent=2, ensure_ascii=False))

    print(f"Retrieved {len(bundle['sources'])} source(s) for '{artwork_name}'")
    print(f"Found {len(bundle['images'])} image asset(s)")
    print(f"Written to: {out_path}")

    if not bundle["sources"]:
        print("WARNING: no sources found — Researcher stage will produce a thin/low-confidence entry.")


if __name__ == "__main__":
    main()
