"""
platforms.py — Multi-platform lead scanner

Covers:
  1. Facebook Pages  — posts + comments via Graph API
  2. Instagram       — comments on your own posts/pages via Graph API
  3. LinkedIn        — paste-and-score (no API, you paste the text manually)

Same Graph API token works for both Facebook and Instagram
(Instagram is owned by Facebook — same developer platform).
"""

import requests
from intent_ai import score_intent
from facebook import commenter_is_interested, make_profile_url, INTEREST_SIGNALS

GRAPH_API = "https://graph.facebook.com/v19.0"


# ══════════════════════════════════════════════════════════════════════════════
# FACEBOOK PAGES
# ══════════════════════════════════════════════════════════════════════════════

def extract_page_id(url_or_id: str) -> str:
    """
    Extract page ID or username from a Facebook page URL.
    Handles:
      https://www.facebook.com/YourPageName
      https://www.facebook.com/pages/Name/123456
      YourPageName
      123456
    """
    s = url_or_id.strip().rstrip("/")
    if "facebook.com" in s:
        # Remove query params
        s = s.split("?")[0]
        parts = [p for p in s.split("/") if p and p != "www.facebook.com"
                 and "facebook.com" not in p]
        # Skip "pages" keyword
        parts = [p for p in parts if p.lower() not in ("pages", "pg", "profile.php")]
        if parts:
            return parts[-1]
    return s


def get_page_posts(page_id: str, token: str, limit: int = 25) -> list[dict]:
    """Fetch recent posts from a Facebook Page including comments."""
    r = requests.get(
        f"{GRAPH_API}/{page_id}/posts",
        params={
            "fields": "id,message,story,from,permalink_url,created_time,"
                      "comments.limit(50){id,message,from,created_time}",
            "limit": limit,
            "access_token": token,
        },
        timeout=20,
    )
    if r.status_code == 403:
        raise PermissionError(
            "Access denied to this page. Make sure your token has page access "
            "or the page is public."
        )
    r.raise_for_status()
    return r.json().get("data", [])


