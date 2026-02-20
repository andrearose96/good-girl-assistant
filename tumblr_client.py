"""Fetch posts from Tumblr blog (OAuth 1.0a)."""
from datetime import datetime
from typing import Iterator
import re

from config import (
    TUMBLR_CONSUMER_KEY,
    TUMBLR_CONSUMER_SECRET,
    TUMBLR_OAUTH_TOKEN,
    TUMBLR_OAUTH_SECRET,
    TUMBLR_BLOG,
)


def _get_client():
    import pytumblr
    return pytumblr.TumblrRestClient(
        TUMBLR_CONSUMER_KEY,
        TUMBLR_CONSUMER_SECRET,
        TUMBLR_OAUTH_TOKEN,
        TUMBLR_OAUTH_SECRET,
    )


def _text_from_post(post: dict) -> str:
    """Extract plain text from a post (supports different post types)."""
    body = post.get("body") or post.get("caption") or ""
    if not body:
        return ""
    # Strip HTML tags roughly
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_posts(blog: str = None, limit_per_batch: int = 20, max_posts: int = 200) -> list[dict]:
    """Fetch posts from blog. Returns list of {id, blog_name, body_text, created_at}."""
    blog = (blog or TUMBLR_BLOG).strip()
    if not blog:
        return []
    if not TUMBLR_CONSUMER_KEY or not TUMBLR_CONSUMER_SECRET:
        return []
    # Allow blog.tumblr.com or just blog
    if ".tumblr.com" in blog:
        blog = blog.replace(".tumblr.com", "").strip()
    client = _get_client()
    out = []
    offset = 0
    while len(out) < max_posts:
        try:
            resp = client.posts(blog, limit=limit_per_batch, offset=offset)
        except Exception as e:
            return [{"error": str(e), "blog": blog}]
        if not resp or "posts" not in resp:
            break
        posts = resp["posts"]
        if not posts:
            break
        for p in posts:
            text = _text_from_post(p)
            out.append({
                "id": str(p.get("id", "")),
                "blog_name": blog,
                "body_text": text,
                "created_at": p.get("date"),
            })
        offset += len(posts)
        if len(posts) < limit_per_batch:
            break
    return out
