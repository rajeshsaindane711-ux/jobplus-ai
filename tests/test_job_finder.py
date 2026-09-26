"""
Unit Tests for JobPlus AI Job Finder & Multi-Platform Filter Engine
"""

import unittest
import tempfile
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.platforms.job_finder import JobFinderEngine
from src.database import DatabaseTracker
from src.utils.ai_copilot import AICareerCopilot

class TestJobFinderEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_jobs.db"
        self.tracker = DatabaseTracker(db_path=self.db_path)
        self.engine = JobFinderEngine(
            tracker=self.tracker,
            min_salary_lpa=12.0,
            max_experience_years=8.0,
            min_match_score=85.0
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_company_blacklist_filter(self):
        """Verifies blacklisted companies (e.g. Wipro/TCS) are filtered out."""
        job = {
            "title": "Senior DevOps Engineer",
            "company": "Wipro Technologies",
            "min_salary": 18.0,
            "experience_required": 5.0,
            "posted_days_ago": 2
        }
        res = self.engine.evaluate_job_eligibility(job)
        self.assertFalse(res["eligible"])
        self.assertIn("blacklisted", res["reason"].lower())

    def test_keyword_blacklist_filter(self):
        """Verifies low-skill/support keywords (e.g. Helpdesk) are filtered out."""
        job = {
            "title": "Junior L1 Helpdesk & Desktop Support",
            "company": "FastTech Inc",
            "min_salary": 14.0,
            "experience_required": 3.0,
            "posted_days_ago": 2
        }
        res = self.engine.evaluate_job_eligibility(job)
        self.assertFalse(res["eligible"])
        self.assertIn("excluded keyword", res["reason"].lower())

    def test_salary_floor_filter(self):
        """Verifies salaries below 12 LPA floor are discarded."""
        job = {
            "title": "DevOps Associate",
            "company": "StartupX",
            "min_salary": 7.5,
            "experience_required": 4.0,
            "posted_days_ago": 1
        }
        res = self.engine.evaluate_job_eligibility(job)
        self.assertFalse(res["eligible"])
        self.assertIn("minimum floor", res["reason"].lower())

    def test_ghost_job_filter(self):
        """Verifies listings older than 30 days are flagged as ghost jobs."""
        job = {
            "title": "Senior SRE Lead",
            "company": "OldCorp",
            "min_salary": 25.0,
            "experience_required": 5.0,
            "posted_days_ago": 45
        }
        res = self.engine.evaluate_job_eligibility(job)
        self.assertFalse(res["eligible"])
        self.assertIn("ghost job", res["reason"].lower())

    def test_full_scan_and_database_persistence(self):
        """Verifies multi-platform scan saves only qualified jobs into SQLite."""
        resume = "Rajesh Saindane: 5 Years experience in Kubernetes EKS, Terraform AWS, Apache Kafka event streaming, ArgoCD, Prometheus, Grafana."
        scan_results = self.engine.scan_and_sync_all_platforms(candidate_resume=resume)

        self.assertGreater(scan_results["total_discovered"], 0)
        self.assertGreater(scan_results["total_qualified"], 0)
        self.assertEqual(scan_results["total_skipped"], 1)  # Wipro helpdesk skipped

        # Verify database has the qualified jobs
        db_jobs = self.tracker.get_matched_jobs(min_match=85.0)
        self.assertEqual(len(db_jobs), scan_results["total_qualified"])
        companies = [j["company"] for j in db_jobs]
        self.assertIn("PhonePe", companies)
        self.assertIn("Zeta Tech", companies)
        self.assertNotIn("Wipro", companies)

if __name__ == "__main__":
    unittest.main()
