# ── Snippet-level signals that indicate promo/article content ──
PROMO_TEXT_SIGNALS = [
    "in this article", "in this post", "in this guide", "read more",
    "learn more", "click here", "our services", "we offer", "we provide",
    "contact us", "get a free quote", "schedule a consultation",
    "download our", "sign up", "subscribe", "our team of experts",
    "years of experience", "award-winning", "industry-leading",
    "as seen in", "trusted by", "our clients include",
]


def extract_leads(results: list[dict]) -> list[dict]:
    """
    Pass results through to AI scoring — only block obvious promo/ad content.
    The AI does the real filtering. Pre-filtering was too aggressive and
    was killing genuine buyer posts that didn't use exact keyword phrases.
    """
    leads = []

    for result in results:
        text  = result.get("snippet") or result.get("Text") or ""
        link  = result.get("link")    or result.get("FirstURL") or ""
        title = result.get("title")   or "Unknown"

        if not text or not link:
            continue

        text_lower = text.lower()

        # Only block content with 3+ clear promo signals — let the AI decide the rest
        promo_hits      = sum(1 for s in PROMO_TEXT_SIGNALS if s in text_lower)
        looks_like_promo = promo_hits >= 3

        if not looks_like_promo:
            leads.append({
                "name":        title,
                "profile_url": link,
                "post_text":   text,
                "post_url":    link,
            })
        else:
            print(f"  Filtered snippet ({promo_hits} promo signals): {text[:60]}")

    return leads
