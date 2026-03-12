import os
import requests


def build_queries(keyword: str) -> list[str]:
    phrases = [
        f"looking for {keyword}",
        f"need {keyword}",
        f"recommend {keyword}",
        f"hire {keyword}",
        f"best {keyword} service",
    ]
    platforms = [
        "site:reddit.com",
        "site:linkedin.com",
        "site:twitter.com",
        "site:quora.com",
        "site:facebook.com",
    ]
    return [f'{p} "{phrase}"' for p in platforms for phrase in phrases]


def search_web(query: str, serp_key_override: str = "") -> list[dict]:
    """
    Uses SerpAPI (Google backend) which properly supports site: operators.
    Key priority: per-request override → environment variable.
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
        return response.json().get("organic_results", [])
    except requests.RequestException as e:
        print(f"Search error for '{query}': {e}")
        return []
