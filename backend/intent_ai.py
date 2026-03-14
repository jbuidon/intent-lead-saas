import os
import re

PROMPT_TEMPLATE = """You are screening social media posts and forum comments to find REAL PEOPLE who are actively looking to hire a service RIGHT NOW.

You must be very strict. Score this text from 1 to 10 using these rules:

SCORE 8-10 (real buyer) — Score HIGH for ANY of these:
- A real person asking for recommendations or quotes: "Anyone recommend a good SEO agency?"
- Someone actively looking to hire: "Looking for a roofer in Austin, budget $5k"
- Someone expressing frustration with a problem you could solve: "My SEO is terrible, nothing is working"
- Someone struggling and looking for help: "I've been doing it myself but failing"
- A commenter saying they're interested: "I'm interested", "How much?", "Count me in"

SCORE 4-7 (possible buyer) — Someone researching, comparing options, or venting without actively asking for help yet.

SCORE 1-3 (not a buyer) — ANY of the following, score LOW:
- Articles, blog posts, or guides
- An agency or business promoting their own services
- News articles or opinion pieces
- Someone answering a question, not asking one
- Generic advice or tips content

The key test: Is this written BY a potential customer SEEKING help?
Or is it written BY a business or writer trying to attract customers?
If the latter, score it 1-2 no matter how relevant it seems.

Text to score:
{post}

Return ONLY a single number 1-10. Nothing else."""


def _clean(text: str) -> str:
    """Remove ALL non-ASCII characters to prevent any encoding issues."""
    text = text.replace('\u2013', '-').replace('\u2014', '-')
    text = text.replace('\u2018', "'").replace('\u2019', "'")
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2026', '...')
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:1500]


def _clean_key(key: str) -> str:
    """Strip any invisible or non-ASCII characters from API keys."""
    return key.encode('ascii', errors='ignore').decode('ascii').strip()


def _get_fallback_order(preferred: str) -> list[tuple[str, str]]:
    """
    Build a list of (provider, key) pairs to try in order.
    Starts with the preferred provider, then falls back to others
    that have keys available — either passed in or from environment.
    """
    env_keys = {
        "openai": _clean_key(os.getenv("OPENAI_API_KEY", "")),
        "gemini": _clean_key(os.getenv("GEMINI_API_KEY", "")),
        "claude": _clean_key(os.getenv("CLAUDE_API_KEY", "")),
    }

    # All three providers in preferred-first order
    order = [preferred] + [p for p in ["openai", "gemini", "claude"] if p != preferred]

    # Only include providers that actually have a key
    return [(p, env_keys[p]) for p in order if env_keys[p]]


def score_intent(post: str, provider: str = "openai", api_key_override: str = "") -> float:
    if not post or not post.strip():
        return 0.0

    clean_post = _clean(post)
    if not clean_post:
        return 0.0

    prompt = PROMPT_TEMPLATE.format(post=clean_post)

    # If a specific key is passed (from frontend UI), use it directly for that provider
    if api_key_override and _clean_key(api_key_override):
        try:
            return _call_provider(provider, prompt, api_key_override)
        except Exception as e:
            print(f"Intent scoring error ({provider}): {e}")
            # Even with override, fall through to env-key fallback below

    # Auto-fallback using environment keys: try preferred first, then others
    fallback_chain = _get_fallback_order(provider)

    if not fallback_chain:
        print("Intent scoring: no API keys available in environment (OPENAI_API_KEY / GEMINI_API_KEY / CLAUDE_API_KEY)")
        return 0.0

    last_error = None
    for p, key in fallback_chain:
        try:
            score = _call_provider(p, prompt, key)
            if p != provider:
                print(f"Intent scoring: fell back to {p} (preferred {provider} unavailable)")
            return score
        except Exception as e:
            print(f"Intent scoring error ({p}): {e}")
            last_error = e
            continue

    print(f"Intent scoring: all providers failed. Last error: {last_error}")
    return 0.0


def _call_provider(provider: str, prompt: str, key: str) -> float:
    """Call a specific provider with a specific key."""
    if provider == "openai":
        return _score_openai(prompt, key)
    elif provider == "gemini":
        return _score_gemini(prompt, key)
    elif provider == "claude":
        return _score_claude(prompt, key)
    else:
        return _score_openai(prompt, key)


def _parse_score(raw: str) -> float:
    try:
        score = float(raw.strip().split()[0])
        return max(1.0, min(10.0, score))
    except (ValueError, IndexError):
        return 0.0


def _score_openai(prompt: str, key_override: str) -> float:
    import urllib.request
    import json
    key = _clean_key(key_override) or _clean_key(os.getenv("OPENAI_API_KEY", ""))
    if not key:
        raise ValueError("No OpenAI API key available")

    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 5,
        "temperature": 0,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return _parse_score(result["choices"][0]["message"]["content"])


def _score_gemini(prompt: str, key_override: str) -> float:
    import requests
    key = _clean_key(key_override) or _clean_key(os.getenv("GEMINI_API_KEY", ""))
    if not key:
        raise ValueError("No Gemini API key available")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 5, "temperature": 0},
    }
    r = requests.post(url, json=body, timeout=15)
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_score(text)


def _score_claude(prompt: str, key_override: str) -> float:
    import requests
    key = _clean_key(key_override) or _clean_key(os.getenv("CLAUDE_API_KEY", ""))
    if not key:
        raise ValueError("No Claude API key available")
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 5,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=15,
    )
    r.raise_for_status()
    text = r.json()["content"][0]["text"]
    return _parse_score(text)
