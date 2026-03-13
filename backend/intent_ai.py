import os


# ── Fix 3: Rewritten prompt that explicitly rejects ads and promo content ──
PROMPT_TEMPLATE = """You are screening social media posts and forum comments to find REAL PEOPLE who are actively looking to hire a service RIGHT NOW.

You must be very strict. Score this text from 1 to 10 using these rules:

SCORE 8-10 (real buyer) — Score HIGH for ANY of these:
- A real person asking for recommendations or quotes: "Anyone recommend a good SEO agency?"
- Someone actively looking to hire: "Looking for a roofer in Austin, budget $5k"
- Someone expressing frustration with a problem you could solve: "My SEO is terrible, nothing is working", "Fed up with my current agency", "Tried everything but can't get traffic"
- Someone struggling and looking for help: "I've been doing it myself but failing", "I can't get my website to rank"
- A commenter saying they're interested: "I'm interested", "How much?", "Count me in", "I need this too"

SCORE 4-7 (possible buyer) — Someone researching, comparing options, or venting without actively asking for help yet.

SCORE 1-3 (not a buyer) — ANY of the following, score LOW:
- Articles, blog posts, or guides (e.g. "10 Benefits of Hiring an SEO Agency")
- An agency or business promoting their own services
- News articles or opinion pieces
- Someone answering a question, not asking one
- Generic advice or tips content
- Anything written BY a service provider TO attract clients

The key test: Is this written BY a potential customer SEEKING help?
Or is it written BY a business or writer trying to attract customers?
If the latter, score it 1-2 no matter how relevant it seems.

Text to score:
{post}

Return ONLY a single number 1-10. Nothing else."""


def score_intent(post: str, provider: str = "openai", api_key_override: str = "") -> float:
    """
    Score buyer intent using the specified AI provider.
    Key priority: per-request override → environment variable.
    Supports: openai, gemini, claude
    """
    if not post or not post.strip():
        return 0.0

    # Strip non-ASCII characters (emojis, unicode) that crash some API clients
    clean_post = post[:1500].encode('ascii', errors='ignore').decode('ascii').strip()
    if not clean_post:
        return 0.0
    prompt = PROMPT_TEMPLATE.format(post=clean_post)

    try:
        if provider == "openai":
            return _score_openai(prompt, api_key_override)
        elif provider == "gemini":
            return _score_gemini(prompt, api_key_override)
        elif provider == "claude":
            return _score_claude(prompt, api_key_override)
        else:
            print(f"Unknown provider: {provider}, falling back to openai")
            return _score_openai(prompt, api_key_override)
    except Exception as e:
        print(f"Intent scoring error ({provider}): {e}")
        return 0.0


def _parse_score(raw: str) -> float:
    try:
        score = float(raw.strip().split()[0])
        return max(1.0, min(10.0, score))
    except (ValueError, IndexError):
        return 0.0


def _score_openai(prompt: str, key_override: str) -> float:
    import requests as req
    key = key_override.strip() or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("No OpenAI API key available")

    # Use requests directly to avoid OpenAI SDK encoding issues
    import json as _json
    body = _json.dumps({
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 5,
        "temperature": 0,
    }, ensure_ascii=True).encode("utf-8")

    r = req.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        data=body,
        timeout=15,
    )
    r.raise_for_status()
    return _parse_score(r.json()["choices"][0]["message"]["content"])


def _score_gemini(prompt: str, key_override: str) -> float:
    import requests
    key = key_override.strip() or os.getenv("GEMINI_API_KEY", "")
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
    key = key_override.strip() or os.getenv("CLAUDE_API_KEY", "")
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
