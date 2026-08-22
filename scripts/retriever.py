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
import re
import requests
from pathlib import Path
from datetime import datetime, timezone

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKIPEDIA_EXTRACT_URL = "https://en.wikipedia.org/w/api.php"
MET_SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"

HEADERS = {
    "User-Agent": "ArtArchiveResearchBot/1.0 (personal research project)"
}


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_")
    return slug[:80]


def fetch_wikidata(artwork_name: str) -> dict | None:
    """Query Wikidata for structured facts about the artwork via its label."""
    query = f"""
    SELECT ?item ?itemLabel ?creatorLabel ?inception ?mediumLabel ?locationLabel ?movementLabel WHERE {{
      ?item rdfs:label "{artwork_name}"@en.
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
            return b.get(key, {}).get("value")

        raw_text_parts = []
        if get("creatorLabel"):
            raw_text_parts.append(f"Creator: {get('creatorLabel')}")
        if get("inception"):
            raw_text_parts.append(f"Inception date: {get('inception')}")
        if get("mediumLabel"):
            raw_text_parts.append(f"Medium: {get('mediumLabel')}")
        if get("locationLabel"):
            raw_text_parts.append(f"Current location: {get('locationLabel')}")
        if get("movementLabel"):
            raw_text_parts.append(f"Movement: {get('movementLabel')}")

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


def fetch_wikipedia_summary(artwork_name: str) -> dict | None:
    """Get the short summary from Wikipedia's REST API."""
    try:
        url = WIKIPEDIA_SUMMARY_URL.format(title=artwork_name.replace(" ", "_"))
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return None
        data = resp.json()
        extract = data.get("extract")
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page")
        if not extract:
            return None
        return {
            "source_id": "wikipedia_summary_001",
            "origin": "Wikipedia (summary)",
            "url": page_url,
            "raw_text": extract,
        }
    except requests.RequestException:
        return None


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


def fetch_met_object(artwork_name: str) -> dict | None:
    """Search the Met's Open Access API and pull the first matching object record."""
    try:
        search_resp = requests.get(
            MET_SEARCH_URL,
            params={"q": artwork_name, "hasImages": "true"},
            headers=HEADERS,
            timeout=20,
        )
        search_resp.raise_for_status()
        object_ids = search_resp.json().get("objectIDs") or []
        if not object_ids:
            return None

        object_id = object_ids[0]
        obj_resp = requests.get(
            MET_OBJECT_URL.format(object_id=object_id), headers=HEADERS, timeout=20
        )
        obj_resp.raise_for_status()
        obj = obj_resp.json()

        fields = {
            "Title": obj.get("title"),
            "Artist": obj.get("artistDisplayName"),
            "Date": obj.get("objectDate"),
            "Medium": obj.get("medium"),
            "Dimensions": obj.get("dimensions"),
            "Department": obj.get("department"),
            "Credit line": obj.get("creditLine"),
            "Image URL": obj.get("primaryImage"),
        }
        raw_text = "; ".join(f"{k}: {v}" for k, v in fields.items() if v)
        if not raw_text:
            return None

        return {
            "source_id": "met_001",
            "origin": "Met Open Access API",
            "url": obj.get("objectURL"),
            "raw_text": raw_text,
            "image_url": obj.get("primaryImage"),
        }
    except requests.RequestException:
        return None


def retrieve(artwork_name: str) -> dict:
    sources = []

    wikidata = fetch_wikidata(artwork_name)
    if wikidata:
        sources.append(wikidata)

    wiki_summary = fetch_wikipedia_summary(artwork_name)
    if wiki_summary:
        sources.append(wiki_summary)

    wiki_full = fetch_wikipedia_full_extract(artwork_name)
    if wiki_full:
        sources.append(wiki_full)

    met = fetch_met_object(artwork_name)
    if met:
        sources.append(met)

    bundle = {
        "artwork_query": artwork_name,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "status": "retrieved" if sources else "no_sources_found",
    }
    return bundle


def main():
    if len(sys.argv) < 2:
        print("Usage: python retriever.py \"<Artwork Name>\"")
        sys.exit(1)

    artwork_name = sys.argv[1]
    slug = slugify(artwork_name)

    bundle = retrieve(artwork_name)

    out_dir = Path("archive") / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "raw_sources.json"
    out_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False))

    print(f"Retrieved {len(bundle['sources'])} source(s) for '{artwork_name}'")
    print(f"Written to: {out_path}")

    if not bundle["sources"]:
        print("WARNING: no sources found — Researcher stage will produce a thin/low-confidence entry.")


if __name__ == "__main__":
    main()
