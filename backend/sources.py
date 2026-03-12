"""
sources.py — Multi-source free search engine

Priority order (free first, SerpAPI last):
  1. Reddit API        — official, free, no key needed, best quality
  2. RSS feeds         — Reddit + Quora + forums, completely free
  3. DuckDuckGo HTML   — free scrape, no API key needed
  4. SerpAPI           — paid fallback, only used if above return nothing

Each source returns a standard list of dicts:
  { snippet, link, title, source_name }
"""

import os
import re
import time
import requests
from urllib.parse import quote_plus, urljoin
from xml.etree import ElementTree

HEADERS = {
    "User-Agent": "LeadRadar/1.0 (lead research tool; contact via github)"
}

# ══════════════════════════════════════════════════════════════════════════════
# 1. REDDIT API  (completely free, official JSON API, no key needed)
# ══════════════════════════════════════════════════════════════════════════════

# Subreddits most likely to have buyer-intent posts
BUYER_SUBREDDITS = [
    "entrepreneur", "smallbusiness", "startups", "business",
    "marketing", "digital_marketing", "SEO", "PPC", "webdev",
    "Wordpress", "ecommerce", "dropshipping", "freelance",
    "hiring", "forhire", "jobs", "slavelabour",
    "socialmedia", "content_marketing", "copywriting",
    "realestate", "personalfinance", "homeimprovement",
    "legaladvice", "accounting",
]

