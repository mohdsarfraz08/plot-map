"""
In-memory, thread-safe, LRU Session Registry for Stage 3B.6 Lazy Orchestration.

Manages compilation sessions, realized candidate assets, and TTL expiration
without external dependencies (Redis, database, Celery).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import hashlib
import threading
import time
from typing import Any, Dict, List, Optional
import uuid


DEFAULT_MAX_SESSIONS = 100
DEFAULT_TTL_SECONDS = 1800  # 30 minutes


@dataclass
class CandidateRecord:
    """Stores full realized assets and summary metadata for a candidate."""
    candidate_id: str
    strategy_id: str
    name: str
    rank: int
    is_selected: bool
    status: str  # "success", "spatially_infeasible", "error"
    strategic_score: float
    spatial_score: float
    composite_score: float
    trade_offs: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    layout: Dict[str, Any] = field(default_factory=dict)
    boundaries: Dict[str, Any] = field(default_factory=dict)
    geometry: Dict[str, Any] = field(default_factory=dict)
    floors: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    drawing_svg: Optional[str] = None
    explanation: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionRecord:
    """Stores full session state including design problem, winner, and all candidates."""
    session_id: str
    created_at: float
    last_accessed_at: float
    prompt_hash: str
    prompt: str
    selected_candidate_id: str
    candidates: Dict[str, CandidateRecord] = field(default_factory=dict)
    intent: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class SessionRegistry:
    """
    Thread-safe, in-memory LRU session cache with deterministic TTL expiration.
    """

    def __init__(
        self,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ):
        self._max_sessions = max_sessions
        self._ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        self._sessions: OrderedDict[str, SessionRecord] = OrderedDict()
        self._prompt_hash_to_session: Dict[str, str] = {}

    @staticmethod
    def compute_prompt_hash(prompt: str) -> str:
        """Deterministically compute SHA-256 hash of normalized user prompt."""
        normalized = " ".join(prompt.strip().lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def remove_expired(self, current_time: Optional[float] = None) -> int:
        """Remove sessions that have exceeded their TTL. Returns count removed."""
        now = current_time if current_time is not None else time.time()
        expired_ids: List[str] = []

        with self._lock:
            for session_id, session in self._sessions.items():
                if now - session.last_accessed_at > self._ttl_seconds:
                    expired_ids.append(session_id)

            for s_id in expired_ids:
                session = self._sessions.pop(s_id, None)
                if session and session.prompt_hash in self._prompt_hash_to_session:
                    if self._prompt_hash_to_session[session.prompt_hash] == s_id:
                        del self._prompt_hash_to_session[session.prompt_hash]

        return len(expired_ids)

    def create_session(
        self,
        prompt: str,
        selected_candidate_id: str,
        intent: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> SessionRecord:
        """Creates and stores a new session with LRU eviction."""
        now = time.time()
        self.remove_expired(now)

        s_id = session_id or f"session_{uuid.uuid4().hex[:12]}"
        p_hash = self.compute_prompt_hash(prompt)

        session = SessionRecord(
            session_id=s_id,
            created_at=now,
            last_accessed_at=now,
            prompt_hash=p_hash,
            prompt=prompt,
            selected_candidate_id=selected_candidate_id,
            candidates={},
            intent=intent,
            metadata=metadata or {},
        )

        with self._lock:
            # Enforce max sessions LRU limit
            while len(self._sessions) >= self._max_sessions:
                oldest_id, oldest_sess = self._sessions.popitem(last=False)
                if oldest_sess.prompt_hash in self._prompt_hash_to_session:
                    if self._prompt_hash_to_session[oldest_sess.prompt_hash] == oldest_id:
                        del self._prompt_hash_to_session[oldest_sess.prompt_hash]

            self._sessions[s_id] = session
            self._prompt_hash_to_session[p_hash] = s_id

        return session

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        """Retrieves a session by ID and updates its LRU position, or None if expired/not found."""
        now = time.time()
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None

            # Check expiration
            if now - session.last_accessed_at > self._ttl_seconds:
                self._sessions.pop(session_id, None)
                if session.prompt_hash in self._prompt_hash_to_session:
                    if self._prompt_hash_to_session[session.prompt_hash] == session_id:
                        del self._prompt_hash_to_session[session.prompt_hash]
                return None

            # Update access time and move to end (MRU)
            session.last_accessed_at = now
            self._sessions.move_to_end(session_id, last=True)
            return session

    def get_session_by_prompt(self, prompt: str) -> Optional[SessionRecord]:
        """Finds an existing valid session matching the normalized prompt hash."""
        p_hash = self.compute_prompt_hash(prompt)
        with self._lock:
            s_id = self._prompt_hash_to_session.get(p_hash)
            if not s_id:
                return None
            return self.get_session(s_id)

    def store_candidate(self, session_id: str, candidate: CandidateRecord) -> bool:
        """Stores a candidate record inside an active session."""
        session = self.get_session(session_id)
        if not session:
            return False

        with self._lock:
            session.candidates[candidate.candidate_id] = candidate
            return True

    def get_candidate(self, session_id: str, candidate_id: str) -> Optional[CandidateRecord]:
        """Retrieves a specific candidate record from an active session."""
        session = self.get_session(session_id)
        if not session:
            return None

        with self._lock:
            return session.candidates.get(candidate_id)

    def clear(self) -> None:
        """Clears all sessions from the registry."""
        with self._lock:
            self._sessions.clear()
            self._prompt_hash_to_session.clear()


# Global registry singleton
_GLOBAL_REGISTRY: Optional[SessionRegistry] = None
_REGISTRY_LOCK = threading.Lock()


def get_session_registry() -> SessionRegistry:
    """Returns the global SessionRegistry singleton instance."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        with _REGISTRY_LOCK:
            if _GLOBAL_REGISTRY is None:
                _GLOBAL_REGISTRY = SessionRegistry()
    return _GLOBAL_REGISTRY
