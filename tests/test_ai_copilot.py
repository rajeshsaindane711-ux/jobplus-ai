"""
Unit Tests for JobPlus AI Career Copilot & Free Gemini Engine
"""

import unittest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.ai_copilot import AICareerCopilot

class TestAICareerCopilot(unittest.TestCase):
    def setUp(self):
        self.copilot = AICareerCopilot()

    def test_ats_match_analysis(self):
        """Verifies ATS match analysis returns score >= 70, matched & missing keywords."""
        resume = """
        Rajesh Saindane - DevOps & SRE Engineer
        5.0 Years Experience in Kubernetes, EKS, Terraform, Kafka, AWS, CI/CD, ArgoCD, Prometheus, Grafana.
        """
        job_desc = """
        Looking for a Senior SRE with strong hands-on expertise in Kubernetes, Terraform, AWS, Docker, Datadog.
        Must have 4+ years experience in cloud infrastructure.
        """
        result = self.copilot.analyze_ats_match(resume, job_desc)
        self.assertIn("score", result)
        self.assertGreaterEqual(result["score"], 80.0)
        self.assertIn("matched_keywords", result)
        self.assertIn("Kubernetes", result["matched_keywords"])
        self.assertIn("Terraform", result["matched_keywords"])
        self.assertIn("tailoring_suggestions", result)

    def test_human_cover_letter_generation(self):
        """Verifies generated cover letter is non-robotic, mentions company, role, and achievements."""
        letter = self.copilot.generate_cover_letter(
            candidate_name="Rajesh Saindane",
            position="Lead DevOps Engineer",
            company="Zeta Tech",
            experience_years=5.0,
            notice_period="30 Days"
        )
        self.assertIn("Zeta Tech", letter)
        self.assertIn("Lead DevOps Engineer", letter)
        self.assertIn("Rajesh Saindane", letter)
        self.assertIn("30 Days", letter)
        self.assertIn("Kubernetes", letter)
        # Verify no robotic AI cliches
        self.assertNotIn("tapestry", letter.lower())
        self.assertNotIn("delve", letter.lower())

    def test_recruiter_outreach_sequence(self):
        """Verifies 3-touch sequence structure."""
        outreach = self.copilot.generate_outreach_sequence(
            candidate_name="Rajesh Saindane",
            recruiter_name="Ananya",
            company="PhonePe",
            position="Senior SRE"
        )
        self.assertEqual(len(outreach["sequence"]), 3)
        self.assertIn("Touch 1", outreach["sequence"][0]["stage"])
        self.assertIn("Touch 2", outreach["sequence"][1]["stage"])
        self.assertIn("Touch 3", outreach["sequence"][2]["stage"])
        self.assertIn("PhonePe", outreach["sequence"][0]["subject"])

    def test_bullet_optimization(self):
        """Verifies Google X-Y-Z formula rewriting."""
        optimized = self.copilot.optimize_resume_bullet(
            "I worked on setting up kafka and docker",
            target_tech="kafka"
        )
        self.assertIn("10M+ Daily Events", optimized["impact_metric"])
        self.assertIn("Apache Kafka", optimized["added_keywords"])

if __name__ == "__main__":
    unittest.main()
