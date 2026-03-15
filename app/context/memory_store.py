"""In-memory fallback store for conversation memory when DB is unavailable."""

import os
from collections import deque, defaultdict
from typing import Dict, List, Any
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Global in-memory store with conversation-specific deques
_memory_store: Dict[str, deque] = defaultdict(lambda: deque(maxlen=int(os.getenv('MEMORY_WINDOW', '6'))))


def append_message_memory(conversation_id: str, user_id: int, role: str, content: str):
    """Append message to in-memory store."""
    try:
        key = f"{conversation_id}:{user_id}"
        message = {
            "role": role,
            "content": content,
            "ts": None  # No timestamp for in-memory store
        }
        _memory_store[key].append(message)
        logger.debug("message_stored_in_memory", conversation_id=conversation_id, role=role)
    except Exception as e:
        logger.warning("memory_store_failed", error=str(e))


def load_recent_messages_memory(conversation_id: str, user_id: int, limit: int = 6) -> List[Dict[str, Any]]:
    """Load recent messages from in-memory store."""
    try:
        key = f"{conversation_id}:{user_id}"
        messages = list(_memory_store[key])
        # Return up to limit messages (already in chronological order due to deque)
        return messages[-limit:] if len(messages) > limit else messages
    except Exception as e:
        logger.warning("memory_load_failed", error=str(e))
        return []


def clear_conversation_memory(conversation_id: str, user_id: int):
    """Clear memory for a specific conversation (for testing/cleanup)."""
    try:
        key = f"{conversation_id}:{user_id}"
        if key in _memory_store:
            del _memory_store[key]
            logger.debug("conversation_memory_cleared", conversation_id=conversation_id)
    except Exception as e:
        logger.warning("memory_clear_failed", error=str(e))
