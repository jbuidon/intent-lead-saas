"""
sources.py — Multi-source free search engine

Priority order (free first, SerpAPI last):
  1. Reddit API        — official, free, no key needed, best quality
  2. RSS feeds         — Reddit + Quora + forums, completely free
  3. DuckDuckGo HTML   — free scrape, no API key needed
  4. Facebook Groups   — targeted site:facebook.com/groups queries via DDG
  5. SerpAPI           — paid fallback, only used if above return nothing

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
    results = []

    try:
        url = f"https://www.reddit.com/search.json"
        params = {
            "q": keyword,
            "sort": "new",
            "limit": limit,
            "type": "link",
            "t": "week",
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
                import datetime
                created_utc = p.get("created_utc")
                post_date = datetime.datetime.utcfromtimestamp(created_utc).isoformat() + "Z" if created_utc else ""
                results.append({
                    "snippet":     (text[:500] if len(text) > 500 else text),
                    "title":       title,
                    "link":        link,
                    "source_name": f"reddit/r/{sub}",
                    "post_date":   post_date,
                })

    except Exception as e:
        print(f"Reddit search error: {e}")

    for subreddit in BUYER_SUBREDDITS[:8]:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/search.json"
            params = {"q": keyword, "restrict_sr": "1", "sort": "new", "limit": 10, "t": "week"}
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
                    import datetime
                    created_utc = p.get("created_utc")
                    post_date = datetime.datetime.utcfromtimestamp(created_utc).isoformat() + "Z" if created_utc else ""
                    results.append({
                        "snippet":     text[:500],
                        "title":       title,
                        "link":        link,
                        "source_name": f"reddit/r/{subreddit}",
                        "post_date":   post_date,
                    })

            time.sleep(0.5)

        except Exception as e:
            print(f"Reddit r/{subreddit} error: {e}")
            continue

    seen = set()
    unique = []
    for r in results:
        if r["link"] not in seen:
            seen.add(r["link"])
            unique.append(r)

    return unique


# ══════════════════════════════════════════════════════════════════════════════
# 2. RSS FEEDS
# ══════════════════════════════════════════════════════════════════════════════

RSS_FEEDS = [
    "https://www.reddit.com/r/entrepreneur/search.rss?q={kw}&sort=new&restrict_sr=1",
    "https://www.reddit.com/r/smallbusiness/search.rss?q={kw}&sort=new&restrict_sr=1",
    "https://www.reddit.com/r/forhire/search.rss?q={kw}&sort=new&restrict_sr=1",
    "https://www.reddit.com/r/hiring/search.rss?q={kw}&sort=new&restrict_sr=1",
    "https://www.reddit.com/r/SEO/search.rss?q={kw}&sort=new&restrict_sr=1",
    "https://www.reddit.com/r/digital_marketing/search.rss?q={kw}&sort=new&restrict_sr=1",
    "https://www.quora.com/search?q={kw}&type=question&format=rss",
    "https://hn.algolia.com/api/v1/search_by_date?query={kw}&tags=ask_hn&hitsPerPage=10",
]

def search_rss(keyword: str) -> list[dict]:
    results = []
    kw_encoded = quote_plus(keyword)

    for feed_template in RSS_FEEDS:
        url = feed_template.replace("{kw}", kw_encoded)

        try:
            if "hn.algolia.com" in url:
                r = requests.get(url, headers=HEADERS, timeout=8)
                r.raise_for_status()
                data = r.json()
                for hit in data.get("hits", []):
                    text  = hit.get("story_text") or hit.get("title") or ""
                    title = hit.get("title", "")
                    link  = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID','')}"
                    post_date = hit.get("created_at", "")
                    if text:
                        results.append({
                            "snippet":     text[:500],
                            "title":       title,
                            "link":        link,
                            "source_name": "hackernews",
                            "post_date":   post_date,
                        })
                continue

            r = requests.get(url, headers=HEADERS, timeout=8)
            r.raise_for_status()

            root = ElementTree.fromstring(r.content)
            ns   = {"atom": "http://www.w3.org/2005/Atom"}

            items = root.findall(".//item")
            if not items:
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

                desc = re.sub(r"<[^>]+>", " ", desc).strip()
                desc = re.sub(r"\s+", " ", desc)

                source = "quora" if "quora" in url else "reddit-rss"
                pub_date = txt("pubDate") or txt("updated") or txt("published") or ""

                if (title or desc) and link:
                    results.append({
                        "snippet":     (desc[:500] if desc else title),
                        "title":       title,
                        "link":        link,
                        "source_name": source,
                        "post_date":   pub_date,
                    })

            time.sleep(0.3)

        except Exception as e:
            print(f"RSS feed error ({url[:50]}): {e}")
            continue

    seen = set()
    unique = []
    for r in results:
        if r["link"] not in seen:
            seen.add(r["link"])
            unique.append(r)

    return unique


# ══════════════════════════════════════════════════════════════════════════════
# 3. DUCKDUCKGO HTML SCRAPE
# ══════════════════════════════════════════════════════════════════════════════

DDG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def _parse_ddg_html(html: str, source_label: str) -> list[dict]:
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
    r = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query, "b": "", "kl": "us-en"},
        headers=DDG_HEADERS,
        timeout=12,
    )
    r.raise_for_status()
    return r.text


def search_duckduckgo(query: str) -> list[dict]:
    try:
        return _parse_ddg_html(_ddg_post(query), "duckduckgo")
    except Exception as e:
        print(f"DuckDuckGo scrape error: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# 4. FACEBOOK GROUPS via DuckDuckGo  (free — no token needed)
#    Searches public Facebook group posts using targeted buyer-intent queries
# ══════════════════════════════════════════════════════════════════════════════

# These queries specifically target public Facebook group posts
# where real people are asking for help, recommendations, or showing buying intent
FB_GROUP_QUERIES = [
    # Reduced to 3 essential queries to avoid DDG rate limiting on Render
    'site:facebook.com/groups "{kw}" "looking for"',
    'site:facebook.com/groups "{kw}" "anyone recommend"',
    'site:facebook.com/groups "{kw}" "need help"',
]

def search_facebook_groups_ddg(keyword: str) -> list[dict]:
    """
    Search public Facebook group posts via DuckDuckGo site: operator.
    Kept to 3 queries max to avoid DDG rate limiting on Render.
    """
    results = []

    for template in FB_GROUP_QUERIES:
        query = template.replace("{kw}", keyword)
        try:
            html = _ddg_post(query)
            hits = _parse_ddg_html(html, "facebook_group")
            # Only keep results that actually link to facebook.com
            fb_hits = [h for h in hits if "facebook.com" in h.get("link", "")]
            results.extend(fb_hits)
            time.sleep(2.0)  # longer delay to stay under DDG rate limit
        except Exception as e:
            print(f"Facebook Groups DDG error ('{query[:50]}'): {e}")
            continue

    # Deduplicate
    seen = set()
    unique = []
    for r in results:
        if r["link"] not in seen:
            seen.add(r["link"])
            unique.append(r)

    print(f"[Search] Facebook Groups (DDG): {len(unique)} results")
    return unique


# Keep old function name as alias for backward compatibility
def search_facebook_ddg(keyword: str) -> list[dict]:
    return search_facebook_groups_ddg(keyword)


# ══════════════════════════════════════════════════════════════════════════════
# 5. SERPAPI FALLBACK
# ══════════════════════════════════════════════════════════════════════════════

MIN_FREE_RESULTS = 5

def search_serpapi(query: str, api_key: str, engine: str = "google") -> list[dict]:
    if not api_key:
        return []
    try:
        params = {"q": query, "api_key": api_key, "engine": engine, "num": 10}
        r = requests.get("https://serpapi.com/search", params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        if engine == "google":
            raw = data.get("organic_results", [])
            return [{
                "snippet":     item.get("snippet", ""),
                "title":       item.get("title", ""),
                "link":        item.get("link", ""),
                "source_name": "google/serpapi",
            } for item in raw]

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
    if not api_key:
        return []

    results = []
    # More targeted queries including groups
    fb_queries = [
        f'site:facebook.com/groups "looking for {keyword}"',
        f'site:facebook.com/groups "need {keyword}"',
        f'site:facebook.com/groups "recommend {keyword}"',
        f"looking for {keyword}",
        f"need {keyword}",
    ]
    for q in fb_queries[:3]:  # limit to 3 to save credits
        hits = search_serpapi(q, api_key, engine="google")
        fb_hits = [h for h in hits if "facebook.com" in h.get("link", "")]
        results.extend(fb_hits)

    seen = set()
    unique = []
    for r in results:
        if r["link"] not in seen:
            seen.add(r["link"])
            unique.append(r)

    return unique


# ══════════════════════════════════════════════════════════════════════════════
# 6. USA-FOCUSED PLATFORM SEARCH (all free via DuckDuckGo site: queries)
#    Targets platforms where US businesses and consumers actively seek services
# ══════════════════════════════════════════════════════════════════════════════

USA_PLATFORM_QUERIES = [
    # Quora — high-intent questions from US professionals (1 broad query)
    ('site:quora.com "{kw}"',                          "quora"),

    # Upwork — job posts = real buyers ready to spend money (best ROI)
    ('site:upwork.com/jobs "{kw}"',                    "upwork"),

    # IndieHackers — startup founders, US-heavy
    ('site:indiehackers.com "{kw}"',                   "indiehackers"),

    # LinkedIn public posts
    ('site:linkedin.com/posts "{kw}" "looking for"',   "linkedin"),

    # Craigslist — USA local service requests
    ('site:craigslist.org "{kw}"',                     "craigslist"),

    # Warrior Forum — US marketing/business community
    ('site:warriorforum.com "{kw}"',                   "warriorforum"),
]

def search_usa_platforms(keyword: str) -> list[dict]:
    """
    Search USA-focused platforms via DuckDuckGo site: queries.
    Kept to 6 queries max to avoid DDG rate limiting on Render.
    """
    results = []

    for template, source_name in USA_PLATFORM_QUERIES:
        query = template.replace("{kw}", keyword)
        try:
            html = _ddg_post(query)
            hits = _parse_ddg_html(html, source_name)
            results.extend(hits)
            time.sleep(2.0)  # longer delay to avoid DDG rate limiting
        except Exception as e:
            print(f"USA platform search error ({source_name}): {e}")
            continue

    # Deduplicate
    seen = set()
    unique = []
    for r in results:
        if r["link"] not in seen:
            seen.add(r["link"])
            unique.append(r)

    print(f"[Search] USA Platforms: {len(unique)} results")
    return unique


# ══════════════════════════════════════════════════════════════════════════════
# UNIFIED SEARCH
# ══════════════════════════════════════════════════════════════════════════════

def multi_search(keyword: str, serp_key: str = "") -> list[dict]:
    """
    Search all sources in priority order:
      1. Reddit API              (free)
      2. RSS feeds               (free)
      3. DuckDuckGo general      (free)
      4. Facebook Groups via DDG (free — no token needed, finds public group posts)
      5. USA Platforms via DDG   (free — Quora, IndieHackers, Upwork, Craigslist, LinkedIn, etc.)
      6. SerpAPI fallback        (paid — only if free sources find < MIN_FREE_RESULTS)
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

    # 4. Facebook Groups via DuckDuckGo (free — no token needed)
    fb_results = search_facebook_groups_ddg(keyword)
    add_results(fb_results)

    # 5. USA-focused platforms via DuckDuckGo (free)
    usa_results = search_usa_platforms(keyword)
    add_results(usa_results)

    # 6. SerpAPI fallbacks (paid) — only if free sources didn't find enough
    if len(all_results) < MIN_FREE_RESULTS and serp_key:
        print(f"[Search] Only {len(all_results)} free results — activating SerpAPI fallback")

        serp_queries = [
            f'site:reddit.com "looking for {keyword}"',
            f'site:reddit.com "need {keyword}"',
            f'site:quora.com "{keyword}"',
        ]
        for q in serp_queries:
            add_results(search_serpapi(q, serp_key, engine="google"))

        # SerpAPI Facebook groups
        add_results(search_facebook_serpapi(keyword, serp_key))

    elif not serp_key:
        print("[Search] No SerpAPI key — free sources only")
    else:
        print(f"[Search] Free sources sufficient ({len(all_results)} results) — SerpAPI skipped")

    print(f"[Search] Total unique results: {len(all_results)}")
    return all_results
