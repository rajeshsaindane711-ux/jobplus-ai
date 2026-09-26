"""
Unit Tests for Autonomous Form-Filler with Safety Circuit Breaker — JobPlus AI
"""

import unittest
import os
import tempfile
import json
from src.platforms.form_filler import AutonomousFormFiller, CircuitBreakerException
from src.database import DatabaseTracker
from src.config import load_profile

class TestAutonomousFormFiller(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_jobplus.db")
        self.tracker = DatabaseTracker(db_path=self.db_path)
        self.profile = load_profile("config/profile.yaml")
        self.filler = AutonomousFormFiller(
            page=None,
            profile=self.profile,
            tracker=self.tracker,
            data_dir=self.test_dir
        )

    def test_ats_detection(self):
        self.assertEqual(self.filler.detect_ats_type("https://boards.greenhouse.io/stripe/jobs/123"), "greenhouse")
        self.assertEqual(self.filler.detect_ats_type("https://jobs.lever.co/netflix/456"), "lever")
        self.assertEqual(self.filler.detect_ats_type("https://jobs.ashbyhq.com/linear/789"), "ashby")
        self.assertEqual(self.filler.detect_ats_type("https://target.myworkdayjobs.com/careers/101"), "workday")
        self.assertEqual(self.filler.detect_ats_type("https://www.linkedin.com/jobs/view/999"), "linkedin")
        self.assertEqual(self.filler.detect_ats_type("https://www.naukri.com/job-listings-1234"), "naukri")

    def test_screening_question_resolution(self):
        # Notice Period
        ans, conf = self.filler.resolve_screening_question("What is your official notice period in days?")
        self.assertTrue(conf)
        self.assertIn("30", ans)

        # Total Experience
        ans, conf = self.filler.resolve_screening_question("How many years of total experience do you have?", input_type="number")
        self.assertTrue(conf)
        self.assertIn("5", ans)

        # Work Authorization
        ans, conf = self.filler.resolve_screening_question("Are you legally authorized to work in India?")
        self.assertTrue(conf)
        self.assertEqual(ans, "Yes")

        # Visa Sponsorship
        ans, conf = self.filler.resolve_screening_question("Will you now or in the future require visa sponsorship?")
        self.assertTrue(conf)
        self.assertIn("No", ans)

        # Tech Skills
        ans, conf = self.filler.resolve_screening_question("Years of experience with Kubernetes and EKS?")
        self.assertTrue(conf)
        self.assertIn("5", ans)

    def test_circuit_breaker_on_unknown_question(self):
        # An unknown required question that is not in profile or QA memory
        unknown_q = "What is your Top Secret SC Clearance number and security clearance status?"
        ans, conf = self.filler.resolve_screening_question(unknown_q)
        self.assertFalse(conf)
        self.assertIsNone(ans)

        # Trigger circuit breaker
        cb_res = self.filler.trigger_circuit_breaker(
            question=unknown_q,
            platform="greenhouse",
            company="DefenseCorp",
            job_url="https://boards.greenhouse.io/defensecorp/jobs/999"
        )
        self.assertEqual(cb_res["status"], "circuit_breaker_triggered")
        self.assertEqual(cb_res["company"], "DefenseCorp")
        self.assertIn("review_id", cb_res)

        # Verify application status in database is flagged
        recent = self.tracker.get_recent_applications(limit=5)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["status"], "flagged_verification")
        self.assertEqual(recent[0]["company"], "DefenseCorp")

    def test_resolve_review_item_and_qa_memory(self):
        # 1. Trigger circuit breaker for custom question
        custom_q = "Do you have hands-on experience configuring Kafka Schema Registry?"
        cb_res = self.filler.trigger_circuit_breaker(
            question=custom_q,
            platform="lever",
            company="FintechAI",
            job_url="https://jobs.lever.co/fintech/1"
        )
        review_id = cb_res["review_id"]

        # 2. Resolve via user answer
        resolved = self.filler.resolve_review_item(review_id, "Yes, 3+ years managing Avro schemas and Confluent Schema Registry.")
        self.assertTrue(resolved)

        # 3. Verify next time this question is asked, it resolves immediately with 100% confidence from QA memory
        ans, conf = self.filler.resolve_screening_question(custom_q)
        self.assertTrue(conf)
        self.assertEqual(ans, "Yes, 3+ years managing Avro schemas and Confluent Schema Registry.")

    def test_batch_processing_dedup(self):
        jobs = [
            {"company": "Company A", "url": "https://boards.greenhouse.io/companya/jobs/1", "title": "DevOps Engineer"},
            {"company": "Company B", "url": "https://jobs.lever.co/companyb/jobs/2", "title": "SRE Lead"}
        ]
        # Pre-apply to Company A
        self.tracker.record_application("greenhouse", jobs[0]["url"], "DevOps", "Company A", 95.0, "applied")

        res = self.filler.process_batch(jobs, dry_run=True)
        self.assertEqual(res["total"], 2)
        self.assertEqual(res["skipped"], 1) # Company A skipped due to deduplication
        self.assertEqual(res["applied"], 1) # Company B simulated dry-run applied

if __name__ == "__main__":
    unittest.main()
