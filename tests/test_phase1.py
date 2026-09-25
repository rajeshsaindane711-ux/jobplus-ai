import unittest
import tempfile
from pathlib import Path
from src.config import load_profile, load_search_config
from src.database import DatabaseTracker

class TestPhase1(unittest.TestCase):
    def test_load_configs(self):
        profile = load_profile()
        self.assertIsNotNone(profile.candidate.first_name)
        self.assertIsNotNone(profile.experience.total_years)

        search_config = load_search_config()
        self.assertGreater(len(search_config.search.keywords), 0)
        self.assertTrue(search_config.platforms["naukri"].enabled)
        self.assertTrue(search_config.platforms["linkedin"].enabled)

    def test_database_tracker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_db = Path(tmpdir) / "test_tracker.db"
            tracker = DatabaseTracker(db_path=test_db)

            # Test initial state
            self.assertFalse(tracker.is_applied("naukri", "job_123"))

            # Test recording application
            success = tracker.record_application(
                platform="naukri",
                job_id="job_123",
                title="Python Developer",
                company="Tech Corp",
                location="Bengaluru",
                url="https://naukri.com/job/123",
                status="applied",
            )
            self.assertTrue(success)
            self.assertTrue(tracker.is_applied("naukri", "job_123"))

            # Test daily count
            self.assertEqual(tracker.get_today_applied_count("naukri"), 1)
            self.assertEqual(tracker.get_today_applied_count("linkedin"), 0)

            # Test deduplication / update
            updated = tracker.record_application(
                platform="naukri",
                job_id="job_123",
                title="Python Developer",
                company="Tech Corp",
                status="applied",
                notes="Already submitted",
            )
            self.assertTrue(updated)
            self.assertEqual(tracker.get_today_applied_count("naukri"), 1)

            # Test stats
            stats = tracker.get_summary_stats()
            self.assertIn("naukri", stats)
            self.assertEqual(stats["naukri"]["applied"], 1)

if __name__ == "__main__":
    unittest.main()
