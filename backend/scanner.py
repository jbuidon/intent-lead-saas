import os
import time
import datetime
from sources import multi_search
from extractor import extract_leads
from intent_ai import score_intent
from database import save_lead, get_keywords, get_setting

# Fallback keywords if none saved in DB yet
DEFAULT_KEYWORDS = [
    "seo agency",
    "web designer",
    "social media manager",
    "google ads",
    "ai receptionist",
]

SCAN_INTERVAL_SECONDS = 7200  # 2 hours between scans

# Shared state — readable via /scanner/status endpoint
scanner_state = {
    "status": "starting",     # starting | running | waiting | error
    "last_run": None,         # ISO timestamp
    "next_run": None,         # ISO timestamp
    "leads_found_last": 0,
    "keywords": [],
    "error": None,
}


def scan_once():
    global scanner_state
    print("🔍 Scanner: Starting scan cycle...")

    # Load keywords: DB first → TRACKED_KEYWORDS env var → hardcoded defaults
    keywords = get_keywords()
    if not keywords:
        env_kw = os.environ.get("TRACKED_KEYWORDS", "")
        if env_kw:
            keywords = [k.strip() for k in env_kw.split(",") if k.strip()]
            print(f"[Scanner] Keywords from env var: {keywords}")
        else:
            keywords = DEFAULT_KEYWORDS
            print(f"[Scanner] No keywords in DB or env, using defaults: {keywords}")
    else:
        print(f"[Scanner] Keywords from settings: {keywords}")

    # Load min_score: DB setting → env var → default 5
    try:
        min_score = float(get_setting("min_score", "") or os.environ.get("MIN_SCORE", "5"))
    except ValueError:
        min_score = 5.0
    print(f"[Scanner] Min intent score: {min_score}")

    scanner_state["status"] = "running"
    scanner_state["keywords"] = keywords
    scanner_state["error"] = None

    total_found = 0

    for keyword in keywords:
        try:
            results = multi_search(keyword, serp_key="")
            print(f"[Scanner] '{keyword}': {len(results)} results from free sources")

            for result in results:
                try:
                    extracted = extract_leads([{
                        "snippet": result.get("snippet", ""),
                        "link":    result.get("link", ""),
                        "title":   result.get("title", ""),
                    }])
                    for lead in extracted:
                        score = score_intent(lead["post_text"])
                        if score >= min_score:
                            save_lead(lead["post_text"], lead["post_url"], score, keyword=keyword, post_date=result.get("post_date", ""))
                            total_found += 1
                            print(f"✅ [{keyword}] {score}: {lead['post_text'][:80]}")
                except Exception as e:
                    print(f"Scanner scoring error: {e}")
                    continue

        except Exception as e:
            print(f"Scanner keyword error '{keyword}': {e}")
            continue

        # Wait between keywords to avoid DDG rate limiting on Render
        if keyword != keywords[-1]:
            print(f"[Scanner] Waiting 60s before next keyword (DDG rate limit protection)...")
            time.sleep(60)

    now = datetime.datetime.utcnow()
    next_run = now + datetime.timedelta(seconds=SCAN_INTERVAL_SECONDS)
    scanner_state["last_run"] = now.isoformat() + "Z"
    scanner_state["next_run"] = next_run.isoformat() + "Z"
    scanner_state["leads_found_last"] = total_found
    scanner_state["status"] = "waiting"
    print(f"✅ Scanner done. {total_found} leads saved.")


def run_scanner():
    global scanner_state
    print("🚀 Background scanner started (free sources only, no SerpAPI).")
    scanner_state["status"] = "waiting"
    next_run = datetime.datetime.utcnow() + datetime.timedelta(seconds=600)
    scanner_state["next_run"] = next_run.isoformat() + "Z"
    time.sleep(600)  # Wait 10 min for server startup
    while True:
        try:
            scan_once()
        except Exception as e:
            scanner_state["status"] = "error"
            scanner_state["error"] = str(e)
            print(f"❌ Scanner cycle failed: {e}")
        print(f"⏳ Next scan in {SCAN_INTERVAL_SECONDS // 60} minutes.")
        time.sleep(SCAN_INTERVAL_SECONDS)
