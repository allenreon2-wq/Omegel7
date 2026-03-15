# ============================================================
#   Anonymous Chat Bot — handlers/matching.py
#   Smart async matching engine with gender / interest / country
# ============================================================

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from config import QUEUE_TIMEOUT, SEARCH_MSG_INTERVAL

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
#  Data structures
# ════════════════════════════════════════════════════════════
@dataclass
class QueueEntry:
    user_id:       int
    joined_at:     float = field(default_factory=time.monotonic)
    gender:        str   = "random"
    interests:     Set[str] = field(default_factory=set)
    country:       str   = ""
    gender_filter: str   = "random"   # what they want to see
    past_partners: Set[int] = field(default_factory=set)


# ════════════════════════════════════════════════════════════
#  MatchMaker
# ════════════════════════════════════════════════════════════
class MatchMaker:
    """
    Thread-safe in-memory queue.
    Priority:
      1.  Same interests  + gender filter  + country
      2.  Same interests  + gender filter
      3.  Gender filter   + country
      4.  Gender filter
      5.  Any available user (fallback)
    Users who were recently matched together are skipped for
    RECENT_SKIP_COUNT matches.
    """

    RECENT_SKIP_COUNT = 5  # avoid re-match in last N partners

    def __init__(self):
        self._queue:   Dict[int, QueueEntry]  = {}
        self._lock:    asyncio.Lock           = asyncio.Lock()
        self._matched: Dict[int, int]         = {}   # user_id -> partner_id

    # ── Public API ──────────────────────────────────────────
    async def enqueue(self, entry: QueueEntry) -> Optional[int]:
        """
        Add user to queue and immediately try to match.
        Returns partner_id if match found, else None (stays in queue).
        """
        async with self._lock:
            if entry.user_id in self._queue:
                return None          # already queued
            if entry.user_id in self._matched:
                return None          # already in chat

            match = self._find_match(entry)
            if match:
                partner = self._queue.pop(match)
                self._matched[entry.user_id]    = match
                self._matched[match]            = entry.user_id
                log.debug("✅ Matched %s <-> %s", entry.user_id, match)
                return match

            self._queue[entry.user_id] = entry
            return None

    async def dequeue(self, user_id: int) -> bool:
        """Remove user from queue. Returns True if was queued."""
        async with self._lock:
            return self._queue.pop(user_id, None) is not None

    async def remove_matched(self, user_id: int):
        """Remove from matched dict when chat ends."""
        async with self._lock:
            partner = self._matched.pop(user_id, None)
            if partner:
                self._matched.pop(partner, None)

    async def is_queued(self, user_id: int) -> bool:
        async with self._lock:
            return user_id in self._queue

    async def queue_size(self) -> int:
        async with self._lock:
            return len(self._queue)

    async def expire_old_entries(self) -> List[int]:
        """Remove queue entries older than QUEUE_TIMEOUT. Returns expired IDs."""
        now     = time.monotonic()
        expired = []
        async with self._lock:
            for uid, entry in list(self._queue.items()):
                if now - entry.joined_at > QUEUE_TIMEOUT:
                    self._queue.pop(uid)
                    expired.append(uid)
        return expired

    # ── Private matching logic ───────────────────────────────
    def _find_match(self, seeker: QueueEntry) -> Optional[int]:
        candidates = [
            e for uid, e in self._queue.items()
            if self._compatible(seeker, e)
        ]
        if not candidates:
            return None

        def score(e: QueueEntry) -> int:
            s = 0
            common = seeker.interests & e.interests
            s += len(common) * 10
            if seeker.country and e.country == seeker.country:
                s += 5
            s -= int(time.monotonic() - e.joined_at)   # prefer waiting longer
            return s

        candidates.sort(key=score, reverse=True)
        return candidates[0].user_id

    def _compatible(self, seeker: QueueEntry, candidate: QueueEntry) -> bool:
        # Skip self
        if seeker.user_id == candidate.user_id:
            return False
        # Skip recent partners
        if candidate.user_id in seeker.past_partners:
            return False
        if seeker.user_id in candidate.past_partners:
            return False
        # Gender filter from seeker's side
        if seeker.gender_filter != "random":
            if candidate.gender not in (seeker.gender_filter, "random"):
                return False
        # Gender filter from candidate's side
        if candidate.gender_filter != "random":
            if seeker.gender not in (candidate.gender_filter, "random"):
                return False
        return True


# ── module-level singleton ───────────────────────────────────
matchmaker = MatchMaker()


# ════════════════════════════════════════════════════════════
#  Flood Guard
# ════════════════════════════════════════════════════════════
class FloodGuard:
    """
    Sliding window rate limiter per user.
    """
    def __init__(self, limit: int = 10, window: int = 10):
        self.limit  = limit
        self.window = window
        self._hits:  Dict[int, List[float]] = {}

    def check(self, user_id: int) -> bool:
        """Returns True if user is flooding (should be blocked)."""
        now  = time.monotonic()
        hits = self._hits.get(user_id, [])
        hits = [t for t in hits if now - t < self.window]
        hits.append(now)
        self._hits[user_id] = hits
        return len(hits) > self.limit

    def reset(self, user_id: int):
        self._hits.pop(user_id, None)


flood_guard = FloodGuard()


# ════════════════════════════════════════════════════════════
#  Bad-word / AI moderation helper
# ════════════════════════════════════════════════════════════
class ContentModerator:
    def __init__(self, wordlist_path: str = "badwords.txt"):
        self._words: Set[str] = set()
        try:
            with open(wordlist_path, "r", encoding="utf-8") as f:
                self._words = {line.strip().lower() for line in f if line.strip()}
            log.info("Loaded %d bad words", len(self._words))
        except FileNotFoundError:
            # seed with a tiny default list
            self._words = {
                "spam", "scam", "nude", "porn",
                "fuck", "shit", "ass", "bitch"
            }

    def is_clean(self, text: str) -> bool:
        """Returns True if message passes moderation."""
        if not text:
            return True
        words = text.lower().split()
        return not any(w in self._words for w in words)

    def reload(self, wordlist_path: str = "badwords.txt"):
        self.__init__(wordlist_path)


moderator = ContentModerator()
