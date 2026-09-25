import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.utils.logger import logger

from contextlib import contextmanager

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobpilot.db"

class DatabaseTracker:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Creates tables if they don't exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT,
                    url TEXT,
                    status TEXT NOT NULL,
                    notes TEXT,
                    screenshot_path TEXT,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(platform, job_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_platform_job_id 
                ON applications(platform, job_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_applied_date 
                ON applications(platform, applied_at)
            """)
            conn.commit()

    def is_applied(self, platform: str, job_id: str) -> bool:
        """Checks if a job has already been processed or applied to."""
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
        notes: str = "",
        screenshot_path: str = "",
    ) -> bool:
        """Records a job application attempt."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO applications (platform, job_id, title, company, location, url, status, notes, screenshot_path, applied_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(platform, job_id) DO UPDATE SET
                        status = excluded.status,
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
                        notes,
                        screenshot_path,
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to record application for job {job_id}: {e}")
            return False

    def get_today_applied_count(self, platform: str) -> int:
        """Returns the number of jobs applied to today on a given platform."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            today_str = datetime.now().strftime("%Y-%m-%d")
            cursor.execute(
                """
                SELECT COUNT(*) FROM applications 
                WHERE platform = ? AND status = 'applied' AND date(applied_at) = date(?)
                """,
                (platform.lower(), today_str),
            )
            return cursor.fetchone()[0]

    def get_summary_stats(self) -> Dict[str, Any]:
        """Returns summary statistics across platforms."""
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

    def get_recent_applications(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns the most recent application records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT platform, job_id, title, company, location, status, applied_at, url
                FROM applications 
                ORDER BY applied_at DESC 
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(r) for r in cursor.fetchall()]
