# ── Snippet-level signals that indicate a real buyer post ──
BUYER_TEXT_SIGNALS = [
    # Active search / hiring intent
    "looking for", "need a", "need help", "anyone recommend",
    "can anyone", "recommend a", "searching for", "how do i find",
    "where can i find", "hiring a", "looking to hire", "budget",
    "how much does", "affordable", "for my business", "for my website",
    "for my small business", "who should i", "which agency",
    "any suggestions", "any recommendations", "please help",
    "struggling with", "can't find", "cannot find",
    # Problem / frustration signals (also high intent — they need a solution)
    "my seo is terrible", "nothing is working", "fed up with",
    "tired of my", "i tried everything", "no results",
    "wasted money", "my agency failed", "fired my agency",
    "doing it myself but", "can't get traffic", "nobody finds my",
    "my website doesn't", "my rankings dropped", "lost all my traffic",
    "i'm struggling", "im struggling", "really frustrated",
    "having a hard time", "can't figure out", "need to fix",
    # Commenter interest signals
    "i'm interested", "im interested", "how much", "count me in",
    "i need this", "following this", "same here", "i want this",
]

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
    Extract leads from SerpAPI organic_results.
    Applies a second layer of text filtering on the snippet itself
    to catch promo content that slipped past the domain filter.
    """
    leads = []

    for result in results:
        text  = result.get("snippet") or result.get("Text") or ""
        link  = result.get("link")    or result.get("FirstURL") or ""
        title = result.get("title")   or "Unknown"

        if not text or not link:
            continue

        text_lower = text.lower()

        # Must contain at least one buyer signal in the snippet
        has_buyer_signal = any(signal in text_lower for signal in BUYER_TEXT_SIGNALS)

        # Must NOT be dominated by promo language
        promo_hits = sum(1 for signal in PROMO_TEXT_SIGNALS if signal in text_lower)
        looks_like_promo = promo_hits >= 2  # 2+ promo phrases = almost certainly an ad/article

        if has_buyer_signal and not looks_like_promo:
            leads.append({
                "name":        title,
                "profile_url": link,
                "post_text":   text,
                "post_url":    link,
            })
        else:
            reason = "no buyer signal" if not has_buyer_signal else f"{promo_hits} promo signals"
            print(f"  Filtered snippet ({reason}): {text[:60]}")

    return leads
