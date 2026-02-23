"""
scrape_drugs.py — Fetches drug/medicine data from the OpenFDA API
and stores it into the local SQLite database.

The OpenFDA API provides free, public access to FDA drug labeling data
including indications, warnings, adverse reactions, and drug interactions.

Usage:
    python scrape_drugs.py
"""

import time
import requests
from database import init_db, insert_drugs_bulk, get_total_drugs

# ─── Configuration ──────────────────────────────────────────────────
OPENFDA_URL = "https://api.fda.gov/drug/label.json"
BATCH_SIZE = 100  # OpenFDA max per request
MAX_DRUGS = 500   # Total drugs to fetch
REQUEST_DELAY = 0.5


def truncate(text: str, max_len: int = 2000) -> str:
    """Truncate long FDA text fields to keep DB lightweight."""
    if not text:
        return ""
    if isinstance(text, list):
        text = " ".join(text)
    return text[:max_len].strip()


def fetch_drugs_batch(skip: int = 0, limit: int = 100) -> list[dict]:
    """Fetch a batch of drug labels from OpenFDA."""
    params = {
        "search": 'openfda.product_type:"HUMAN PRESCRIPTION DRUG"',
        "limit": limit,
        "skip": skip,
    }

    try:
        resp = requests.get(OPENFDA_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except Exception as e:
        print(f"  [WARN] OpenFDA request failed (skip={skip}): {e}")
        return []


def parse_drug(raw: dict) -> dict:
    """Parse a raw OpenFDA drug label into our database schema."""
    openfda = raw.get("openfda", {})

    generic_names = openfda.get("generic_name", [])
    brand_names = openfda.get("brand_name", [])

    generic_name = generic_names[0] if generic_names else ""
    brand_name = brand_names[0] if brand_names else ""

    # Skip entries with no useful name
    if not generic_name and not brand_name:
        return None

    return {
        "generic_name": generic_name,
        "brand_name": brand_name,
        "indications": truncate(raw.get("indications_and_usage", "")),
        "description": truncate(raw.get("description", "")),
        "warnings": truncate(raw.get("warnings", "")),
        "adverse_reactions": truncate(raw.get("adverse_reactions", "")),
        "drug_interactions": truncate(raw.get("drug_interactions", "")),
        "dosage_forms": truncate(openfda.get("dosage_form", "")),
        "source_url": f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:\"{generic_name}\"",
    }


def run():
    print("=" * 60)
    print("  Healthcare Chatbot — FDA Drug Data Scraper")
    print("=" * 60)

    init_db()

    all_drugs = []
    fetched = 0

    while fetched < MAX_DRUGS:
        batch_size = min(BATCH_SIZE, MAX_DRUGS - fetched)
        print(f"[Drugs] Fetching batch (skip={fetched}, limit={batch_size})...")

        raw_drugs = fetch_drugs_batch(skip=fetched, limit=batch_size)
        if not raw_drugs:
            print("[Drugs] No more results. Stopping.")
            break

        for raw in raw_drugs:
            parsed = parse_drug(raw)
            if parsed:
                all_drugs.append(parsed)

        fetched += len(raw_drugs)
        time.sleep(REQUEST_DELAY)

    # Deduplicate by generic_name
    seen = set()
    unique_drugs = []
    for d in all_drugs:
        key = d["generic_name"].lower()
        if key and key not in seen:
            seen.add(key)
            unique_drugs.append(d)

    if unique_drugs:
        insert_drugs_bulk(unique_drugs)

    total = get_total_drugs()
    print("=" * 60)
    print(f"  Done! Total drugs in database: {total}")
    print("=" * 60)


if __name__ == "__main__":
    run()
