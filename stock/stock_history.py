# stock/stock_history.py
"""
Stock Recommendation History and Persistent Snapshot Repository for Jarvis V2.1.
Maintains permanent, immutable historical snapshots of all stock suggestions,
price snapshots, and lifecycle audit events in SQLite.
"""

from datetime import datetime
import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid
from core.timezone_manager import get_timezone_manager

from .stock_models import (
    PriceSnapshotRecord,
    RecommendationRecord,
    StockCandidateResult,
    StockEventRecord,
    StockQueryParams,
)

logger = logging.getLogger("jarvis.stock.history")

IST_TZ = get_timezone_manager().get_ist_timezone()


class StockHistoryDatabase:
    """Thread-safe SQLite repository managing permanent stock recommendation snapshots."""

    _instance: Optional["StockHistoryDatabase"] = None
    _singleton_lock = threading.Lock()

    def __init__(self, db_path: str = "data/jarvis.db"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._ensure_db_dir()
        self._init_schema()

    @classmethod
    def get_instance(cls, db_path: str = "data/jarvis.db") -> "StockHistoryDatabase":
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = cls(db_path=db_path)
            return cls._instance

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
        """Initializes tables for recommendation sessions, recommendations, snapshots, and events."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("PRAGMA journal_mode = WAL")
                    cursor.execute("PRAGMA synchronous = NORMAL")
                except Exception as e:
                    logger.debug("Failed to set WAL mode: %s", e)

                # 1. stock_recommendation_sessions
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_recommendation_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    criteria_json TEXT NOT NULL,
                    candidate_count INTEGER DEFAULT 0,
                    timestamp REAL NOT NULL
                )
                """)

                # 2. stock_recommendations
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_recommendations (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    exchange TEXT DEFAULT 'NSE',
                    recommendation_date TEXT NOT NULL,
                    recommendation_time TEXT NOT NULL,
                    timezone TEXT DEFAULT 'Asia/Kolkata',
                    reference_price REAL NOT NULL,
                    current_price_at_analysis REAL NOT NULL,
                    target_1 REAL,
                    target_2 REAL,
                    target_method TEXT,
                    exit_price REAL,
                    invalidation_price REAL,
                    exit_type TEXT DEFAULT 'setup_invalidation',
                    maximum_holding_period_days INTEGER DEFAULT 30,
                    time_exit_date TEXT,
                    recommendation_type TEXT DEFAULT 'SWING_LONG',
                    investment_horizon TEXT,
                    risk_profile TEXT,
                    sector TEXT,
                    market_cap TEXT,
                    technical_reason TEXT,
                    fundamental_reason TEXT,
                    risk_reason TEXT,
                    selection_criteria_json TEXT,
                    data_source TEXT,
                    data_timestamp TEXT,
                    analysis_version TEXT,
                    strategy_version TEXT,
                    status TEXT DEFAULT 'ACTIVE',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """)

                # 3. stock_price_snapshots
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_price_snapshots (
                    id TEXT PRIMARY KEY,
                    recommendation_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    timestamp REAL NOT NULL,
                    source TEXT,
                    data_timestamp TEXT
                )
                """)

                # 4. stock_events
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_events (
                    id TEXT PRIMARY KEY,
                    recommendation_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    old_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    price REAL NOT NULL,
                    trigger_detail TEXT,
                    timestamp REAL NOT NULL
                )
                """)

                # Indices
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_rec_symbol ON stock_recommendations (symbol)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_rec_date ON stock_recommendations (recommendation_date)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_rec_session ON stock_recommendations (session_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_rec_status ON stock_recommendations (status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_snaps_rec ON stock_price_snapshots (recommendation_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_events_rec ON stock_events (recommendation_id)")

                conn.commit()

    def save_session(
        self,
        params: StockQueryParams,
        candidates: List[StockCandidateResult],
        session_id: Optional[str] = None,
        user_id: str = "default_user",
        timestamp: Optional[float] = None,
    ) -> Tuple[str, List[RecommendationRecord]]:
        """
        Atomically saves recommendation session and creates immutable RecommendationRecord
        for every candidate returned by the screener.
        """
        now_ts = timestamp or time.time()
        now_dt = datetime.fromtimestamp(now_ts, tz=IST_TZ)
        date_str = now_dt.strftime("%Y-%m-%d")
        time_str = now_dt.strftime("%H:%M:%S")

        sid = session_id or f"REC-{now_dt.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        records: List[RecommendationRecord] = []

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 1. Insert session
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO stock_recommendation_sessions (
                        id, user_id, criteria_json, candidate_count, timestamp
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (sid, user_id, params.model_dump_json(), len(candidates), now_ts),
                )

                # 2. Insert recommendations
                for cand in candidates:
                    rec_id = f"REC-{cand.symbol.replace('.NS', '')}-{now_dt.strftime('%Y%m%d%H%M%S')}"
                    ref_price = float(cand.reference_price or cand.current_price)
                    t1 = float(cand.target_1) if cand.target_1 is not None else None
                    t2 = float(cand.target_2) if cand.target_2 is not None else None
                    inv_price = float(cand.invalidation_price or cand.invalidation_level) if (cand.invalidation_price or cand.invalidation_level) else None

                    rec = RecommendationRecord(
                        id=rec_id,
                        session_id=sid,
                        user_id=user_id,
                        symbol=cand.symbol,
                        company_name=cand.company_name,
                        exchange="NSE",
                        recommendation_date=date_str,
                        recommendation_time=time_str,
                        timezone="Asia/Kolkata",
                        reference_price=ref_price,
                        current_price_at_analysis=cand.current_price,
                        target_1=t1,
                        target_2=t2,
                        target_method=cand.target_method or "risk_reward",
                        exit_price=inv_price,
                        invalidation_price=inv_price,
                        exit_type="setup_invalidation",
                        maximum_holding_period_days=cand.holding_period_days or 30,
                        time_exit_date=cand.time_exit_date,
                        recommendation_type="SWING_LONG",
                        investment_horizon=params.horizon,
                        risk_profile=params.risk,
                        sector=cand.sector,
                        market_cap=cand.market_cap,
                        technical_reason=cand.technical_summary,
                        fundamental_reason=cand.fundamental_summary,
                        risk_reason="; ".join(cand.risks) if cand.risks else "",
                        selection_criteria_json=params.model_dump_json(),
                        data_source=cand.data_source,
                        data_timestamp=cand.data_timestamp,
                        analysis_version="v2.1",
                        strategy_version="v1.0-multi-factor-equity",
                        status="ACTIVE",
                        created_at=now_ts,
                        updated_at=now_ts,
                    )
                    records.append(rec)

                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO stock_recommendations (
                            id, session_id, user_id, symbol, company_name, exchange,
                            recommendation_date, recommendation_time, timezone, reference_price,
                            current_price_at_analysis, target_1, target_2, target_method, exit_price,
                            invalidation_price, exit_type, maximum_holding_period_days, time_exit_date,
                            recommendation_type, investment_horizon, risk_profile, sector, market_cap,
                            technical_reason, fundamental_reason, risk_reason, selection_criteria_json,
                            data_source, data_timestamp, analysis_version, strategy_version, status,
                            created_at, updated_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?, ?, ?,
                            ?, ?
                        )
                        """,
                        (
                            rec.id, rec.session_id, rec.user_id, rec.symbol, rec.company_name, rec.exchange,
                            rec.recommendation_date, rec.recommendation_time, rec.timezone, rec.reference_price,
                            rec.current_price_at_analysis, rec.target_1, rec.target_2, rec.target_method, rec.exit_price,
                            rec.invalidation_price, rec.exit_type, rec.maximum_holding_period_days, rec.time_exit_date,
                            rec.recommendation_type, rec.investment_horizon, rec.risk_profile, rec.sector, rec.market_cap,
                            rec.technical_reason, rec.fundamental_reason, rec.risk_reason, rec.selection_criteria_json,
                            rec.data_source, rec.data_timestamp, rec.analysis_version, rec.strategy_version, rec.status,
                            rec.created_at, rec.updated_at
                        ),
                    )

                    # 3. Initial price snapshot
                    cursor.execute(
                        """
                        INSERT INTO stock_price_snapshots (
                            id, recommendation_id, symbol, price, timestamp, source, data_timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (str(uuid.uuid4()), rec.id, rec.symbol, rec.reference_price, now_ts, rec.data_source, rec.data_timestamp),
                    )

                    # 4. Initial RECOMMENDED audit event
                    cursor.execute(
                        """
                        INSERT INTO stock_events (
                            id, recommendation_id, symbol, event_type, old_status, new_status,
                            price, trigger_detail, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()), rec.id, rec.symbol, "RECOMMENDED",
                            "NONE", "ACTIVE", rec.reference_price,
                            f"Recommended at ₹{rec.reference_price:.2f} (T1: ₹{rec.target_1}, T2: ₹{rec.target_2}, Invalidation: ₹{rec.invalidation_price})",
                            now_ts
                        ),
                    )

                conn.commit()

        logger.info("StockHistoryDatabase: Saved session '%s' with %d recommendations.", sid, len(records))
        return sid, records

    def get_recommendation(self, rec_id: str) -> Optional[RecommendationRecord]:
        """Retrieves a single recommendation record by ID."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM stock_recommendations WHERE id = ?", (rec_id,))
                row = cursor.fetchone()
                if row:
                    return RecommendationRecord(**dict(row))
        return None

    def get_latest_recommendation(self) -> Optional[RecommendationRecord]:
        """Retrieves the most recent recommendation record."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM stock_recommendations ORDER BY created_at DESC LIMIT 1")
                row = cursor.fetchone()
                if row:
                    return RecommendationRecord(**dict(row))
        return None

    def get_recommendations_by_date(self, date_str: str) -> List[RecommendationRecord]:
        """Retrieves recommendations for a specific YYYY-MM-DD date."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM stock_recommendations WHERE recommendation_date = ? ORDER BY created_at DESC",
                    (date_str,),
                )
                rows = cursor.fetchall()
                return [RecommendationRecord(**dict(r)) for r in rows]

    def get_recommendations_by_symbol(self, symbol: str) -> List[RecommendationRecord]:
        """Retrieves recommendations matching a stock symbol (e.g. 'TCS' or 'TCS.NS')."""
        clean_sym = symbol.upper().replace(".NS", "")
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM stock_recommendations WHERE symbol LIKE ? OR symbol = ? ORDER BY created_at DESC",
                    (f"%{clean_sym}%", clean_sym),
                )
                rows = cursor.fetchall()
                return [RecommendationRecord(**dict(r)) for r in rows]

    def get_all_recommendations(self, limit: int = 50) -> List[RecommendationRecord]:
        """Retrieves recent recommendations across all sessions."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM stock_recommendations ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()
                return [RecommendationRecord(**dict(r)) for r in rows]

    def record_price_snapshot(
        self,
        recommendation_id: str,
        symbol: str,
        price: float,
        source: str = "NSE_LIVE",
        data_timestamp: str = "",
        timestamp: Optional[float] = None,
    ) -> PriceSnapshotRecord:
        """Records a new market price snapshot in stock_price_snapshots."""
        now_ts = timestamp or time.time()
        snap = PriceSnapshotRecord(
            id=str(uuid.uuid4()),
            recommendation_id=recommendation_id,
            symbol=symbol,
            price=price,
            timestamp=now_ts,
            source=source,
            data_timestamp=data_timestamp,
        )
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO stock_price_snapshots (
                        id, recommendation_id, symbol, price, timestamp, source, data_timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (snap.id, snap.recommendation_id, snap.symbol, snap.price, snap.timestamp, snap.source, snap.data_timestamp),
                )
                conn.commit()
        return snap

    def get_price_snapshots(self, recommendation_id: str) -> List[PriceSnapshotRecord]:
        """Retrieves all historical price snapshots for a recommendation."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM stock_price_snapshots WHERE recommendation_id = ? ORDER BY timestamp ASC",
                    (recommendation_id,),
                )
                rows = cursor.fetchall()
                return [PriceSnapshotRecord(**dict(r)) for r in rows]

    def record_event(
        self,
        recommendation_id: str,
        symbol: str,
        event_type: str,
        old_status: str,
        new_status: str,
        price: float,
        trigger_detail: str = "",
        timestamp: Optional[float] = None,
    ) -> StockEventRecord:
        """Records an audit event in stock_events."""
        now_ts = timestamp or time.time()
        evt = StockEventRecord(
            id=str(uuid.uuid4()),
            recommendation_id=recommendation_id,
            symbol=symbol,
            event_type=event_type,
            old_status=old_status,
            new_status=new_status,
            price=price,
            trigger_detail=trigger_detail,
            timestamp=now_ts,
        )
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO stock_events (
                        id, recommendation_id, symbol, event_type, old_status, new_status,
                        price, trigger_detail, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (evt.id, evt.recommendation_id, evt.symbol, evt.event_type, evt.old_status, evt.new_status, evt.price, evt.trigger_detail, evt.timestamp),
                )
                conn.commit()
        return evt

    def get_events(self, recommendation_id: str) -> List[StockEventRecord]:
        """Retrieves audit trail events for a recommendation."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM stock_events WHERE recommendation_id = ? ORDER BY timestamp ASC",
                    (recommendation_id,),
                )
                rows = cursor.fetchall()
                return [StockEventRecord(**dict(r)) for r in rows]

    def update_status(self, recommendation_id: str, new_status: str) -> bool:
        """
        Updates recommendation lifecycle status ONLY.
        NEVER overwrites reference_price, target_1, target_2, or invalidation_price.
        """
        now_ts = time.time()
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE stock_recommendations SET status = ?, updated_at = ? WHERE id = ?",
                    (new_status, now_ts, recommendation_id),
                )
                conn.commit()
                return cursor.rowcount > 0
