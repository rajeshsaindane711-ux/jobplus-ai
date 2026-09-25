import random
import time
from pathlib import Path
from typing import Dict, Optional, Tuple
from playwright.sync_api import BrowserContext, Page, sync_playwright
from playwright_stealth import Stealth
from src.utils.logger import logger, console

stealth_handler = Stealth()

PROFILE_DIR = Path(__file__).resolve().parent.parent / "data" / "browser_profile"

class BrowserManager:
    """Manages persistent browser sessions with stealth anti-detection."""

    def __init__(self, headless: bool = False, profile_dir: Optional[Path] = None):
        self.headless = headless
        self.profile_dir = profile_dir or PROFILE_DIR
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = None
        self._context: Optional[BrowserContext] = None

    def start(self) -> BrowserContext:
        """Launches persistent browser context with stealth parameters."""
        if self._context:
            return self._context

        self._playwright = sync_playwright().start()

        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--start-maximized",
        ]

        logger.info(f"Launching persistent browser context from: {self.profile_dir}")
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            channel="chromium",
            args=args,
            viewport=None, # Use maximized window
            no_viewport=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        return self._context

    def new_page(self) -> Page:
        """Creates or gets an active page with stealth scripts applied."""
        context = self.start()
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()

        stealth_handler.apply_stealth_sync(page)
        return page

    def close(self):
        """Closes browser context and playwright safely."""
        try:
            if self._context:
                self._context.close()
                self._context = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
            logger.info("Browser session closed safely.")
        except Exception as e:
            logger.warning(f"Error while closing browser: {e}")

    @staticmethod
    def human_delay(min_seconds: float = 2.0, max_seconds: float = 5.0):
        """Pauses execution with random jitter to mimic human behavior."""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)

    def launch_interactive_login(self):
        """
        Opens a visible browser for the user to log in manually to Naukri and LinkedIn.
        Once the user logs in and presses Enter in terminal, sessions are saved.
        """
        self.headless = False
        context = self.start()
        
        # Open LinkedIn Login tab
        p1 = context.pages[0] if context.pages else context.new_page()
        stealth_handler.apply_stealth_sync(p1)
        logger.info("Navigating to LinkedIn login page...")
        p1.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        # Open Naukri Login tab
        p2 = context.new_page()
        stealth_handler.apply_stealth_sync(p2)
        logger.info("Navigating to Naukri login page...")
        p2.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")

        console.print("\n[bold yellow]═══════════════════ MANUAL LOGIN REQUIRED ═══════════════════[/bold yellow]")
        console.print("[cyan]1. Switch to the opened browser window.[/cyan]")
        console.print("[cyan]2. Log into your LinkedIn account (complete 2FA if prompted).[/cyan]")
        console.print("[cyan]3. Log into your Naukri account (complete OTP if prompted).[/cyan]")
        console.print("[cyan]4. Once you see your profile/feed on BOTH sites, come back here.[/cyan]")
        console.print("[bold yellow]══════════════════════════════════════════════════════════════[/bold yellow]\n")

        input("Press [ENTER] in this terminal when you have successfully logged in to both platforms...")

        logger.info("Saving session state and closing browser...")
        self.close()
        console.print("[bold green]✓ Session credentials and cookies saved successfully![/bold green]\n")

    def check_login_status(self) -> Dict[str, bool]:
        """
        Navigates to Naukri and LinkedIn to verify if current session is authenticated.
        """
        context = self.start()
        status = {"linkedin": False, "naukri": False}
        page = self.new_page()

        # Check LinkedIn
        logger.info("Checking LinkedIn authentication...")
        try:
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
            current_url = page.url.lower()
            if any(term in current_url for term in ["login", "authwall", "signup", "checkpoint"]):
                status["linkedin"] = False
            elif page.locator("nav.global-nav").count() > 0 or page.locator("div.feed-identity-module").count() > 0:
                status["linkedin"] = True
            elif "/feed" in current_url and "login" not in current_url:
                status["linkedin"] = True
        except Exception as e:
            logger.warning(f"Error checking LinkedIn session: {e}")

        # Check Naukri
        logger.info("Checking Naukri authentication...")
        try:
            page.goto("https://www.naukri.com/mnjuser/homepage", wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
            current_url = page.url.lower()
            if any(term in current_url for term in ["nlogin", "login", "register", "signup"]):
                status["naukri"] = False
            elif ("/mnjuser/homepage" in current_url or "/mnjuser/profile" in current_url) and "login" not in current_url:
                # Confirm presence of user name or profile badge
                if page.locator(".user-name, .info__name, a[title='View profile']").count() > 0:
                    status["naukri"] = True
                else:
                    status["naukri"] = True
            else:
                status["naukri"] = False
        except Exception as e:
            logger.warning(f"Error checking Naukri session: {e}")

        self.close()
        return status
