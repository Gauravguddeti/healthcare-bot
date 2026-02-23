"""
database.py — Local SQLite FTS5 knowledge base for the Healthcare Chatbot.
Stores medical text chunks AND drug/medicine info. Supports full-text search on both.
"""

import sqlite3
import os
import re
import shutil

_SRC_DB = os.path.join(os.path.dirname(__file__), "knowledge.db")

def _resolve_db_path() -> str:
    """
    On Vercel the deployed filesystem is read-only.
    Copy the pre-built DB to /tmp (writable) on first use.
    Locally, use the file in place.
    """
    if os.environ.get("VERCEL"):
        tmp_path = "/tmp/knowledge.db"
        if not os.path.exists(tmp_path) and os.path.exists(_SRC_DB):
            shutil.copy2(_SRC_DB, tmp_path)
        return tmp_path
    return _SRC_DB

DB_PATH = _resolve_db_path()


def get_connection():
    """Return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Create all tables and FTS5 virtual tables if they don't already exist.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # ─── Medical knowledge chunks table ────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            source_url TEXT,
            content TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            title,
            content,
            content='chunks',
            content_rowid='id'
        )
    """)

    cursor.executescript("""
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
            INSERT INTO chunks_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;
    """)

    # ─── Drugs / medicines table ───────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drugs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generic_name TEXT NOT NULL,
            brand_name TEXT,
            indications TEXT,
            description TEXT,
            warnings TEXT,
            adverse_reactions TEXT,
            drug_interactions TEXT,
            dosage_forms TEXT,
            source_url TEXT
        )
    """)

    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS drugs_fts USING fts5(
            generic_name,
            brand_name,
            indications,
            description,
            warnings,
            adverse_reactions,
            drug_interactions,
            content='drugs',
            content_rowid='id'
        )
    """)

    cursor.executescript("""
        CREATE TRIGGER IF NOT EXISTS drugs_ai AFTER INSERT ON drugs BEGIN
            INSERT INTO drugs_fts(rowid, generic_name, brand_name, indications,
                                  description, warnings, adverse_reactions, drug_interactions)
            VALUES (new.id, new.generic_name, new.brand_name, new.indications,
                    new.description, new.warnings, new.adverse_reactions, new.drug_interactions);
        END;

        CREATE TRIGGER IF NOT EXISTS drugs_ad AFTER DELETE ON drugs BEGIN
            INSERT INTO drugs_fts(drugs_fts, rowid, generic_name, brand_name, indications,
                                  description, warnings, adverse_reactions, drug_interactions)
            VALUES ('delete', old.id, old.generic_name, old.brand_name, old.indications,
                    old.description, old.warnings, old.adverse_reactions, old.drug_interactions);
        END;
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Database initialized at {DB_PATH}")


# ─── Chunk operations ─────────────────────────────────────────

def insert_chunk(title: str, source_url: str, content: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO chunks (title, source_url, content) VALUES (?, ?, ?)",
        (title, source_url, content),
    )
    conn.commit()
    conn.close()


def insert_chunks_bulk(chunks: list[dict]):
    conn = get_connection()
    conn.executemany(
        "INSERT INTO chunks (title, source_url, content) VALUES (:title, :source_url, :content)",
        chunks,
    )
    conn.commit()
    conn.close()
    print(f"[DB] Inserted {len(chunks)} chunks.")


# ─── Drug operations ──────────────────────────────────────────

def insert_drug(drug: dict):
    conn = get_connection()
    conn.execute(
        """INSERT INTO drugs (generic_name, brand_name, indications, description,
                              warnings, adverse_reactions, drug_interactions, dosage_forms, source_url)
           VALUES (:generic_name, :brand_name, :indications, :description,
                   :warnings, :adverse_reactions, :drug_interactions, :dosage_forms, :source_url)""",
        drug,
    )
    conn.commit()
    conn.close()


def insert_drugs_bulk(drugs: list[dict]):
    conn = get_connection()
    conn.executemany(
        """INSERT INTO drugs (generic_name, brand_name, indications, description,
                              warnings, adverse_reactions, drug_interactions, dosage_forms, source_url)
           VALUES (:generic_name, :brand_name, :indications, :description,
                   :warnings, :adverse_reactions, :drug_interactions, :dosage_forms, :source_url)""",
        drugs,
    )
    conn.commit()
    conn.close()
    print(f"[DB] Inserted {len(drugs)} drugs.")


# ─── Search ───────────────────────────────────────────────────

def _sanitize_fts_query(query: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", query)
    words = cleaned.split()
    if not words:
        return ""
    return " ".join(words)


def search(query: str, top_k: int = 5) -> list[dict]:
    """Search medical knowledge chunks."""
    conn = get_connection()
    cursor = conn.cursor()
    sanitized = _sanitize_fts_query(query)
    results = []

    if sanitized:
        try:
            cursor.execute(
                """SELECT c.id, c.title, c.source_url, c.content
                   FROM chunks_fts
                   JOIN chunks c ON chunks_fts.rowid = c.id
                   WHERE chunks_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (sanitized, top_k),
            )
            for row in cursor.fetchall():
                results.append({
                    "id": row["id"], "title": row["title"],
                    "source_url": row["source_url"], "content": row["content"],
                })
        except Exception:
            results = []

    if not results:
        cursor.execute(
            "SELECT id, title, source_url, content FROM chunks WHERE content LIKE ? OR title LIKE ? LIMIT ?",
            (f"%{query}%", f"%{query}%", top_k),
        )
        for row in cursor.fetchall():
            results.append({
                "id": row["id"], "title": row["title"],
                "source_url": row["source_url"], "content": row["content"],
            })

    conn.close()
    return results


def search_drugs(query: str, top_k: int = 5) -> list[dict]:
    """Search drug/medicine database."""
    conn = get_connection()
    cursor = conn.cursor()
    sanitized = _sanitize_fts_query(query)
    results = []

    if sanitized:
        try:
            cursor.execute(
                """SELECT d.id, d.generic_name, d.brand_name, d.indications,
                          d.description, d.warnings, d.adverse_reactions,
                          d.drug_interactions, d.dosage_forms, d.source_url
                   FROM drugs_fts
                   JOIN drugs d ON drugs_fts.rowid = d.id
                   WHERE drugs_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (sanitized, top_k),
            )
            for row in cursor.fetchall():
                results.append({
                    "id": row["id"],
                    "generic_name": row["generic_name"],
                    "brand_name": row["brand_name"],
                    "indications": row["indications"],
                    "description": row["description"],
                    "warnings": row["warnings"],
                    "adverse_reactions": row["adverse_reactions"],
                    "drug_interactions": row["drug_interactions"],
                    "dosage_forms": row["dosage_forms"],
                    "source_url": row["source_url"],
                })
        except Exception:
            results = []

    if not results:
        cursor.execute(
            """SELECT * FROM drugs
               WHERE generic_name LIKE ? OR brand_name LIKE ? OR indications LIKE ?
               LIMIT ?""",
            (f"%{query}%", f"%{query}%", f"%{query}%", top_k),
        )
        for row in cursor.fetchall():
            results.append(dict(row))

    conn.close()
    return results


def get_total_chunks() -> int:
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()
    return count


def get_total_drugs() -> int:
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM drugs").fetchone()[0]
    except Exception:
        count = 0
    conn.close()
    return count


if __name__ == "__main__":
    init_db()
    print(f"[DB] Total chunks: {get_total_chunks()}")
    print(f"[DB] Total drugs: {get_total_drugs()}")
