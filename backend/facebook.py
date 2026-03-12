"""
facebook.py — Facebook Group lead scanner via Graph API

Scans group posts AND their comments to find:
1. Post authors asking for help / showing buyer intent
2. Commenters expressing interest ("I'm interested", "how much?", "I need this too")
3. People frustrated with a problem related to your keyword

Each lead includes the person's name + direct Facebook profile URL
so you can visit their profile and message them manually.

HOW TO SET UP (one-time):
1. Go to https://developers.facebook.com → Create App → Business type
2. Add "Facebook Login" as a product
3. Go to https://developers.facebook.com/tools/explorer/
4. Select your app → Generate Access Token
5. Add permissions: groups_access_member_info
6. Copy token → paste in LeadRadar Settings → Facebook Token

Tokens expire ~60 days. To extend to ~90 days:
GET https://graph.facebook.com/oauth/access_token
  ?grant_type=fb_exchange_token
  &client_id=YOUR_APP_ID
  &client_secret=YOUR_APP_SECRET
  &fb_exchange_token=YOUR_SHORT_TOKEN
"""

import requests
from intent_ai import score_intent

GRAPH_API = "https://graph.facebook.com/v19.0"

# ── Phrases that signal a commenter is interested / a potential buyer ──────────
INTEREST_SIGNALS = [
    # Direct interest
    "i'm interested", "im interested", "i am interested", "interested",
    "count me in", "let's go", "lets go", "sign me up", "i want this",
    "i need this", "i need one", "i want one", "yes please", "me please",
    "where do i sign", "how do i get", "i'd like", "id like",
    # Price / buying intent questions
    "how much", "what's the price", "whats the price", "how much does it cost",
    "what's the cost", "do you deliver", "do you ship", "can you do",
    "are you available", "is this available", "still available",
    "how to order", "how can i order", "how do i buy", "where to buy",
    "can i get one", "can we get", "can you make", "do you make",
    "what's included", "whats included", "how long does it take",
    # Soft interest
    "following this", "following!", "follow this", "saving this",
    "bookmarking", "need this too", "same here", "same!", "this is what i need",
    "been looking for this", "been searching for", "looking for something like",
    "i've been looking", "ive been looking",
    # Frustration with current situation (problem-aware buyer)
    "my seo is terrible", "my website is slow", "i can't get traffic",
    "nobody finds my", "struggling with", "having trouble with",
    "not working for me", "tried everything", "nothing is working",
    "fed up with my", "tired of my", "my current agency",
    "my old agency", "previous agency failed", "wasted money on",
]


def extract_group_id(url_or_id: str) -> str:
    """Extract group ID from URL or return as-is if already an ID."""
    url_or_id = url_or_id.strip().rstrip("/")
    if "/groups/" in url_or_id:
        return url_or_id.split("/groups/")[-1].split("/")[0].split("?")[0]
    return url_or_id


def make_profile_url(user_id: str, username: str = "") -> str:
    """Build a direct Facebook profile URL from a user ID or username."""
    if user_id and user_id != "unknown":
        return f"https://www.facebook.com/profile.php?id={user_id}"
    return "https://www.facebook.com"


