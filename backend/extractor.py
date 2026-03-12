def extract_leads(results: list[dict]) -> list[dict]:
    """
    ✅ FIX: Original extractor expected DuckDuckGo's 'Text'/'FirstURL' fields.
    Updated to work with SerpAPI's organic_results format: 'snippet'/'link'.
    """
    leads = []

    for result in results:
        # SerpAPI returns 'snippet' and 'link'
        text = result.get("snippet") or result.get("Text") or ""
        link = result.get("link") or result.get("FirstURL") or ""
        title = result.get("title") or "Unknown"

        if text and link:
            leads.append({
                "name": title,
                "profile_url": link,
                "post_text": text,
                "post_url": link,
            })

    return leads
