import sqlite3
import threading

# ✅ FIX: Use a lock for thread safety — scanner thread + API thread both write to DB
_lock = threading.Lock()

# ✅ NOTE: On Render's free tier, the filesystem is ephemeral (data resets on redeploy).
# For persistent storage, replace SQLite with PostgreSQL (e.g. via Render's managed DB
# or Supabase free tier) and use the 'psycopg2' library instead.
DB_PATH = "leads.db"


def _get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post TEXT NOT NULL,
            url TEXT NOT NULL,
            intent REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def save_lead(post: str, url: str, intent: float):
    with _lock:
        try:
            conn = _get_connection()
            conn.execute(
                "INSERT INTO leads (post, url, intent) VALUES (?, ?, ?)",
                (post, url, intent),
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
                "SELECT id, post, url, intent, created_at FROM leads ORDER BY intent DESC"
            ).fetchall()
            conn.close()
            return rows
        except Exception as e:
            print(f"Database read error: {e}")
            return []