def get_page_info(page_id: str, token: str) -> dict:
    r = requests.get(
        f"{GRAPH_API}/{page_id}",
        params={"fields": "id,name,fan_count,link", "access_token": token},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def scan_facebook_page(
    page_url: str,
    token: str,
    provider: str = "openai",
    provider_key: str = "",
    min_score: float = 7.0,
) -> dict:
    """
    Scan a Facebook Page for buyer-intent posts and interested commenters.
    Works on public pages — no need to be a member/follower.
    """
    page_id = extract_page_id(page_url)

    try:
        info = get_page_info(page_id, token)
    except requests.HTTPError as e:
        return {
            "platform": "facebook_page",
            "page_id": page_id,
            "page_url": page_url,
            "error": f"Could not access page: {e}",
            "leads": [],
        }

    page_name = info.get("name", page_id)

    try:
        posts = get_page_posts(page_id, token)
    except Exception as e:
        return {
            "platform": "facebook_page",
            "page_id": page_id,
            "page_name": page_name,
            "page_url": page_url,
            "error": f"Could not fetch posts: {e}",
            "leads": [],
        }

    leads = []
    posts_scanned = 0
    comments_scanned = 0

    for post in posts:
        post_text = post.get("message") or post.get("story") or ""
        if not post_text or len(post_text.strip()) < 15:
            continue

        posts_scanned += 1
        post_url    = post.get("permalink_url") or f"https://facebook.com/{post.get('id','')}"
        post_author = post.get("from") or {}
        author_id   = post_author.get("id", "unknown")
        author_name = post_author.get("name", page_name)  # page name if no individual author

        # Score the post itself
        try:
            post_score = score_intent(post_text, provider=provider, api_key_override=provider_key)
        except Exception as e:
            print(f"Page post scoring error: {e}")
            post_score = 0.0

        if post_score >= min_score:
            leads.append({
                "name":         author_name,
                "profile_url":  make_profile_url(author_id),
                "post_text":    post_text[:400],
                "post_url":     post_url,
                "intent_score": post_score,
                "lead_type":    "post_author",
                "context":      "",
                "source":       f"fb_page:{page_name}",
                "platform":     "Facebook Page",
            })

        # Score interested commenters
        for comment in post.get("comments", {}).get("data", []):
            comment_text = comment.get("message", "").strip()
            if not comment_text or len(comment_text) < 3:
                continue

            comments_scanned += 1
            if not commenter_is_interested(comment_text):
                continue

            commenter      = comment.get("from") or {}
            commenter_id   = commenter.get("id", "unknown")
            commenter_name = commenter.get("name", "Unknown")

            combined = f"Post: {post_text[:200]}\n\nComment: {comment_text}"
            try:
                score = score_intent(combined, provider=provider, api_key_override=provider_key)
            except Exception as e:
                print(f"Page comment scoring error: {e}")
                score = 0.0

            if score >= min_score:
                leads.append({
                    "name":         commenter_name,
                    "profile_url":  make_profile_url(commenter_id),
                    "post_text":    f'💬 "{comment_text}"',
                    "post_url":     post_url,
                    "intent_score": score,
                    "lead_type":    "commenter",
                    "context":      f'On post: "{post_text[:80]}…"',
                    "source":       f"fb_page:{page_name}",
                    "platform":     "Facebook Page",
                })

    return {
        "platform":        "facebook_page",
        "page_id":         page_id,
        "page_name":       page_name,
        "page_url":        page_url,
        "posts_scanned":   posts_scanned,
        "comments_scanned": comments_scanned,
        "leads":           leads,
        "error":           None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# INSTAGRAM (via Facebook Graph API)
# ══════════════════════════════════════════════════════════════════════════════

def get_instagram_accounts(token: str) -> list[dict]:
    """
    Get Instagram Business/Creator accounts linked to this Facebook token.
    These are the accounts you OWN or MANAGE — not other people's accounts.
    """
    r = requests.get(
        f"{GRAPH_API}/me/accounts",
        params={
            "fields": "id,name,instagram_business_account{id,name,username}",
            "access_token": token,
        },
        timeout=10,
    )
    r.raise_for_status()
    pages = r.json().get("data", [])

    ig_accounts = []
    for page in pages:
        ig = page.get("instagram_business_account")
        if ig:
            ig_accounts.append({
                "ig_id":    ig.get("id"),
                "name":     ig.get("name") or ig.get("username", ""),
                "username": ig.get("username", ""),
                "fb_page":  page.get("name", ""),
            })

    return ig_accounts


def get_instagram_posts(ig_user_id: str, token: str, limit: int = 20) -> list[dict]:
    """Fetch recent media posts from your Instagram Business/Creator account."""
    r = requests.get(
        f"{GRAPH_API}/{ig_user_id}/media",
        params={
            "fields": "id,caption,permalink,timestamp,"
                      "comments.limit(50){id,text,username,timestamp}",
            "limit": limit,
            "access_token": token,
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("data", [])


def scan_instagram(
    token: str,
    provider: str = "openai",
    provider_key: str = "",
    min_score: float = 7.0,
) -> list[dict]:
    """
    Scan all Instagram accounts linked to this token for interested commenters.
    Returns a list of result dicts, one per Instagram account found.
    """
    try:
        accounts = get_instagram_accounts(token)
    except Exception as e:
        return [{
            "platform": "instagram",
            "error": f"Could not fetch Instagram accounts: {e}. "
                     "Make sure your Facebook page has a linked Instagram Business account.",
            "leads": [],
        }]

    if not accounts:
        return [{
            "platform": "instagram",
            "error": "No Instagram Business or Creator accounts found linked to this token. "
                     "You need to link your Instagram account to a Facebook Page first "
                     "(Facebook Page Settings → Instagram).",
            "leads": [],
        }]

    results = []

    for account in accounts:
        ig_id    = account["ig_id"]
        ig_name  = account["username"] or account["name"]

        try:
            posts = get_instagram_posts(ig_id, token)
        except Exception as e:
            results.append({
                "platform":  "instagram",
                "ig_name":   ig_name,
                "error":     f"Could not fetch posts: {e}",
                "leads":     [],
            })
            continue

        leads = []
        posts_scanned    = 0
        comments_scanned = 0

        for post in posts:
            caption  = post.get("caption", "") or ""
            post_url = post.get("permalink", f"https://instagram.com/p/{post.get('id','')}")
            posts_scanned += 1

            for comment in post.get("comments", {}).get("data", []):
                comment_text = comment.get("text", "").strip()
                username     = comment.get("username", "Unknown")
                if not comment_text:
                    continue

                comments_scanned += 1

                # Fast keyword check first
                if not commenter_is_interested(comment_text):
                    continue

                # Build Instagram profile URL from username
                ig_profile = f"https://instagram.com/{username}" if username != "Unknown" else "#"

                combined = f"Post caption: {caption[:200]}\n\nComment by @{username}: {comment_text}"
                try:
                    score = score_intent(combined, provider=provider, api_key_override=provider_key)
                except Exception as e:
                    print(f"Instagram comment scoring error: {e}")
                    score = 0.0

                if score >= min_score:
                    caption_preview = caption[:80] + ("…" if len(caption) > 80 else "")
                    leads.append({
                        "name":         f"@{username}",
                        "profile_url":  ig_profile,
                        "post_text":    f'💬 "{comment_text}"',
                        "post_url":     post_url,
                        "intent_score": score,
                        "lead_type":    "commenter",
                        "context":      f'On your post: "{caption_preview}"',
                        "source":       f"ig:{ig_name}",
                        "platform":     "Instagram",
                    })

        results.append({
            "platform":         "instagram",
            "ig_id":            ig_id,
            "ig_name":          ig_name,
            "posts_scanned":    posts_scanned,
            "comments_scanned": comments_scanned,
            "leads":            leads,
            "error":            None,
        })

    return results


# ══════════════════════════════════════════════════════════════════════════════
# LINKEDIN — PASTE & SCORE
# ══════════════════════════════════════════════════════════════════════════════

def score_linkedin_paste(
    items: list[dict],
    provider: str = "openai",
    provider_key: str = "",
    min_score: float = 6.0,  # Lower threshold — LinkedIn is higher quality traffic
) -> list[dict]:
    """
    Score manually pasted LinkedIn content.

    Each item in `items` should be:
    {
        "text":        "the post or comment text you copied",
        "url":         "the LinkedIn profile or post URL",
        "person_name": "name you saw (optional)",
        "content_type": "post" | "comment" | "profile_bio" | "profile_about"
    }

    Returns the same items with intent_score added, filtered to min_score+.
    """
    leads = []

    for item in items:
        text         = (item.get("text") or "").strip()
        url          = (item.get("url") or "").strip()
        person_name  = (item.get("person_name") or "LinkedIn User").strip()
        content_type = item.get("content_type", "post")

        if not text:
            continue

        # Add context to the prompt based on content type
        if content_type == "profile_bio":
            context_hint = "This is a LinkedIn profile bio/headline."
        elif content_type == "profile_about":
            context_hint = "This is the About section from a LinkedIn profile."
        elif content_type == "comment":
            context_hint = "This is a comment someone left on a LinkedIn post."
        else:
            context_hint = "This is a LinkedIn post."

        scored_text = f"{context_hint}\n\n{text}"

        try:
            score = score_intent(scored_text, provider=provider, api_key_override=provider_key)
        except Exception as e:
            print(f"LinkedIn scoring error: {e}")
            score = 0.0

        if score >= min_score:
            leads.append({
                "name":         person_name,
                "profile_url":  url or "#",
                "post_text":    text[:400],
                "post_url":     url or "#",
                "intent_score": score,
                "lead_type":    content_type,
                "context":      f"Pasted {content_type}",
                "source":       "linkedin",
                "platform":     "LinkedIn",
            })

    return leads
