# memory/database.py
"""SQLite Database Manager for Jarvis V2 with 13 Normalized Relational Tables."""

import logging
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.memory.db")


class DatabaseManager:
    """Thread-safe SQLite database manager with normalized 13-table schema."""

    def __init__(self, db_path: str = "data/jarvis.db"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._ensure_db_dir()
        self._init_schema()

    def _ensure_db_dir(self) -> None:
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("PRAGMA journal_mode = WAL")
                    cursor.execute("PRAGMA synchronous = NORMAL")
                except Exception as e:
                    logger.debug("Failed to set WAL mode on SQLite: %s", e)

                # 1. users
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    role TEXT DEFAULT 'ADMIN',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)

                # 2. preferences
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT DEFAULT 'default_user',
                    category TEXT DEFAULT 'general',
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    value_type TEXT DEFAULT 'string',
                    updated_at REAL NOT NULL,
                    UNIQUE(user_id, key)
                )
                """)

                # 3. memories (Long-term facts & knowledge)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT DEFAULT 'default_user',
                    category TEXT DEFAULT 'facts',
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    tags TEXT,
                    confidence REAL DEFAULT 1.0,
                    source TEXT DEFAULT 'user',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(user_id, key)
                )
                """)

                # 4. conversations (Short-term & Episodic logs)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_id TEXT DEFAULT 'default_user',
                    turn_id TEXT NOT NULL,
                    role TEXT NOT NULL, -- user / assistant / system
                    content TEXT NOT NULL,
                    intent TEXT,
                    source TEXT DEFAULT 'cli',
                    metadata TEXT,
                    timestamp REAL NOT NULL
                )
                """)

                # 5. entities (Custom vocabulary, terms & domain objects)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL, -- vocabulary, app, device, person, place
                    name TEXT NOT NULL UNIQUE,
                    normalized_value TEXT NOT NULL,
                    context_id TEXT,
                    metadata TEXT,
                    updated_at REAL NOT NULL
                )
                """)

                # 6. corrections (User assumption corrections)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT DEFAULT 'default_user',
                    concept TEXT NOT NULL,
                    original_value TEXT NOT NULL,
                    corrected_value TEXT NOT NULL,
                    occurrences INTEGER DEFAULT 1,
                    last_updated REAL NOT NULL,
                    UNIQUE(user_id, original_value)
                )
                """)

                # 7. learned_patterns (Habits & usage frequencies)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS learned_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_key TEXT NOT NULL UNIQUE,
                    pattern_type TEXT DEFAULT 'command',
                    frequency INTEGER DEFAULT 1,
                    confidence REAL DEFAULT 1.0,
                    context_data TEXT,
                    last_seen REAL NOT NULL
                )
                """)

                # 8. workflows (Procedural macros & composite routines)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    triggers TEXT NOT NULL, -- JSON array of trigger phrases
                    steps_json TEXT NOT NULL, -- JSON array of steps
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)

                # 9. plugins (Registered plugins & metadata)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS plugins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plugin_name TEXT NOT NULL UNIQUE,
                    version TEXT DEFAULT '1.0.0',
                    description TEXT,
                    is_enabled INTEGER DEFAULT 1,
                    permissions_json TEXT,
                    updated_at REAL NOT NULL
                )
                """)

                # 10. plugin_usage (Plugin execution history & logs)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS plugin_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plugin_name TEXT NOT NULL,
                    action_name TEXT NOT NULL,
                    task_id TEXT,
                    parameters_json TEXT,
                    success INTEGER NOT NULL,
                    result_summary TEXT,
                    error TEXT,
                    execution_time_ms REAL DEFAULT 0.0,
                    timestamp REAL NOT NULL
                )
                """)

                # 11. suggestions (Proactive suggestion events & outcomes)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger_event TEXT NOT NULL,
                    suggestion_text TEXT NOT NULL,
                    frequency INTEGER DEFAULT 1,
                    accepted_count INTEGER DEFAULT 0,
                    last_offered REAL NOT NULL
                )
                """)

                # 12. feedback (User feedback & scores)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id TEXT,
                    user_id TEXT DEFAULT 'default_user',
                    rating INTEGER NOT NULL, -- +1, 0, -1
                    feedback_type TEXT DEFAULT 'explicit',
                    comment TEXT,
                    timestamp REAL NOT NULL
                )
                """)

                # 13. tasks (Working memory active & past task graphs)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    task_title TEXT NOT NULL,
                    user_goal TEXT NOT NULL,
                    status TEXT NOT NULL, -- PENDING, IN_PROGRESS, COMPLETED, FAILED
                    current_step INTEGER DEFAULT 0,
                    total_steps INTEGER DEFAULT 0,
                    execution_graph_json TEXT,
                    created_at REAL NOT NULL,
                    finished_at REAL
                )
                """)

                # 14. custom_aliases (User-learned website and application aliases)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS custom_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    target TEXT NOT NULL,
                    action_type TEXT DEFAULT 'OPEN_WEBSITE',
                    description TEXT,
                    created_by TEXT DEFAULT 'user',
                    created_at REAL NOT NULL,
                    last_used REAL
                )
                """)

                # 14b. website_knowledge (canonical user-learned website records)
                # Kept in the authoritative Jarvis database; custom_aliases is
                # retained for backwards-compatible generic command aliases.
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS website_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    normalized_aliases_json TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    source TEXT NOT NULL DEFAULT 'user_learned',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    usage_count INTEGER NOT NULL DEFAULT 0
                )
                """)

                # 15. task_workflows (Long-horizon Task Continuity Engine persistent states)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_workflows (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    final_status TEXT NOT NULL,
                    current_step INTEGER DEFAULT 0,
                    total_steps INTEGER DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    task_state_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)

                # 16. task_checkpoints (Verified step-by-step checkpoints for crash/restart recovery)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    step_id TEXT NOT NULL,
                    verified INTEGER NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """)

                # 17. task_experience (Previous experience learning, procedures, strategies, and failure patterns)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_experience (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_pattern TEXT NOT NULL,
                    procedure_json TEXT NOT NULL,
                    success_rate REAL DEFAULT 1.0,
                    successful_runs INTEGER DEFAULT 1,
                    failed_runs INTEGER DEFAULT 0,
                    strategies_json TEXT,
                    failure_modes_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)

                # 18. experience_memories (Persistent Experience Learning System: episodic, semantic, procedural, failure, preference)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS experience_memories (
                    id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    query_pattern TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    success_count INTEGER DEFAULT 1,
                    failure_count INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1,
                    superseded_by TEXT,
                    source TEXT NOT NULL,
                    task_metadata_json TEXT,
                    embedding_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_type_active ON experience_memories (memory_type, is_active)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_category ON experience_memories (category)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_query ON experience_memories (query_pattern)")

                # =============================================================
                # LEARNING COMMUNICATION ENGINE (LCE) PERSISTENCE TABLES
                # =============================================================
                # 15. communication_patterns
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS communication_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_phrase TEXT NOT NULL,
                    normalized_phrase TEXT NOT NULL,
                    language TEXT DEFAULT 'hinglish',
                    context_key TEXT DEFAULT 'global',
                    intent TEXT NOT NULL,
                    entities_json TEXT DEFAULT '{}',
                    confidence REAL DEFAULT 0.50,
                    usage_count INTEGER DEFAULT 1,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_used_at REAL NOT NULL,
                    source TEXT DEFAULT 'interaction',
                    status TEXT DEFAULT 'candidate',
                    UNIQUE(normalized_phrase, context_key)
                )
                """)

                # 16. communication_corrections
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS communication_corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_text TEXT NOT NULL,
                    wrong_interpretation TEXT NOT NULL,
                    correct_interpretation TEXT NOT NULL,
                    context_key TEXT DEFAULT 'global',
                    reason TEXT DEFAULT 'user_correction',
                    created_at REAL NOT NULL
                )
                """)

                # 17. communication_feedback
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS communication_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    utterance TEXT NOT NULL,
                    interpretation TEXT NOT NULL,
                    feedback_type TEXT NOT NULL,
                    context_key TEXT DEFAULT 'global',
                    confidence_before REAL NOT NULL,
                    confidence_after REAL NOT NULL,
                    created_at REAL NOT NULL
                )
                """)

                # 18. learned_vocabulary
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS learned_vocabulary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    spoken_form TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    canonical_form TEXT NOT NULL,
                    language TEXT DEFAULT 'hinglish',
                    confidence REAL DEFAULT 0.50,
                    usage_count INTEGER DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)

                # 19. communication_aliases
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS communication_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias TEXT NOT NULL COLLATE NOCASE,
                    canonical_command TEXT NOT NULL,
                    context_key TEXT DEFAULT 'global',
                    confidence REAL DEFAULT 0.50,
                    source TEXT DEFAULT 'learned',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(alias, context_key)
                )
                """)

                # 15. task_workflows (Long-horizon Task Continuity Engine persistent states)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_workflows (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    final_status TEXT NOT NULL,
                    current_step INTEGER DEFAULT 0,
                    total_steps INTEGER DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    task_state_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)

                # 16. task_checkpoints (Verified step-by-step checkpoints for crash/restart recovery)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    step_id TEXT NOT NULL,
                    verified INTEGER NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """)

                # 17. task_experience (Previous experience learning, procedures, strategies, and failure patterns)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_experience (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_pattern TEXT NOT NULL,
                    procedure_json TEXT NOT NULL,
                    success_rate REAL DEFAULT 1.0,
                    successful_runs INTEGER DEFAULT 1,
                    failed_runs INTEGER DEFAULT 0,
                    strategies_json TEXT,
                    failure_modes_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)

                # 18. experience_memories (Persistent Experience Learning System: episodic, semantic, procedural, failure, preference)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS experience_memories (
                    id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    query_pattern TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    success_count INTEGER DEFAULT 1,
                    failure_count INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1,
                    superseded_by TEXT,
                    source TEXT NOT NULL,
                    task_metadata_json TEXT,
                    embedding_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_type_active ON experience_memories (memory_type, is_active)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_category ON experience_memories (category)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_query ON experience_memories (query_pattern)")

                # =============================================================
                # LEARNING COMMUNICATION ENGINE (LCE) PERSISTENCE TABLES
                # =============================================================
                # 15. communication_patterns
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS communication_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_phrase TEXT NOT NULL,
                    normalized_phrase TEXT NOT NULL,
                    language TEXT DEFAULT 'hinglish',
                    context_key TEXT DEFAULT 'global',
                    intent TEXT NOT NULL,
                    entities_json TEXT DEFAULT '{}',
                    confidence REAL DEFAULT 0.50,
                    usage_count INTEGER DEFAULT 1,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_used_at REAL NOT NULL,
                    source TEXT DEFAULT 'interaction',
                    status TEXT DEFAULT 'candidate',
                    UNIQUE(normalized_phrase, context_key)
                )
                """)

                # 16. communication_corrections
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS communication_corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_text TEXT NOT NULL,
                    wrong_interpretation TEXT NOT NULL,
                    correct_interpretation TEXT NOT NULL,
                    context_key TEXT DEFAULT 'global',
                    reason TEXT DEFAULT 'user_correction',
                    created_at REAL NOT NULL
                )
                """)

                # 17. communication_feedback
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS communication_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    utterance TEXT NOT NULL,
                    interpretation TEXT NOT NULL,
                    feedback_type TEXT NOT NULL,
                    context_key TEXT DEFAULT 'global',
                    confidence_before REAL NOT NULL,
                    confidence_after REAL NOT NULL,
                    created_at REAL NOT NULL
                )
                """)

                # 18. learned_vocabulary
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS learned_vocabulary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    spoken_form TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    canonical_form TEXT NOT NULL,
                    language TEXT DEFAULT 'hinglish',
                    confidence REAL DEFAULT 0.50,
                    usage_count INTEGER DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)

                # 19. communication_aliases
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS communication_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alias TEXT NOT NULL COLLATE NOCASE,
                    canonical_command TEXT NOT NULL,
                    context_key TEXT DEFAULT 'global',
                    confidence REAL DEFAULT 0.50,
                    source TEXT DEFAULT 'learned',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(alias, context_key)
                )
                """)

                # 20. communication_preferences
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS communication_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT DEFAULT 'default_user',
                    preference_key TEXT NOT NULL,
                    preference_val TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(user_id, preference_key)
                )
                """)

                # 21. proactive_activity_events (Structured historical desktop activity events)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS proactive_activity_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    importance TEXT NOT NULL,
                    application TEXT,
                    window_title TEXT,
                    content_title TEXT,
                    website TEXT,
                    url TEXT,
                    timestamp REAL NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    metadata_json TEXT
                )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_act_events_time ON proactive_activity_events(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_act_events_site ON proactive_activity_events(website)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_act_events_type ON proactive_activity_events(event_type)")

                # 22. conversation_sessions
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT DEFAULT 'default_user',
                    title TEXT,
                    active_topic TEXT DEFAULT 'general',
                    conversation_mode TEXT DEFAULT 'CASUAL',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)

                # 23. conversation_messages
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    speaker TEXT NOT NULL,
                    text TEXT NOT NULL,
                    normalized_text TEXT,
                    dialogue_act TEXT,
                    topic TEXT,
                    entities_json TEXT DEFAULT '{}',
                    timestamp REAL NOT NULL
                )
                """)

                # 24. episodic_memory
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT DEFAULT 'default_user',
                    type TEXT NOT NULL,
                    topic TEXT,
                    fact TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    created_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    expires_at REAL,
                    metadata_json TEXT DEFAULT '{}'
                )
                """)

                # 25. semantic_memory
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS semantic_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT DEFAULT 'default_user',
                    category TEXT DEFAULT 'facts',
                    key TEXT NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    tags TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)

                # 26. conversation_topics
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    subtopic TEXT,
                    status TEXT DEFAULT 'active',
                    started_at REAL NOT NULL,
                    last_active_at REAL NOT NULL
                )
                """)

                # 27. memory_links
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    created_at REAL NOT NULL
                )
                """)

                # 28. memory_embeddings
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_type TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    vector_json TEXT,
                    text_content TEXT,
                    created_at REAL NOT NULL
                )
                """)

                # Seed default user if not exists
                cursor.execute("""
                INSERT OR IGNORE INTO users (id, username, display_name, role, created_at, updated_at)
                VALUES ('default_user', 'boss', 'Boss', 'ADMIN', ?, ?)
                """, (time.time(), time.time()))

                # Safe schema migrations for legacy tables
                try:
                    cursor.execute("PRAGMA table_info(memories)")
                    mem_cols = {row[1] for row in cursor.fetchall()}
                    # Unified-memory extension (Phase 8): typed, scored, expirable
                    # memories stay the SINGLE canonical long-term table — no new
                    # table, no new database. All columns nullable/defaulted so
                    # legacy rows keep working untouched.
                    for col, col_def in [
                        ("memory_type", "TEXT DEFAULT 'FACT'"),
                        ("importance", "REAL DEFAULT 0.5"),
                        ("last_used_at", "REAL"),
                        ("expires_at", "REAL"),
                        ("metadata_json", "TEXT DEFAULT '{}'"),
                    ]:
                        if col not in mem_cols:
                            cursor.execute(f"ALTER TABLE memories ADD COLUMN {col} {col_def}")
                except Exception as e:
                    logger.warning(f"Schema migration check for memories: {e}")

                try:
                    cursor.execute("PRAGMA table_info(episodic_memory)")
                    episodic_cols = {row[1] for row in cursor.fetchall()}
                    if episodic_cols and "topic" not in episodic_cols:
                        logger.info("Migrating legacy episodic_memory table schema...")
                        for col, col_def in [
                            ("user_id", "TEXT DEFAULT 'default_user'"),
                            ("type", "TEXT DEFAULT 'interaction'"),
                            ("topic", "TEXT DEFAULT 'general'"),
                            ("fact", "TEXT DEFAULT ''"),
                            ("confidence", "REAL DEFAULT 1.0"),
                            ("created_at", "REAL DEFAULT 0.0"),
                            ("last_seen_at", "REAL DEFAULT 0.0"),
                            ("expires_at", "REAL"),
                            ("metadata_json", "TEXT DEFAULT '{}'")
                        ]:
                            if col not in episodic_cols:
                                cursor.execute(f"ALTER TABLE episodic_memory ADD COLUMN {col} {col_def}")
                        if "user_input" in episodic_cols and "timestamp" in episodic_cols:
                            cursor.execute("""
                            UPDATE episodic_memory
                            SET fact = COALESCE(user_input, '') || CASE WHEN assistant_response IS NOT NULL THEN ' -> ' || assistant_response ELSE '' END,
                                created_at = timestamp,
                                last_seen_at = timestamp
                            WHERE (fact IS NULL OR fact = '') AND timestamp IS NOT NULL
                            """)
                except Exception as e:
                    logger.warning(f"Schema migration check for episodic_memory: {e}")

                try:
                    cursor.execute("PRAGMA table_info(semantic_memory)")
                    semantic_cols = {row[1] for row in cursor.fetchall()}
                    if semantic_cols and "user_id" not in semantic_cols:
                        logger.info("Migrating legacy semantic_memory table schema...")
                        cursor.execute("ALTER TABLE semantic_memory ADD COLUMN user_id TEXT DEFAULT 'default_user'")
                except Exception as e:
                    logger.warning(f"Schema migration check for semantic_memory: {e}")

                # Indices for high performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_time ON conversations(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_key ON memories(key)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_cat ON memories(category)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(memory_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_expiry ON memories(expires_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_msg_sess ON conversation_messages(session_id, timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_msg_topic ON conversation_messages(topic)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodic_topic ON episodic_memory(topic, confidence)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodic_type ON episodic_memory(type, last_seen_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_semantic_cat ON semantic_memory(category)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_links_src ON memory_links(source_type, source_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_links_tgt ON memory_links(target_type, target_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_pref_key ON preferences(key)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_entity_name ON entities(name)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_plugin_usage_name ON plugin_usage(plugin_name)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_website_knowledge_updated ON website_knowledge(updated_at DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comm_pat_norm ON communication_patterns(normalized_phrase, context_key)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comm_pat_conf ON communication_patterns(confidence)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comm_voc_spoken ON learned_vocabulary(spoken_form)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comm_alias ON communication_aliases(alias, context_key)")

                conn.commit()

        logger.info(f"Initialized SQLite schema with LCE and conversation support at {self.db_path}")

    def execute_query(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]

    def execute_update(self, sql: str, params: Tuple[Any, ...] = ()) -> int:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                conn.commit()
                return cursor.rowcount
