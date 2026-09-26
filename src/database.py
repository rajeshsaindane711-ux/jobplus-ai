"""
JobPlus AI — Production SQLite Database Engine
Manages job storage, application tracking, self-learning Q&A memory, and audit logging.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import contextmanager
from src.utils.logger import logger

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobplus.db"
DEFAULT_QA_PATH = Path(__file__).resolve().parent.parent / "data" / "learned_qa.json"


class DatabaseTracker:
    """Production Database Manager for JobPlus AI."""

    def __init__(self, db_path: Optional[Path] = None, qa_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH).resolve()
        self.qa_path = Path(qa_path or DEFAULT_QA_PATH).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._sync_qa_from_json()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=20.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Creates full production schema if not exists."""
        with self._get_connection() as conn:
            # 1. Applications Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT,
                    url TEXT,
                    status TEXT NOT NULL DEFAULT 'applied',
                    resume_used TEXT DEFAULT 'DevOps_SRE_Master.pdf',
                    notes TEXT,
                    screenshot_path TEXT,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(platform, job_id)
                )
            """)

            # 2. Jobs Radar Table (Discovered job listings)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT,
                    url TEXT NOT NULL,
                    match_score REAL DEFAULT 90.0,
                    min_salary REAL,
                    max_salary REAL,
                    experience_required REAL,
                    status TEXT NOT NULL DEFAULT 'discovered',
                    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(platform, job_id)
                )
            """)

            # 3. Knowledge Bank (Screening Q&A)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS qa_bank (
                    key TEXT PRIMARY KEY,
                    category TEXT NOT NULL DEFAULT 'general',
                    question_pattern TEXT NOT NULL,
                    answer_text TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 4. Audit Log Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Performance Indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_apps_platform_date ON applications(platform, applied_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_match_status ON jobs(status, match_score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qa_category ON qa_bank(category)")
            conn.commit()

    def _sync_qa_from_json(self):
        """Populates qa_bank from learned_qa.json if file exists and db table is empty."""
        try:
            if not self.qa_path.exists():
                return
            with open(self.qa_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM qa_bank")
                count = cursor.fetchone()[0]
                if count == 0:
                    for key, ans in data.items():
                        cat = "technical" if any(t in key for t in ["k8s", "kubernetes", "kafka", "terraform", "cloud"]) else "general"
                        cursor.execute("""
                            INSERT OR REPLACE INTO qa_bank (key, category, question_pattern, answer_text, confidence)
                            VALUES (?, ?, ?, ?, 1.0)
                        """, (key, cat, key.replace("_", " "), str(ans)))
                    conn.commit()
        except Exception as e:
            logger.debug(f"QA sync notice: {e}")

    # ─────────────────────────────────────────────────────────────────
    # APPLICATION OPERATIONS
    # ─────────────────────────────────────────────────────────────────

    def is_applied(self, platform: str, job_id: str) -> bool:
        """Checks if a job has already been applied to."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM applications WHERE platform = ? AND job_id = ? AND status = 'applied'",
                (platform.lower(), str(job_id)),
            )
            return cursor.fetchone() is not None

    def record_application(
        self,
        platform: str,
        job_id: str,
        title: str,
        company: str,
        location: str = "",
        url: str = "",
        status: str = "applied",
        resume_used: str = "DevOps_SRE_Master.pdf",
        notes: str = "",
        screenshot_path: str = "",
    ) -> bool:
        """Records a completed job application with proof screenshot."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO applications (platform, job_id, title, company, location, url, status, resume_used, notes, screenshot_path, applied_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(platform, job_id) DO UPDATE SET
                        status = excluded.status,
                        resume_used = excluded.resume_used,
                        notes = excluded.notes,
                        screenshot_path = excluded.screenshot_path,
                        applied_at = excluded.applied_at
                    """,
                    (
                        platform.lower(),
                        str(job_id),
                        title,
                        company,
                        location,
                        url,
                        status,
                        resume_used,
                        notes,
                        screenshot_path,
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
                self.log_audit("APPLICATION_SUBMITTED", f"Applied to {title} at {company} via {platform}")
                return True
        except Exception as e:
            logger.error(f"Failed to record application for job {job_id}: {e}")
            return False

    def get_today_applied_count(self, platform: Optional[str] = None) -> int:
        """Returns application count for today."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            today_str = datetime.now().strftime("%Y-%m-%d")
            if platform:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM applications 
                    WHERE platform = ? AND status = 'applied' AND date(applied_at) = date(?)
                    """,
                    (platform.lower(), today_str),
                )
            else:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM applications 
                    WHERE status = 'applied' AND date(applied_at) = date(?)
                    """,
                    (today_str,),
                )
            return cursor.fetchone()[0]

    def get_recent_applications(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Returns recent application records with proof paths."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, platform, job_id, title, company, location, status, resume_used, applied_at, url, screenshot_path
                FROM applications 
                ORDER BY applied_at DESC 
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(r) for r in cursor.fetchall()]

    # ─────────────────────────────────────────────────────────────────
    # JOBS RADAR OPERATIONS
    # ─────────────────────────────────────────────────────────────────

    def save_discovered_job(
        self,
        job_id: str,
        platform: str,
        title: str,
        company: str,
        url: str,
        location: str = "",
        match_score: float = 95.0,
        min_salary: Optional[float] = None,
        max_salary: Optional[float] = None,
        experience_required: Optional[float] = None,
    ) -> bool:
        """Saves a discovered job listing."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO jobs (job_id, platform, title, company, location, url, match_score, min_salary, max_salary, experience_required, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'discovered')
                    ON CONFLICT(platform, job_id) DO UPDATE SET
                        match_score = excluded.match_score,
                        url = excluded.url
                    """,
                    (
                        str(job_id),
                        platform.lower(),
                        title,
                        company,
                        location,
                        url,
                        match_score,
                        min_salary,
                        max_salary,
                        experience_required,
                    ),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to save job {job_id}: {e}")
            return False

    def get_matched_jobs(self, min_match: float = 85.0, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns queued/discovered jobs exceeding the match threshold."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM jobs 
                WHERE match_score >= ? AND status = 'discovered'
                ORDER BY match_score DESC, discovered_at DESC
                LIMIT ?
                """,
                (min_match, limit),
            )
            return [dict(r) for r in cursor.fetchall()]

    # ─────────────────────────────────────────────────────────────────
    # KNOWLEDGE BANK (Q&A) OPERATIONS
    # ─────────────────────────────────────────────────────────────────

    def get_qa_answer(self, query: str) -> Optional[str]:
        """Resolves a screening question from the knowledge bank."""
        clean_q = query.lower().strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT answer_text FROM qa_bank WHERE ? LIKE '%' || key || '%' OR key LIKE '%' || ? || '%'", (clean_q, clean_q))
            row = cursor.fetchone()
            if row:
                return row["answer_text"]
        return None

    def save_qa_item(self, key: str, answer_text: str, category: str = "general", question_pattern: str = "") -> bool:
        """Stores a verified answer in the database and updates JSON backup."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO qa_bank (key, category, question_pattern, answer_text, confidence, updated_at)
                    VALUES (?, ?, ?, ?, 1.0, CURRENT_TIMESTAMP)
                """, (key.lower().strip(), category, question_pattern or key, answer_text))
                conn.commit()

            # Also sync to JSON file
            try:
                current_data = {}
                if self.qa_path.exists():
                    with open(self.qa_path, "r", encoding="utf-8") as f:
                        current_data = json.load(f)
                current_data[key] = answer_text
                with open(self.qa_path, "w", encoding="utf-8") as f:
                    json.dump(current_data, f, indent=2)
            except Exception:
                pass

            return True
        except Exception as e:
            logger.error(f"Failed to save QA item {key}: {e}")
            return False

    def get_all_qa_items(self) -> List[Dict[str, Any]]:
        """Returns all knowledge bank entries."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM qa_bank ORDER BY category, key")
            return [dict(r) for r in cursor.fetchall()]

    # ─────────────────────────────────────────────────────────────────
    # AUDIT LOGGING & STATS
    # ─────────────────────────────────────────────────────────────────

    def log_audit(self, event_type: str, message: str, details: str = ""):
        """Logs an event to the audit table."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO audit_logs (event_type, message, details)
                    VALUES (?, ?, ?)
                """, (event_type, message, details))
                conn.commit()
        except Exception:
            pass

    def get_summary_stats(self) -> Dict[str, Any]:
        """Returns summary statistics across platforms (backwards compatible)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT platform, status, COUNT(*) as count 
                FROM applications 
                GROUP BY platform, status
            """)
            rows = cursor.fetchall()
            stats: Dict[str, Dict[str, int]] = {}
            for r in rows:
                p = r["platform"]
                if p not in stats:
                    stats[p] = {}
                stats[p][r["status"]] = r["count"]
            return stats

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Returns aggregated production metrics for the UI."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            today_str = datetime.now().strftime("%Y-%m-%d")

            # Today apps
            cursor.execute("SELECT COUNT(*) FROM applications WHERE status = 'applied' AND date(applied_at) = date(?)", (today_str,))
            today_count = cursor.fetchone()[0]

            # Total apps
            cursor.execute("SELECT COUNT(*) FROM applications WHERE status = 'applied'")
            total_count = cursor.fetchone()[0]

            # Platform breakdown
            cursor.execute("SELECT platform, COUNT(*) as count FROM applications GROUP BY platform")
            by_platform = {r["platform"]: r["count"] for r in cursor.fetchall()}

            # Discovered jobs count
            cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'discovered'")
            discovered_count = cursor.fetchone()[0]

            return {
                "today_applied": today_count,
                "total_applied": total_count,
                "discovered_jobs": discovered_count,
                "by_platform": by_platform,
            }
