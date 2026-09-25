import unittest
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from src.config import load_profile
from src.utils.resume_manager import ResumeManager

class TestResumeManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.profile = load_profile()
        self.profile.resume.directory = str(Path(self.tmpdir.name) / "resumes")
        self.manager = ResumeManager(self.profile)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_find_and_freshen_resume(self):
        # 1. Create a dummy master resume
        master_file = self.manager.resumes_dir / "Rajesh_Saindane_DevOps_SRE_Resume_old.pdf"
        master_file.write_text("dummy resume content")

        found = self.manager.find_master_resume()
        self.assertIsNotNone(found)
        self.assertEqual(found.name, master_file.name)

        # 2. Test date stamping with offset 1 (yesterday)
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%d%m%Y")
        freshened = self.manager.get_freshened_resume(date_offset_days=1)
        self.assertIsNotNone(freshened)
        self.assertTrue(freshened.exists())
        self.assertIn(yesterday_str, freshened.name)
        self.assertTrue(freshened.name.endswith(".pdf"))

    def test_monthly_version_auto_pick(self):
        # Create older resume
        old_file = self.manager.resumes_dir / "Resume_January.pdf"
        old_file.write_text("january")

        # Create newer resume
        new_file = self.manager.resumes_dir / "Resume_February.pdf"
        new_file.write_text("february")

        # Ensure new_file has later mtime
        import time
        now = time.time()
        import os
        os.utime(old_file, (now - 1000, now - 1000))
        os.utime(new_file, (now, now))

        latest = self.manager.find_master_resume()
        self.assertEqual(latest.name, "Resume_February.pdf")

if __name__ == "__main__":
    unittest.main()
