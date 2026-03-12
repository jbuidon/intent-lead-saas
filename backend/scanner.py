import time
from search_engine import build_queries, search_web
from extractor import extract_leads
from intent_ai import score_intent
from database import save_lead

# Add or edit keywords you want to track here
TRACKED_KEYWORDS = [
    "seo agency",
    "ai receptionist",
    "roof repair",
    "marketing agency",
    "web designer",
    "social media manager",
]

# How often to scan (seconds). 3600 = every 1 hour.
SCAN_INTERVAL_SECONDS = 3600


def scan_once():
    """Run one full scan cycle across all keywords."""
    print("🔍 Scanner: Starting scan cycle...")

    total_found = 0

    for keyword in TRACKED_KEYWORDS:
        queries = build_queries(keyword)

        for query in queries:
            try:
                results = search_web(query)
                leads = extract_leads(results)

                for lead in leads:
                    score = score_intent(lead["post_text"])

                    if score >= 7:
                        save_lead(lead["post_text"], lead["post_url"], score)
                        total_found += 1
                        print(f"✅ Buyer detected [{keyword}] Intent: {score}")
                        print(f"   {lead['post_text'][:100]}...")

            except Exception as e:
                print(f"Scanner error on query '{query}': {e}")
                continue  # ✅ FIX: Don't let one failed query crash the whole scan

    print(f"✅ Scanner: Cycle complete. {total_found} leads found.")


def run_scanner():
    """
    Runs continuously in a background thread.
    ✅ FIX: Original had bare while True with no error catching — one crash would
    silently kill the thread. This version catches all exceptions and keeps going.
    """
    print("🚀 Background scanner started.")

    while True:
        try:
            scan_once()
        except Exception as e:
            print(f"❌ Scanner cycle failed: {e}")

        print(f"⏳ Next scan in {SCAN_INTERVAL_SECONDS // 60} minutes.")
        time.sleep(SCAN_INTERVAL_SECONDS)