def search_reddit(keyword: str, limit: int = 25) -> list[dict]:
    """
    Search Reddit using the official free JSON API.
    No API key required. Searches posts + comments.
    """
    results = []

    # Search across all of Reddit
    try:
        url = f"https://www.reddit.com/search.json"
        params = {
            "q": keyword,
            "sort": "new",
            "limit": limit,
            "type": "link",
            "t": "month",
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()

        for post in data.get("data", {}).get("children", []):
            p = post.get("data", {})
            text  = p.get("selftext", "") or p.get("title", "")
            title = p.get("title", "")
            link  = f"https://reddit.com{p.get('permalink', '')}"
            sub   = p.get("subreddit", "reddit")

            if text and len(text.strip()) > 20:
                results.append({
                    "snippet":     (text[:500] if len(text) > 500 else text),
                    "title":       title,
                    "link":        link,
                    "source_name": f"reddit/r/{sub}",
                })

    except Exception as e:
        print(f"Reddit search error: {e}")

    # Also search top buyer subreddits directly
    for subreddit in BUYER_SUBREDDITS[:8]:  # limit to 8 to avoid rate limits
        try:
            url = f"https://www.reddit.com/r/{subreddit}/search.json"
            params = {"q": keyword, "restrict_sr": "1", "sort": "new", "limit": 10, "t": "month"}
            r = requests.get(url, params=params, headers=HEADERS, timeout=8)
            if r.status_code == 429:
                time.sleep(2)
                continue
            r.raise_for_status()
            data = r.json()

            for post in data.get("data", {}).get("children", []):
                p = post.get("data", {})
                text  = p.get("selftext", "") or p.get("title", "")
                title = p.get("title", "")
                link  = f"https://reddit.com{p.get('permalink', '')}"

                if text and len(text.strip()) > 20:
                    results.append({
                        "snippet":     text[:500],
                        "title":       title,
                        "link":        link,
                        "source_name": f"reddit/r/{subreddit}",
                    })

            time.sleep(0.5)  # Be polite to Reddit's API

        except Exception as e:
            print(f"Reddit r/{subreddit} error: {e}")
            continue

    # Deduplicate by link
    seen = set()
    unique = []
    for r in results:
        if r["link"] not in seen:
            seen.add(r["link"])
            unique.append(r)

    return unique


# ══════════════════════════════════════════════════════════════════════════════
# 2. RSS FEEDS  (Reddit, Quora, various forums — completely free)
# ══════════════════════════════════════════════════════════════════════════════

RSS_FEEDS = [
    # Reddit RSS for buyer-intent subreddits
    "https://www.reddit.com/r/entrepreneur/search.rss?q={kw}&sort=new&restrict_sr=1",
    "https://www.reddit.com/r/smallbusiness/search.rss?q={kw}&sort=new&restrict_sr=1",
    "https://www.reddit.com/r/forhire/search.rss?q={kw}&sort=new&restrict_sr=1",
    "https://www.reddit.com/r/hiring/search.rss?q={kw}&sort=new&restrict_sr=1",
    "https://www.reddit.com/r/SEO/search.rss?q={kw}&sort=new&restrict_sr=1",
    "https://www.reddit.com/r/digital_marketing/search.rss?q={kw}&sort=new&restrict_sr=1",
    # Quora RSS (search results)
    "https://www.quora.com/search?q={kw}&type=question&format=rss",
    # Hacker News (good for tech/startup leads)
    "https://hn.algolia.com/api/v1/search_by_date?query={kw}&tags=ask_hn&hitsPerPage=10",
]

def search_rss(keyword: str) -> list[dict]:
    """
    Pull from RSS feeds — Reddit, Quora, Hacker News.
    Completely free, no rate limits worth worrying about.
    """
    results = []
    kw_encoded = quote_plus(keyword)

    for feed_template in RSS_FEEDS:
        url = feed_template.replace("{kw}", kw_encoded)

        try:
            # Hacker News uses JSON API, not RSS
            if "hn.algolia.com" in url:
                r = requests.get(url, headers=HEADERS, timeout=8)
                r.raise_for_status()
                data = r.json()
                for hit in data.get("hits", []):
                    text  = hit.get("story_text") or hit.get("title") or ""
                    title = hit.get("title", "")
                    link  = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID','')}"
                    if text:
                        results.append({
                            "snippet":     text[:500],
                            "title":       title,
                            "link":        link,
                            "source_name": "hackernews",
                        })
                continue

            # Standard RSS/Atom parsing
            r = requests.get(url, headers=HEADERS, timeout=8)
            r.raise_for_status()

            # Parse XML
            root = ElementTree.fromstring(r.content)
            ns   = {"atom": "http://www.w3.org/2005/Atom"}

            # Try RSS format first
            items = root.findall(".//item")
            if not items:
                # Try Atom format
                items = root.findall(".//atom:entry", ns) or root.findall(".//entry")

            for item in items[:10]:
                def txt(tag, alt=""):
                    el = item.find(tag) or item.find(f"atom:{tag}", ns)
                    return (el.text or "").strip() if el is not None else alt

                title   = txt("title")
                link_el = item.find("link") or item.find("atom:link", ns)
                link    = ""
                if link_el is not None:
                    link = link_el.get("href") or link_el.text or ""
                desc    = txt("description") or txt("summary") or txt("content")

                # Strip HTML tags from description
                desc = re.sub(r"<[^>]+>", " ", desc).strip()
                desc = re.sub(r"\s+", " ", desc)

                source = "quora" if "quora" in url else "reddit-rss"

                if (title or desc) and link:
                    results.append({
                        "snippet":     (desc[:500] if desc else title),
                        "title":       title,
                        "link":        link,
                        "source_name": source,
                    })

            time.sleep(0.3)

        except Exception as e:
            print(f"RSS feed error ({url[:50]}): {e}")
            continue

    # Deduplicate
    seen = set()
    unique = []
    for r in results:
        if r["link"] not in seen:
            seen.add(r["link"])
            unique.append(r)

    return unique


# ══════════════════════════════════════════════════════════════════════════════
# 3. DUCKDUCKGO HTML SCRAPE  (free, no key needed)
# ══════════════════════════════════════════════════════════════════════════════

DDG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def _parse_ddg_html(html: str, source_label: str) -> list[dict]:
    """Shared DDG HTML parser — extracts results from DuckDuckGo lite HTML."""
    from urllib.parse import unquote
    results = []

    title_pattern   = re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)
    snippet_pattern = re.compile(r'class="result__snippet"[^>]*>([^<]+(?:<[^>]+>[^<]*</[^>]+>[^<]*)*)</a>', re.IGNORECASE)

    titles   = title_pattern.findall(html)
    snippets = [re.sub(r"<[^>]+>", "", s).strip() for s in snippet_pattern.findall(html)]

    for i, (link, title) in enumerate(titles[:15]):
        snippet = snippets[i] if i < len(snippets) else title
        if link.startswith("//duckduckgo.com/l/?"):
            uddg_match = re.search(r"uddg=([^&]+)", link)
            if uddg_match:
                link = unquote(uddg_match.group(1))
        if link and (title or snippet):
            results.append({
                "snippet":     snippet[:500],
                "title":       title.strip(),
                "link":        link,
                "source_name": source_label,
            })
    return results


