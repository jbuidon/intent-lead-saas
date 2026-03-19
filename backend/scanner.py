import os
import time
import datetime
from sources import multi_search
from extractor import extract_leads
from intent_ai import score_intent
from database import save_lead, get_keywords

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

    # Load keywords from DB (set via Settings page) — fall back to defaults
    keywords = get_keywords()
    if not keywords:
        keywords = DEFAULT_KEYWORDS
        print(f"[Scanner] No keywords in DB, using defaults: {keywords}")
    else:
        print(f"[Scanner] Keywords from settings: {keywords}")

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
                        if score >= 7:
                            save_lead(lead["post_text"], lead["post_url"], score, keyword=keyword)
                            total_found += 1
                            print(f"✅ [{keyword}] {score}: {lead['post_text'][:80]}")
                except Exception as e:
                    print(f"Scanner scoring error: {e}")
                    continue

        except Exception as e:
            print(f"Scanner keyword error '{keyword}': {e}")
            continue

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
