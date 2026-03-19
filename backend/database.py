import sqlite3
import threading

_lock = threading.Lock()

DB_PATH = "leads.db"

def _get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post TEXT NOT NULL,
            url TEXT NOT NULL,
            intent REAL NOT NULL,
            keyword TEXT DEFAULT '',
            post_date TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Add columns if upgrading from old schema
    for col, definition in [
        ("keyword", "TEXT DEFAULT ''"),
        ("post_date", "TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {col} {definition}")
            conn.commit()
        except Exception:
            pass  # Column already exists
    conn.commit()
    return conn


def save_lead(post: str, url: str, intent: float, keyword: str = "", post_date: str = ""):
    with _lock:
        try:
            conn = _get_connection()
            # Deduplicate — skip if same URL already saved today
            existing = conn.execute(
                "SELECT id FROM leads WHERE url = ? AND date(created_at) = date('now')",
                (url,)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO leads (post, url, intent, keyword, post_date) VALUES (?, ?, ?, ?, ?)",
                    (post, url, intent, keyword, post_date),
                )
                conn.commit()
            conn.close()
        except Exception as e:
            print(f"Database save error: {e}")


def get_all_leads() -> list[tuple]:
    with _lock:
        try:
            conn = _get_connection()
            rows = conn.execute(
                "SELECT id, post, url, intent, created_at, keyword, post_date FROM leads ORDER BY created_at DESC"
            ).fetchall()
            conn.close()
            return rows
        except Exception as e:
            print(f"Database read error: {e}")
            return []


def get_keywords() -> list[str]:
    """Get tracked keywords stored in DB (set from frontend Settings)."""
    with _lock:
        try:
            conn = _get_connection()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'keywords'"
            ).fetchone()
            conn.close()
            if row and row[0]:
                return [k.strip() for k in row[0].split('\n') if k.strip()]
            return []
        except Exception as e:
            print(f"Database get_keywords error: {e}")
            return []


def save_keywords(keywords: list[str]):
    """Save tracked keywords to DB from frontend Settings."""
    with _lock:
        try:
            conn = _get_connection()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('keywords', ?)",
                ('\n'.join(keywords),)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Database save_keywords error: {e}")
