import os
import time
from sources import multi_search
from extractor import extract_leads
from intent_ai import score_intent
from database import save_lead

TRACKED_KEYWORDS = [
    "seo agency",
    "web designer",
    "social media manager",
]

SCAN_INTERVAL_SECONDS = 7200  # 2 hours between scans


def scan_once():
    print("🔍 Scanner: Starting scan cycle...")
    serp_key    = os.getenv("SERP_API_KEY", "")
    total_found = 0

    for keyword in TRACKED_KEYWORDS:
        try:
            # Use free sources only — pass empty serp_key to never touch SerpAPI
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
                            save_lead(lead["post_text"], lead["post_url"], score)
                            total_found += 1
                            print(f"✅ [{keyword}] {score}: {lead['post_text'][:80]}")
                except Exception as e:
                    print(f"Scanner scoring error: {e}")
                    continue

        except Exception as e:
            print(f"Scanner keyword error '{keyword}': {e}")
            continue

    print(f"✅ Scanner done. {total_found} leads saved.")


def run_scanner():
    print("🚀 Background scanner started (free sources only, no SerpAPI).")
    # Wait 10 minutes before first scan so server starts up cleanly
    time.sleep(600)
    while True:
        try:
            scan_once()
        except Exception as e:
            print(f"❌ Scanner cycle failed: {e}")
        print(f"⏳ Next scan in {SCAN_INTERVAL_SECONDS // 60} minutes.")
        time.sleep(SCAN_INTERVAL_SECONDS)
