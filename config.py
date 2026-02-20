"""App config from env."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "commitments.db"

# Tumblr (optional; app works with manual import too)
TUMBLR_CONSUMER_KEY = os.getenv("TUMBLR_CONSUMER_KEY", "")
TUMBLR_CONSUMER_SECRET = os.getenv("TUMBLR_CONSUMER_SECRET", "")
TUMBLR_OAUTH_TOKEN = os.getenv("TUMBLR_OAUTH_TOKEN", "")
TUMBLR_OAUTH_SECRET = os.getenv("TUMBLR_OAUTH_SECRET", "")
TUMBLR_BLOG = os.getenv("TUMBLR_BLOG", "").strip()

def tumblr_configured():
    return bool(TUMBLR_CONSUMER_KEY and TUMBLR_CONSUMER_SECRET)
