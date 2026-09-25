import unittest
import tempfile
from pathlib import Path
from src.browser import BrowserManager

class TestPhase2(unittest.TestCase):
    def test_browser_initialization(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_dir = Path(tmpdir) / "test_profile"
            manager = BrowserManager(headless=True, profile_dir=profile_dir)

            try:
                page = manager.new_page()
                self.assertIsNotNone(page)

                # Test navigation to a simple fast page
                page.goto("data:text/html,<html><head><title>JobPilot Test</title></head><body><h1>JobPilot</h1></body></html>")
                title = page.title()
                self.assertEqual(title, "JobPilot Test")

                # Test stealth presence (navigator.webdriver should be undefined or false)
                is_webdriver = page.evaluate("navigator.webdriver")
                self.assertFalse(is_webdriver)

            finally:
                manager.close()

            # Profile directory should have been created and populated
            self.assertTrue(profile_dir.exists())

if __name__ == "__main__":
    unittest.main()
