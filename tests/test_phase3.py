import unittest
import tempfile
from pathlib import Path
from src.config import load_profile, load_search_config
from src.database import DatabaseTracker
from src.platforms.email_outreach import EmailOutreachEngine
from src.platforms.naukri import NaukriAutomator
from src.platforms.linkedin import LinkedInAutomator

class TestPhase3(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile()
        self.search_cfg = load_search_config()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test_jobplus.db"
        self.tracker = DatabaseTracker(self.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_email_outreach_extraction(self):
        engine = EmailOutreachEngine(self.profile, self.tracker)
        sample_post = """
        We are looking for a Python Developer. 
        Interested candidates please share your resume to hiring@techventures.io or careers@innovate.co.in.
        Please do not email help@linkedin.com.
        """
        emails = engine.extract_emails(sample_post)
        self.assertIn("hiring@techventures.io", emails)
        self.assertIn("careers@innovate.co.in", emails)
        self.assertNotIn("help@linkedin.com", emails)

    def test_email_content_generation(self):
        engine = EmailOutreachEngine(self.profile, self.tracker)

        # 1. With JD
        content_with_jd = engine.generate_email_content(
            job_title="Backend Engineer",
            company="TechCorp",
            job_description="Immediate joiner required with Python & AWS expertise."
        )
        self.assertIn("Application: Backend Engineer", content_with_jd["subject"])
        self.assertIn("TechCorp", content_with_jd["body"])
        self.assertIn(self.profile.experience.current_job_title, content_with_jd["body"])

        # 2. Without JD
        content_no_jd = engine.generate_email_content(
            job_title="Full Stack Developer",
            company="StartupX",
            job_description=""
        )
        self.assertIn("Application: Full Stack Developer", content_no_jd["subject"])
        self.assertIn("StartupX", content_no_jd["body"])

    def test_email_outreach_deduplication(self):
        engine = EmailOutreachEngine(self.profile, self.tracker)
        to_email = "lead.recruiter@company.com"

        self.assertFalse(engine.is_emailed(to_email))
        engine.record_email_sent(to_email, "Python Lead", "Company", "Subject", "sent")
        self.assertTrue(engine.is_emailed(to_email))

    def test_naukri_search_url_builder(self):
        automator = NaukriAutomator(
            page=None,
            profile=self.profile,
            platform_config=self.search_cfg.platforms["naukri"],
            safety_config=self.search_cfg.safety,
            tracker=self.tracker,
        )
        url = automator.build_search_url("Python Developer", "Bengaluru")
        self.assertTrue(url.startswith("https://www.naukri.com/python-developer-jobs-in-bengaluru"))
        self.assertIn("experience=", url)

    def test_linkedin_search_url_builder(self):
        automator = LinkedInAutomator(
            page=None,
            profile=self.profile,
            platform_config=self.search_cfg.platforms["linkedin"],
            safety_config=self.search_cfg.safety,
            tracker=self.tracker,
        )
        url = automator.build_search_url("Backend Engineer", "Remote")
        self.assertTrue(url.startswith("https://www.linkedin.com/jobs/search/"))
        self.assertIn("f_AL=true", url) # Easy Apply filter
        self.assertIn("Backend+Engineer", url)

if __name__ == "__main__":
    unittest.main()
