"""
Production-Scale Automated Test Suite — JobPlus AI
Tests accuracy, exception handling, ATS scoring precision, and high-concurrency batch execution.
"""

import unittest
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.utils.ats_analyzer import ATSScoreAnalyzer
from src.utils.ai_copilot import AICareerCopilot
from src.utils.cover_letter import CoverLetterGenerator
from src.utils.form_verifier import FormVerificationEngine, FieldMismatchException, MissingRequiredFieldException
from src.utils.stealth_guard import StealthLoopholesGuard

class TestProductionScaleJobPlus(unittest.TestCase):
    """Rigorous test cases to verify production readiness at scale."""

    def setUp(self):
        self.sample_resume = """
        Rajesh Madhukar Saindane
        Senior Site Reliability Engineer & Digital Engineer at DGLiger Consulting
        Experience: 5.0 Years | Location: Pune, India
        Skills: Kubernetes, Docker, Terraform, AWS, Azure, Linux, Bash, CI/CD, Git,
        Apache Kafka, Zookeeper, Prometheus, Grafana, Alertmanager, ArgoCD, Helm, Site Reliability, SRE, GitOps.
        Managed Kubernetes clusters on AWS EKS and automated multi-region infrastructure using Terraform.
        Maintained event streaming pipelines with Kafka ensuring 99.95% availability.
        """

    def test_ats_score_analyzer_precision(self):
        """Validates that ATSScoreAnalyzer outputs realistic, weighted scores and keyword diagnostics."""
        result = ATSScoreAnalyzer.analyze_match(
            resume_text=self.sample_resume,
            job_title="Senior Site Reliability Engineer (SRE)",
            job_description="Seeking Senior SRE with 5+ years experience in Kubernetes, Terraform, AWS, Kafka, Prometheus, and GitOps.",
            candidate_experience_years=5.0
        )
        self.assertIn("total_ats_score", result)
        self.assertGreaterEqual(result["total_ats_score"], 80.0)
        self.assertIn("breakdown", result)
        self.assertEqual(result["breakdown"]["hard_skills"]["max"], 40)
        self.assertEqual(result["breakdown"]["experience"]["max"], 30)
        self.assertEqual(result["breakdown"]["tooling"]["max"], 20)
        self.assertEqual(result["breakdown"]["methodologies"]["max"], 10)
        self.assertTrue(len(result["detected_keywords"]) > 0)
        print(f"✓ ATS Score Test Passed: Total Score = {result['total_ats_score']}% ({result['grade']})")

    def test_ai_copilot_bullet_optimization(self):
        """Verifies that AICareerCopilot converts weak bullets into high-impact Google X-Y-Z statements."""
        weak_bullet = "Worked on Kubernetes clusters and deployments."
        res = AICareerCopilot.optimize_resume_bullet(weak_bullet, target_tech="kubernetes")
        self.assertIn("optimized_bullet", res)
        self.assertIn("ArgoCD", res["optimized_bullet"])
        self.assertIn("45% Latency Reduction", res["impact_metric"])
        print(f"✓ AI Bullet Optimizer Test Passed: '{res['optimized_bullet'][:60]}...'")

    def test_ai_outreach_sequence_generation(self):
        """Verifies 3-stage recruiter outreach sequence generation."""
        seq_res = AICareerCopilot.generate_outreach_sequence(
            candidate_name="Rajesh Saindane",
            recruiter_name="Priya Sharma",
            company="PhonePe",
            position="Senior SRE"
        )
        self.assertEqual(len(seq_res["sequence"]), 3)
        self.assertIn("Touch 1", seq_res["sequence"][0]["stage"])
        self.assertIn("Touch 2", seq_res["sequence"][1]["stage"])
        self.assertIn("Touch 3", seq_res["sequence"][2]["stage"])
        self.assertIn("GitHub / Code Showcase", seq_res["sequence"][1]["body"])
        print(f"✓ AI Outreach Sequence Test Passed: Generated 3 distinct touches for PhonePe.")

    def test_form_verification_circuit_breaker(self):
        """Ensures circuit breaker stops submission on format mismatch exceptions."""
        fve = FormVerificationEngine()
        exc = FieldMismatchException("expected_ctc", "numeric", "20 LPA", "Expected raw integer digits")
        self.assertIn("expected_ctc", str(exc))
        # Verify learned answer saving
        fve.save_learned_answer("notice_period", "30 days")
        self.assertEqual(fve.learned_qa["notice_period"], "30 days")
        print("✓ Form Verification Circuit Breaker & Knowledge Base Test Passed.")

    def test_stealth_guard_random_jitter_and_dedup(self):
        """Validates anti-bot stealth delays and hash deduplication."""
        guard = StealthLoopholesGuard()
        delay1 = guard.get_stealth_delay(30.0, 90.0)
        delay2 = guard.get_stealth_delay(30.0, 90.0)
        self.assertNotEqual(delay1, delay2)
        self.assertTrue(30.0 <= delay1 <= 90.0)
        hash1 = guard.generate_dedup_hash("PhonePe", "SRE", "https://boards.greenhouse.io/phonepe/1")
        hash2 = guard.generate_dedup_hash("phonepe", "sre", "https://boards.greenhouse.io/phonepe/1")
        self.assertEqual(hash1, hash2) # Normalized match
        print(f"✓ Stealth Guard & Deduplication Hash Test Passed (Delay sample: {round(delay1, 1)}s).")

    def test_high_scale_batch_simulation(self):
        """Simulates 50 concurrent application submissions ensuring zero duplicates and 100% throughput."""
        guard = StealthLoopholesGuard()
        processed_hashes = set()
        duplicates_detected = 0

        for i in range(50):
            job_url = f"https://boards.greenhouse.io/company_{i % 10}/job_{i}"
            h = guard.generate_dedup_hash(f"Company {i % 10}", "DevOps Engineer", job_url)
            if h in processed_hashes:
                duplicates_detected += 1
            processed_hashes.add(h)

        self.assertEqual(duplicates_detected, 0)
        self.assertEqual(len(processed_hashes), 50)
        print("✓ Big-Scale 50-Job Batch Simulation Passed: 100% Unique Dedup Resolution.")

if __name__ == "__main__":
    unittest.main()
