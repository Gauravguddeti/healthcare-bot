"""
scraper.py — Scrapes public MedlinePlus health topic pages and stores
the extracted text into the local SQLite FTS5 knowledge base.

MedlinePlus is a service of the National Library of Medicine (NLM)
and provides freely available health information for the public.

Usage:
    python scraper.py
"""

import re
import time
import requests
from bs4 import BeautifulSoup
from database import init_db, insert_chunks_bulk, get_total_chunks

# ─── Configuration ──────────────────────────────────────────────────
BASE_URL = "https://medlineplus.gov"

# MedlinePlus organizes topics A-Z across separate letter pages.
LETTER_PAGES = [
    f"{BASE_URL}/healthtopics_{letter}.html"
    for letter in "abcdefghijklmnopqrstuvw"
] + [f"{BASE_URL}/healthtopics_xyz.html"]

MAX_TOPICS = 500  # Expanded for broader medical coverage
CHUNK_MAX_CHARS = 1500  # Max chars per knowledge chunk
REQUEST_DELAY = 0.4  # Polite delay between requests (seconds)
HEADERS = {
    "User-Agent": "HealthcareChatbot-StudentProject/1.0 (educational use only)"
}


def get_topic_links() -> list[dict]:
    """
    Iterate through the A-Z letter pages on MedlinePlus and
    collect individual topic page links and titles.
    """
    print("[Scraper] Fetching topic index (A-Z letter pages)...")
    topics_seen = set()
    topics = []

    for page_url in LETTER_PAGES:
        if len(topics) >= MAX_TOPICS:
            break

        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [WARN] Could not fetch {page_url}: {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Each topic is an <a> inside the main list. We look for
        # links that point to medlineplus.gov/<topic>.html
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            title = a_tag.get_text(strip=True)

            # Only pick direct topic pages (not category or external links)
            if (
                title
                and len(title) > 2
                and href.startswith("https://medlineplus.gov/")
                and href.endswith(".html")
                and "/healthtopics" not in href
                and "/lab-tests/" not in href
                and "/genetics/" not in href
                and "/druginfo/" not in href
                and href not in topics_seen
            ):
                topics_seen.add(href)
                topics.append({"title": title, "url": href})

            if len(topics) >= MAX_TOPICS:
                break

        time.sleep(REQUEST_DELAY)

    print(f"[Scraper] Collected {len(topics)} unique topic links.")
    return topics


def scrape_topic_page(url: str) -> str:
    """
    Given a MedlinePlus topic URL, extract the main summary text.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [WARN] Failed to fetch {url}: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # MedlinePlus topic summaries live in <div id="topic-summary">
    content_div = (
        soup.find("div", {"id": "topic-summary"})
        or soup.find("article")
        or soup.find("main")
    )

    if not content_div:
        return ""

    # Remove script and style tags
    for tag in content_div.find_all(["script", "style", "nav"]):
        tag.decompose()

    text = content_div.get_text(separator="\n", strip=True)
    # Clean excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, title: str, source_url: str) -> list[dict]:
    """
    Split a long text into smaller chunks within CHUNK_MAX_CHARS.
    Splits on paragraph boundaries to maintain readability.
    """
    if not text:
        return []

    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current_chunk) + len(para) + 2 > CHUNK_MAX_CHARS and current_chunk:
            chunks.append({
                "title": title,
                "source_url": source_url,
                "content": current_chunk.strip(),
            })
            current_chunk = para
        else:
            current_chunk += ("\n\n" + para) if current_chunk else para

    if current_chunk.strip():
        chunks.append({
            "title": title,
            "source_url": source_url,
            "content": current_chunk.strip(),
        })

    return chunks


def run_scraper():
    """Main scraping pipeline."""
    print("=" * 60)
    print("  Healthcare Chatbot — MedlinePlus Scraper")
    print("=" * 60)

    # 1. Initialize the database
    init_db()

    # 2. Get topic links from A-Z pages
    topics = get_topic_links()
    if not topics:
        print("[Scraper] No topics found. Exiting.")
        return

    # 3. Scrape each topic and build chunks
    all_chunks = []
    for i, topic in enumerate(topics):
        print(f"[Scraper] ({i + 1}/{len(topics)}) Scraping: {topic['title']}...")
        text = scrape_topic_page(topic["url"])
        if text:
            chunks = chunk_text(text, topic["title"], topic["url"])
            all_chunks.extend(chunks)
        time.sleep(REQUEST_DELAY)

    # 4. Bulk insert all chunks
    if all_chunks:
        insert_chunks_bulk(all_chunks)

    total = get_total_chunks()
    print("=" * 60)
    print(f"  Scraping complete! Total chunks in database: {total}")
    print("=" * 60)


if __name__ == "__main__":
    run_scraper()
