import os
import requests
from urllib.parse import urlparse

# ── Domains that publish promotional/advertorial content, not real buyer posts ──
BLOCKED_DOMAINS = {
    # Agency & directory sites
    "clutch.co", "goodfirms.co", "sortlist.com", "upcity.com", "expertise.com",
    "designrush.com", "agencyspotter.com", "toptal.com", "upwork.com",
    "freelancer.com", "bark.com", "thumbtack.com", "bark.com",
    # Article / blog farms that write "hire X" content
    "medium.com", "hubspot.com", "wordstream.com", "searchenginejournal.com",
    "searchengineland.com", "neilpatel.com", "semrush.com", "ahrefs.com",
    "moz.com", "forbes.com", "entrepreneur.com", "inc.com", "businessinsider.com",
    "thebalancemb.com", "indeed.com", "glassdoor.com",
    # Q&A sites that host agency self-promo (keep reddit/quora but filter per-result)
    "hireseospecialistagency.quora.com",  # subdomains used for promo
}

# ── Phrases that appear in promo/article titles but never in real buyer posts ──
PROMO_TITLE_SIGNALS = [
    "benefits of", "why hire", "reasons to hire", "how to hire", "guide to",
    "tips for hiring", "ultimate guide", "complete guide", "everything you need",
    "what is a", "how to choose", "top 10", "best practices", "case study",
    "we helped", "our services", "agency services", "pricing", "portfolio",
]

# ── Only question-style phrases that real humans use when looking to buy ──
BUYER_PHRASES = [
    # Direct requests
    f"looking for a {{kw}}",
    f"need a {{kw}}",
    f"need help with {{kw}}",
    f"anyone recommend a {{kw}}",
    f"can anyone recommend a {{kw}}",
    f"recommend a good {{kw}}",
    f"searching for a {{kw}}",
    f"hiring a {{kw}}",
    f"how do I find a {{kw}}",
    f"where can I find a {{kw}}",
    # Budget/intent signals
    f"budget for {{kw}}",
    f"how much does {{kw}} cost",
    f"affordable {{kw}}",
    f"{{kw}} for my business",
    f"{{kw}} for my website",
    f"{{kw}} for small business",
    f"looking to hire {{kw}}",
    # Problem / frustration signals — people who NEED your service
    f"my {{kw}} is not working",
    f"struggling with {{kw}}",
    f"bad experience with {{kw}}",
    f"failed {{kw}}",
    f"fired my {{kw}}",
    f"{{kw}} ruined my",
    f"wasted money on {{kw}}",
    f"can\'t find good {{kw}}",
    f"help with {{kw}} problem",
]

# ── Platforms where real humans post questions ──
PLATFORMS = [
    "site:reddit.com",
    "site:twitter.com",
    "site:x.com",
    "site:linkedin.com/posts",   # only actual posts, not company pages
    "site:quora.com/q",          # only question pages, not profile/blog subdomains
    "site:facebook.com/groups",  # only group posts
    "site:producthunt.com/discussions",
    "site:indiehackers.com",
]


def build_queries(keyword: str) -> list[str]:
    """
    Build question-style, platform-specific search queries.
    Uses tighter phrases that only match real human requests, not articles.
    """
    queries = []
    for platform in PLATFORMS:
        for phrase_template in BUYER_PHRASES:
            phrase = phrase_template.replace("{kw}", keyword)
            queries.append(f'{platform} "{phrase}"')
    return queries


def is_blocked(url: str, title: str) -> bool:
    """Return True if this result looks like promo/agency content, not a buyer post."""
    try:
        hostname = urlparse(url).hostname or ""
        # Strip www.
        hostname = hostname.replace("www.", "")

        # Block known promo domains
        if hostname in BLOCKED_DOMAINS:
            return True

        # Block any Quora subdomain (these are user blogs used for self-promo)
        if hostname.endswith(".quora.com") and hostname != "www.quora.com":
            return True

        # Block results whose titles look like articles/guides, not questions
        title_lower = (title or "").lower()
        if any(signal in title_lower for signal in PROMO_TITLE_SIGNALS):
            return True

    except Exception:
        pass

    return False


def search_web(query: str, serp_key_override: str = "") -> list[dict]:
    """
    Search via SerpAPI and pre-filter results to remove promo/agency pages
    before they ever reach the AI scorer.
    """
    api_key = serp_key_override.strip() or os.getenv("SERP_API_KEY", "")

    if not api_key:
        print("Warning: No SERP_API_KEY available.")
        return []

    try:
        response = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "api_key": api_key, "engine": "google", "num": 10},
            timeout=10,
        )
        response.raise_for_status()
        raw_results = response.json().get("organic_results", [])

        # Pre-filter: remove promo/agency results before AI scoring
        clean = []
        for r in raw_results:
            url   = r.get("link", "")
            title = r.get("title", "")
            if not is_blocked(url, title):
                clean.append(r)
            else:
                print(f"  Filtered promo result: {title[:60]}")

        return clean

    except requests.RequestException as e:
        print(f"Search error for '{query}': {e}")
        return []