def get_group_info(group_id: str, token: str) -> dict:
    r = requests.get(
        f"{GRAPH_API}/{group_id}",
        params={"fields": "id,name,member_count", "access_token": token},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def get_group_posts(group_id: str, token: str, limit: int = 25) -> list[dict]:
    """Fetch recent posts from a group including author info."""
    r = requests.get(
        f"{GRAPH_API}/{group_id}/feed",
        params={
            "fields": "id,message,story,from,permalink_url,created_time,comments.limit(50){id,message,from,created_time}",
            "limit": limit,
            "access_token": token,
        },
        timeout=20,
    )
    if r.status_code == 403:
        raise PermissionError(
            "Access denied. Make sure your token has 'groups_access_member_info' "
            "permission and you are a member of this group."
        )
    r.raise_for_status()
    return r.json().get("data", [])


def commenter_is_interested(comment_text: str) -> bool:
    """
    Quick keyword check — is this comment from someone showing interest?
    This runs before the AI scorer to avoid scoring every single comment.
    """
    text_lower = comment_text.lower().strip()
    return any(signal in text_lower for signal in INTEREST_SIGNALS)


def scan_group(
    group_url: str,
    token: str,
    provider: str = "openai",
    provider_key: str = "",
    min_score: float = 7.0,
) -> dict:
    """
    Scan a Facebook group for:
    1. Post authors showing buyer intent or frustration
    2. Commenters expressing interest in a post

    Each lead contains:
    - name: person's full name
    - profile_url: direct link to their Facebook profile
    - post_text: the text that triggered the lead
    - post_url: link to the original post
    - intent_score: AI score 1-10
    - lead_type: "post_author" | "commenter"
    - context: for commenters, shows the original post title
    """
    group_id = extract_group_id(group_url)

    try:
        info = get_group_info(group_id, token)
    except requests.HTTPError as e:
        return {"group_id": group_id, "group_url": group_url,
                "error": f"Could not access group: {e}", "leads": []}
    except PermissionError as e:
        return {"group_id": group_id, "group_url": group_url,
                "error": str(e), "leads": []}

    group_name = info.get("name", group_id)

    try:
        posts = get_group_posts(group_id, token)
    except Exception as e:
        return {"group_id": group_id, "group_name": group_name, "group_url": group_url,
                "error": f"Could not fetch posts: {e}", "leads": []}

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
        author_name = post_author.get("name", "Unknown")
        author_profile = make_profile_url(author_id)

        # ── Score the POST AUTHOR ──────────────────────────────────────────
        try:
            post_score = score_intent(post_text, provider=provider, api_key_override=provider_key)
        except Exception as e:
            print(f"Scoring error (post): {e}")
            post_score = 0.0

        if post_score >= min_score:
            leads.append({
                "name":         author_name,
                "profile_url":  author_profile,
                "post_text":    post_text[:400],
                "post_url":     post_url,
                "intent_score": post_score,
                "lead_type":    "post_author",
                "context":      "",
                "source":       f"fb:{group_name}",
            })

        # ── Score COMMENTERS on this post ──────────────────────────────────
        comments_data = post.get("comments", {}).get("data", [])

        for comment in comments_data:
            comment_text = comment.get("message", "").strip()
            if not comment_text or len(comment_text) < 3:
                continue

            comments_scanned += 1
            commenter      = comment.get("from") or {}
            commenter_id   = commenter.get("id", "unknown")
            commenter_name = commenter.get("name", "Unknown")
            commenter_profile = make_profile_url(commenter_id)

            # First do a fast keyword check — only run AI on promising comments
            if not commenter_is_interested(comment_text):
                continue

            # Run AI score on the comment in context of the post
            combined_text = (
                f"Original post: {post_text[:200]}\n\n"
                f"Comment by {commenter_name}: {comment_text}"
            )

            try:
                comment_score = score_intent(
                    combined_text,
                    provider=provider,
                    api_key_override=provider_key,
                )
            except Exception as e:
                print(f"Scoring error (comment): {e}")
                comment_score = 0.0

            if comment_score >= min_score:
                # Truncate post text for context display
                post_preview = post_text[:80] + ("…" if len(post_text) > 80 else "")

                leads.append({
                    "name":         commenter_name,
                    "profile_url":  commenter_profile,
                    "post_text":    f'💬 "{comment_text}"',
                    "post_url":     post_url,
                    "intent_score": comment_score,
                    "lead_type":    "commenter",
                    "context":      f'On post: "{post_preview}"',
                    "source":       f"fb:{group_name}",
                })

    return {
        "group_id":        group_id,
        "group_name":      group_name,
        "group_url":       group_url,
        "posts_scanned":   posts_scanned,
        "comments_scanned": comments_scanned,
        "leads":           leads,
        "error":           None,
    }
