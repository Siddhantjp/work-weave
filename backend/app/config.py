"""Settings, read once from the environment (.env at the project root)."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


DB_PATH = _path(os.getenv("DB_PATH", "data/listings.db"))
CHROMA_DIR = _path(os.getenv("CHROMA_DIR", "data/chroma"))
FRONTEND_DIR = ROOT / "frontend" / "dist"

# Listing source (apna.co)
SCRAPER_MIN_INTERVAL_S = float(os.getenv("SCRAPER_MIN_INTERVAL_S", "2.5"))   # politeness delay between requests
REFRESH_TTL_HOURS = float(os.getenv("REFRESH_TTL_HOURS", "0.25"))            # re-check apna.co when a trade is older than this
AUTO_REFRESH_MINUTES = float(os.getenv("AUTO_REFRESH_MINUTES", "0"))         # 0 = no background scraping

# LLM (Groq)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# Accounts: a separate database from the listings. Postgres in production (DATABASE_URL), a local SQLite file otherwise.
USER_DATABASE_URL = os.getenv("USER_DATABASE_URL") or os.getenv("DATABASE_URL") or f"sqlite:///{_path('data/users.db').as_posix()}"
CACHE_DB_PATH = _path(os.getenv("CACHE_DB_PATH", "data/llm_cache.db"))       # LLM answers cache (contains prompts, so also kept apart)

# Sign-in (Google OAuth / OpenID Connect)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")         # the public address of this app
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)             # signs the short OAuth handshake cookie
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
COOKIE_SECURE = BASE_URL.startswith("https://")
SESSION_DAYS = 7
