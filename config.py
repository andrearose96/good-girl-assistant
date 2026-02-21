"""App config from env and stored settings."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# Load .env from project root (next to config.py) so keys are found regardless of cwd
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "commitments.db"


def _env(key: str, default: str = "") -> str:
    """Get env var, stripped of whitespace and optional quotes."""
    v = os.getenv(key, default) or ""
    if isinstance(v, str):
        v = v.strip().strip('"').strip("'")
    return v


# Tumblr (optional; app works with manual import too)
# Consumer key/secret from env; token/secret from env or from DB after "Connect Tumblr"
TUMBLR_CONSUMER_KEY = _env("TUMBLR_CONSUMER_KEY")
TUMBLR_CONSUMER_SECRET = _env("TUMBLR_CONSUMER_SECRET")
TUMBLR_OAUTH_TOKEN = _env("TUMBLR_OAUTH_TOKEN")
TUMBLR_OAUTH_SECRET = _env("TUMBLR_OAUTH_SECRET")
TUMBLR_BLOG = _env("TUMBLR_BLOG")


def _tumblr_token_from_db():
    """Load token/secret from DB if not in env (set by in-app Connect Tumblr flow)."""
    if TUMBLR_OAUTH_TOKEN and TUMBLR_OAUTH_SECRET:
        return TUMBLR_OAUTH_TOKEN, TUMBLR_OAUTH_SECRET
    try:
        from db import get_setting
        token = get_setting("tumblr_oauth_token")
        secret = get_setting("tumblr_oauth_secret")
        if token and secret:
            return token, secret
    except Exception:
        pass
    return "", ""


def get_tumblr_oauth_token_secret():
    """Return (oauth_token, oauth_secret) from env or DB."""
    return _tumblr_token_from_db()


def tumblr_consumer_configured():
    """True when app key and secret are set (required to start Connect flow)."""
    return bool(TUMBLR_CONSUMER_KEY and TUMBLR_CONSUMER_SECRET)


def tumblr_configured():
    """True only when all four Tumblr keys are set (env or DB) for API calls."""
    token, secret = get_tumblr_oauth_token_secret()
    return bool(
        TUMBLR_CONSUMER_KEY
        and TUMBLR_CONSUMER_SECRET
        and token
        and secret
    )
