"""Chat history repository for persistent conversation storage."""

import sqlite3
from typing import List, Dict
from ..utils.logger import get_logger

logger = get_logger(__name__)


def ensure_chat_tables(conn: sqlite3.Connection) -> None:
    """Ensure chat history tables exist (idempotent)."""
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT CHECK(role IN ('user','assistant')) NOT NULL,
                content TEXT NOT NULL,
                ts DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_conv_user_ts
            ON chat_messages(conversation_id, user_id, ts)
        """)
        
        conn.commit()
        logger.info("chat_tables_ensured")
    except Exception as e:
        logger.warning("chat_tables_creation_failed", error=str(e))


def initialize_chat_db() -> None:
    """Initialize chat database tables - convenience wrapper."""
    from ..utils.config import settings
    try:
        conn = sqlite3.connect(settings.database_url.replace("sqlite:///", ""))
        ensure_chat_tables(conn)
        conn.close()
    except Exception as e:
        logger.error("chat_db_initialization_failed", error=str(e))


def save_message(conn: sqlite3.Connection, conversation_id: str, user_id: int, role: str, content: str) -> None:
    """Save a chat message to the database."""
    try:
        conn.execute(
            "INSERT INTO chat_messages (conversation_id, user_id, role, content) VALUES (?,?,?,?)",
            (conversation_id, user_id, role, content),
        )
        conn.commit()
    except Exception as e:
        logger.warning("chat_save_failed", error=str(e), conversation_id=conversation_id)


def load_recent_messages(conn: sqlite3.Connection, conversation_id: str, user_id: int, limit: int) -> List[Dict[str, str]]:
    """Load recent chat messages for a conversation, ordered oldest→newest."""
    try:
        rows = conn.execute(
            """
            SELECT role, content
            FROM chat_messages
            WHERE conversation_id = ? AND user_id = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (conversation_id, user_id, limit)
        ).fetchall()
        # reverse to oldest→newest for LLM
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
    except Exception as e:
        logger.warning("chat_load_failed", error=str(e), conversation_id=conversation_id)
        return []