def _ddg_post(query: str) -> str:
    """Make a single DuckDuckGo lite POST request, return raw HTML."""
    r = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query, "b": "", "kl": "us-en"},
        headers=DDG_HEADERS,
        timeout=12,
    )
    r.raise_for_status()
    return r.text


def search_duckduckgo(query: str) -> list[dict]:
    """
    Scrape DuckDuckGo for general web results — free, no API key required.
    """
    try:
        return _parse_ddg_html(_ddg_post(query), "duckduckgo")
    except Exception as e:
        print(f"DuckDuckGo scrape error: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# 3b. FACEBOOK via DuckDuckGo  (free — searches public Facebook posts via DDG)
# ══════════════════════════════════════════════════════════════════════════════

# Buyer-intent phrase templates specifically for Facebook public posts
FB_BUYER_PHRASES = [
    'site:facebook.com "looking for {kw}"',
    'site:facebook.com "need {kw}"',
    'site:facebook.com "anyone recommend" "{kw}"',
    'site:facebook.com "recommend a {kw}"',
    'site:facebook.com "struggling with {kw}"',
    'site:facebook.com/groups "looking for {kw}"',
    'site:facebook.com/groups "need {kw}"',
    'site:facebook.com/groups "recommend" "{kw}"',
]

def search_facebook_ddg(keyword: str) -> list[dict]:
    """
    Search public Facebook posts and groups via DuckDuckGo site: operator.
    Completely free — no API key, no token required.
    Finds public posts where people are asking for recommendations or help.
    """
    results = []

    for template in FB_BUYER_PHRASES:
        query = template.replace("{kw}", keyword)
        try:
            html = _ddg_post(query)
            hits = _parse_ddg_html(html, "facebook/ddg")
            # Only keep results that actually link to facebook.com
            fb_hits = [h for h in hits if "facebook.com" in h.get("link", "")]
            results.extend(fb_hits)
            time.sleep(0.6)  # Be polite to DDG
        except Exception as e:
            print(f"Facebook DDG error ('{query[:40]}'): {e}")
            continue

    # Deduplicate
    seen = set()
    unique = []
    for r in results:
        if r["link"] not in seen:
            seen.add(r["link"])
            unique.append(r)

    return unique


# ══════════════════════════════════════════════════════════════════════════════
# 4. SERPAPI FALLBACK  (only used when free sources return < MIN_FREE_RESULTS)
#    Includes a Facebook-specific engine pass for extra coverage
# ══════════════════════════════════════════════════════════════════════════════

MIN_FREE_RESULTS = 5  # Only call SerpAPI if free sources found fewer than this

def search_serpapi(query: str, api_key: str, engine: str = "google") -> list[dict]:
    """SerpAPI — paid fallback. Supports google and facebook engines."""
    if not api_key:
        return []
    try:
        params = {"q": query, "api_key": api_key, "engine": engine, "num": 10}
        r = requests.get("https://serpapi.com/search", params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        # Google engine returns organic_results
        if engine == "google":
            raw = data.get("organic_results", [])
            return [{
                "snippet":     item.get("snippet", ""),
                "title":       item.get("title", ""),
                "link":        item.get("link", ""),
                "source_name": "google/serpapi",
            } for item in raw]

        # Facebook engine returns organic_results with posts
        elif engine == "facebook":
            raw = data.get("organic_results", [])
            return [{
                "snippet":     item.get("snippet", "") or item.get("description", ""),
                "title":       item.get("title", "") or item.get("author", {}).get("name", ""),
                "link":        item.get("link", "") or item.get("url", ""),
                "source_name": "facebook/serpapi",
            } for item in raw if item.get("link") or item.get("url")]

    except Exception as e:
        print(f"SerpAPI error (engine={engine}): {e}")
        return []


def search_facebook_serpapi(keyword: str, api_key: str) -> list[dict]:
    """
    Use SerpAPI's Facebook engine to search public Facebook posts.
    Only called as a fallback when DDG Facebook search returns too little.
    Costs ~3 SerpAPI credits (one query per buyer phrase).
    """
    if not api_key:
        return []

    results = []
    fb_queries = [
        f"looking for {keyword}",
        f"need {keyword}",
        f"recommend {keyword}",
    ]
    for q in fb_queries:
        hits = search_serpapi(q, api_key, engine="facebook")
        results.extend(hits)

    # Deduplicate
    seen = set()
    unique = []
    for r in results:
        if r["link"] not in seen:
            seen.add(r["link"])
            unique.append(r)

    return unique


# ══════════════════════════════════════════════════════════════════════════════
# UNIFIED SEARCH — tries all sources, deduplicates, returns combined results
# ══════════════════════════════════════════════════════════════════════════════

def multi_search(keyword: str, serp_key: str = "") -> list[dict]:
    """
    Search all sources in priority order:
      1. Reddit API        (free — official API, best quality)
      2. RSS feeds         (free — Reddit, Quora, Hacker News)
      3. DuckDuckGo        (free — general web buyer-intent queries)
      3b. Facebook via DDG (free — site:facebook.com buyer-intent queries)
      4. SerpAPI Google    (paid fallback — general web)
      4b. SerpAPI Facebook (paid fallback — Facebook engine, ~3 credits)

    SerpAPI is ONLY called when free sources return fewer than MIN_FREE_RESULTS.
    Returns deduplicated list with standard fields.
    """
    all_results = []
    seen_links  = set()

    def add_results(new_results: list[dict]):
        for r in new_results:
            link = r.get("link", "")
            if link and link not in seen_links:
                seen_links.add(link)
                all_results.append(r)

    print(f"[Search] Keyword: '{keyword}'")

    # 1. Reddit (free)
    reddit_results = search_reddit(keyword)
    add_results(reddit_results)
    print(f"[Search] Reddit: {len(reddit_results)} results")

    # 2. RSS (free)
    rss_results = search_rss(keyword)
    add_results(rss_results)
    print(f"[Search] RSS: {len(rss_results)} results")

    # 3. DuckDuckGo general (free)
    ddg_queries = [
        f"looking for {keyword}",
        f"need {keyword} help",
        f"recommend {keyword}",
        f"struggling with {keyword}",
    ]
    for q in ddg_queries:
        add_results(search_duckduckgo(q))
        time.sleep(0.5)
    print(f"[Search] DuckDuckGo general: {len(all_results)} total so far")

    # 3b. Facebook via DuckDuckGo (free)
    fb_ddg_results = search_facebook_ddg(keyword)
    add_results(fb_ddg_results)
    print(f"[Search] Facebook (DDG): {len(fb_ddg_results)} results")

    # 4. SerpAPI fallbacks (paid) — only if free sources didn't find enough
    if len(all_results) < MIN_FREE_RESULTS and serp_key:
        print(f"[Search] Only {len(all_results)} free results — activating SerpAPI fallback")

        # 4a. SerpAPI Google for Reddit/Quora
        serp_queries = [
            f'site:reddit.com "looking for {keyword}"',
            f'site:reddit.com "need {keyword}"',
            f'site:quora.com "{keyword}"',
        ]
        for q in serp_queries:
            add_results(search_serpapi(q, serp_key, engine="google"))

        # 4b. SerpAPI Facebook engine
        print("[Search] SerpAPI Facebook engine fallback…")
        add_results(search_facebook_serpapi(keyword, serp_key))

    elif not serp_key:
        print("[Search] No SerpAPI key — free sources only")
    else:
        print(f"[Search] Free sources sufficient ({len(all_results)} results) — SerpAPI skipped")

    print(f"[Search] Total unique results: {len(all_results)}")
    return all_results
