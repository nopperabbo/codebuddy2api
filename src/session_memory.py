"""Session Memory — per-conversation session memory with auto-cleanup."""
import hashlib
import json
import os
import re
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path(".sessions")
MAX_FACTS = 20
SESSION_TTL_SECONDS = 24 * 60 * 60
_CLEANUP_INTERVAL = 50
_cleanup_counter = 0

FILE_PATH_PATTERN = re.compile(r"(?:^|[\s\"'`(])(/[\w/.-]+\.\w+|[\w][\w/.-]*\.\w+)")
DECISION_PATTERN = re.compile(
    r"(?:I'll use|let's go with|the approach is|I'll implement|we should use|I chose|using)\s+(.{5,80})",
    re.IGNORECASE,
)


def _ensure_sessions_dir():
    SESSIONS_DIR.mkdir(exist_ok=True)


def _session_path(session_id: str) -> Path:
    safe_id = re.sub(r"[^\w\-]", "_", session_id)
    return SESSIONS_DIR / f"{safe_id}.json"


def _load_session(session_id: str) -> dict:
    path = _session_path(session_id)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            age = time.time() - data.get("last_updated_ts", 0)
            if age > SESSION_TTL_SECONDS:
                path.unlink(missing_ok=True)
                return _new_session(session_id)
            return data
        except (json.JSONDecodeError, OSError):
            return _new_session(session_id)
    return _new_session(session_id)


def _new_session(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "key_facts": [],
        "recent_files": [],
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "last_updated_ts": time.time(),
    }


def _save_session(session_id: str, data: dict):
    _ensure_sessions_dir()
    data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data["last_updated_ts"] = time.time()
    try:
        _session_path(session_id).write_text(json.dumps(data, indent=2))
    except OSError as e:
        logger.warning(f"Failed to save session {session_id}: {e}")


def _derive_session_id(messages: list) -> str:
    if messages:
        first_content = messages[0].get("content", "")
        if isinstance(first_content, str):
            return hashlib.sha256(first_content.encode()).hexdigest()[:16]
    return hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]


def cleanup_old_sessions():
    if not SESSIONS_DIR.exists():
        return
    now = time.time()
    try:
        for f in SESSIONS_DIR.iterdir():
            if f.suffix == ".json":
                try:
                    data = json.loads(f.read_text())
                    if now - data.get("last_updated_ts", 0) > SESSION_TTL_SECONDS:
                        f.unlink(missing_ok=True)
                        logger.debug(f"Cleaned up expired session: {f.name}")
                except (json.JSONDecodeError, OSError):
                    pass
    except OSError:
        pass


def inject_session_context(messages: list, session_id: str | None) -> list:
    if not session_id:
        session_id = _derive_session_id(messages)

    session = _load_session(session_id)
    facts = session.get("key_facts", [])

    if not facts:
        return messages

    context_text = "Session context: " + "; ".join(facts)
    result = list(messages)

    insert_idx = 0
    if result and result[0].get("role") == "system":
        insert_idx = 1

    result.insert(insert_idx, {"role": "system", "content": context_text})
    return result


def extract_and_save_facts(response_content: str, session_id: str | None):
    if not session_id or not response_content:
        return

    session = _load_session(session_id)
    facts = session.get("key_facts", [])
    files = session.get("recent_files", [])

    file_matches = FILE_PATH_PATTERN.findall(response_content[:5000])
    for fp in file_matches:
        fp = fp.strip()
        if fp and fp not in files:
            files.append(fp)

    decision_matches = DECISION_PATTERN.findall(response_content[:5000])
    for decision in decision_matches:
        decision = decision.strip().rstrip(".,;:")
        if decision and decision not in facts:
            facts.append(decision)

    facts = facts[-MAX_FACTS:]
    files = files[-MAX_FACTS:]

    session["key_facts"] = facts
    session["recent_files"] = files
    _save_session(session_id, session)

    global _cleanup_counter
    _cleanup_counter += 1
    if _cleanup_counter >= _CLEANUP_INTERVAL:
        _cleanup_counter = 0
        cleanup_old_sessions()
