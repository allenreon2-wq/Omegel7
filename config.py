# ============================================================
#   Anonymous Chat Bot — config.py
#   All values are loaded from .env — never hardcode secrets!
# ============================================================

import os
import sys
from dotenv import load_dotenv

# Load .env file FIRST before reading any env variable
load_dotenv()

# ── Telegram credentials ────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID    = os.getenv("API_ID")
API_HASH  = os.getenv("API_HASH")

# ── Validate required values at startup ─────────────────────
_missing = [k for k, v in {"BOT_TOKEN": BOT_TOKEN, "API_ID": API_ID, "API_HASH": API_HASH}.items() if not v]
if _missing:
    sys.exit(f"❌  Missing required environment variables: {', '.join(_missing)}\n"
             f"    Copy .env.example → .env and fill in the values.")

API_ID = int(API_ID)   # must be int for Pyrogram

# ── Admin IDs (comma-separated, e.g. "111,222,333") ─────────
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
if not ADMIN_IDS:
    sys.exit("❌  ADMIN_IDS is not set in .env. Add at least one admin Telegram user ID.")


# ── Database ────────────────────────────────────────────────
DB_PATH     = os.getenv("DB_PATH", "data/chatbot.db")

# ── Anti-spam / flood control ───────────────────────────────
FLOOD_LIMIT          = 10       # max messages per window
FLOOD_WINDOW         = 10       # seconds
REPORT_BAN_THRESHOLD = 5        # auto-ban after N reports
KARMA_REPORT_PENALTY = -10
KARMA_CHAT_REWARD    = 2        # awarded per completed session
MIN_KARMA_TO_CHAT    = -50      # below this → soft-ban

# ── AI moderation (simple bad-word list path) ────────────────
BADWORDS_FILE = "badwords.txt"

# ── Matching ────────────────────────────────────────────────
QUEUE_TIMEOUT = 120   # seconds before auto-leaving queue
SEARCH_MSG_INTERVAL = 5  # seconds between "still searching…" dots

# ── Misc ────────────────────────────────────────────────────
BOT_USERNAME = "YourBotUsername"
SUPPORT_USERNAME = "YourSupportUsername"
