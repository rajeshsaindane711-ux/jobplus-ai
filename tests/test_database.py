"""
Unit Tests for JobPlus AI Production Database Engine
"""

import unittest
import tempfile
import os
import sys
import json
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import DatabaseTracker

class TestProductionDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_jobplus.db"
        self.qa_path = Path(self.temp_dir.name) / "test_qa.json"
        
        # Create initial test QA json
        with open(self.qa_path, "w", encoding="utf-8") as f:
            json.dump({
                "notice_period": "30 days",
                "current_ctc": "10 LPA",
                "expected_ctc": "20 LPA",
                "kubernetes_experience": "4+ Years on EKS/GKE"
            }, f)

        self.db = DatabaseTracker(db_path=self.db_path, qa_path=self.qa_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_initialization_and_sync(self):
        """Verifies tables are created and QA data auto-synced from JSON."""
        qa_items = self.db.get_all_qa_items()
        self.assertGreaterEqual(len(qa_items), 4)
        
        answer = self.db.get_qa_answer("What is your notice_period?")
        self.assertEqual(answer, "30 days")

    def test_record_application_and_deduplication(self):
        """Verifies recording application and unique constraint enforcement."""
        success = self.db.record_application(
            platform="linkedin",
            job_id="phonepe-sre-001",
            title="Senior SRE",
            company="PhonePe",
            location="Pune",
            url="https://phonepe.com/careers/sre-001",
            status="applied",
            resume_used="DevOps_SRE_Master.pdf",
            notes="Submitted via ATS"
        )
        self.assertTrue(success)
        self.assertTrue(self.db.is_applied("linkedin", "phonepe-sre-001"))
        self.assertFalse(self.db.is_applied("linkedin", "non-existent-job"))

        # Check today count
        today_count = self.db.get_today_applied_count("linkedin")
        self.assertEqual(today_count, 1)

    def test_save_and_retrieve_discovered_jobs(self):
        """Verifies jobs radar saving and match threshold filtering."""
        self.db.save_discovered_job(
            job_id="zeta-01",
            platform="direct_ats",
            title="Cloud Platform Engineer",
            company="Zeta Tech",
            url="https://boards.greenhouse.io/zeta/01",
            location="Bengaluru",
            match_score=96.4
        )
        self.db.save_discovered_job(
            job_id="low-match-02",
            platform="naukri",
            title="Junior Helpdesk",
            company="OtherCorp",
            url="https://naukri.com/job/02",
            match_score=65.0
        )

        matched = self.db.get_matched_jobs(min_match=90.0)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["job_id"], "zeta-01")
        self.assertEqual(matched[0]["match_score"], 96.4)

    def test_save_new_qa_item_and_file_sync(self):
        """Verifies saving new screening question updates DB and JSON file."""
        saved = self.db.save_qa_item(
            key="relocation_preference",
            answer_text="Open to relocate to Pune or Bengaluru",
            category="general"
        )
        self.assertTrue(saved)
        
        retrieved = self.db.get_qa_answer("relocation_preference")
        self.assertEqual(retrieved, "Open to relocate to Pune or Bengaluru")

        # Verify JSON file has it
        with open(self.qa_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("relocation_preference", data)

    def test_dashboard_summary(self):
        """Verifies aggregated metrics calculation."""
        self.db.record_application("naukri", "job-1", "DevOps Engineer", "Company A")
        self.db.record_application("linkedin", "job-2", "SRE Lead", "Company B")
        self.db.save_discovered_job("job-3", "direct_ats", "Platform Eng", "Company C", "http://c.com")

        summary = self.db.get_dashboard_summary()
        self.assertEqual(summary["today_applied"], 2)
        self.assertEqual(summary["total_applied"], 2)
        self.assertEqual(summary["discovered_jobs"], 1)
        self.assertEqual(summary["by_platform"]["naukri"], 1)
        self.assertEqual(summary["by_platform"]["linkedin"], 1)

if __name__ == "__main__":
    unittest.main()
