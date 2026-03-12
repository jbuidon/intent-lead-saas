import os


PROMPT_TEMPLATE = """Does this post indicate the person wants to hire or buy a service?

Score from 1 to 10 where:
- 1-3 = No intent (browsing, discussing, or complaining)
- 4-6 = Mild interest (researching or comparing)
- 7-10 = Strong buyer intent (actively looking to hire or buy)

Post:
{post}

Return ONLY a single number between 1 and 10. No explanation."""


def score_intent(post: str, provider: str = "openai", api_key_override: str = "") -> float:
    """
    Score buyer intent using the specified AI provider.
    Key priority: per-request override → environment variable.
    Supports: openai, gemini, claude
    """
    if not post or not post.strip():
        return 0.0

    prompt = PROMPT_TEMPLATE.format(post=post[:1500])  # Truncate to save tokens

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
    from openai import OpenAI
    key = key_override.strip() or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("No OpenAI API key available")

    client = OpenAI(api_key=key)
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=5,
        temperature=0,
    )
    return _parse_score(r.choices[0].message.content)


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
