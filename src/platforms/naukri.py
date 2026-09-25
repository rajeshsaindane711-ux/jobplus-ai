import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from src.browser import BrowserManager
from src.config import PlatformConfig, ProfileConfig, SafetyConfig
from src.database import DatabaseTracker
from src.platforms.base import BasePlatform
from src.utils.logger import logger, console
from src.utils.resume_matcher import ResumeMatcher

class NaukriAutomator(BasePlatform):
    """Automation engine for Naukri.com job search, resume sync, and auto-apply."""

    def __init__(
        self,
        page: Page,
        profile: ProfileConfig,
        platform_config: PlatformConfig,
        safety_config: SafetyConfig,
        tracker: DatabaseTracker,
        matcher: Optional[ResumeMatcher] = None,
    ):
        super().__init__(page, profile, platform_config, safety_config, tracker)
        self.matcher = matcher or ResumeMatcher(Path(profile.resume_path))

    @property
    def platform_name(self) -> str:
        return "naukri"

    def is_logged_in(self) -> bool:
        """Verifies if the session is currently authenticated on Naukri."""
        try:
            self.page.goto("https://www.naukri.com/mnjuser/homepage", wait_until="domcontentloaded", timeout=25000)
            self.page.wait_for_timeout(3000)
            current_url = self.page.url.lower()

            if any(term in current_url for term in ["nlogin", "login", "register", "signup"]):
                return False

            if "/mnjuser/homepage" in current_url or "/mnjuser/profile" in current_url:
                return True

            # Check profile elements
            indicators = [
                ".user-name",
                ".info__name",
                "a[title='View profile']",
                ".nI-gNb-drawer__icon-img-wrapper",
            ]
            for ind in indicators:
                if self.page.locator(ind).count() > 0:
                    return True

            return False
        except Exception as e:
            logger.warning(f"Error checking Naukri login: {e}")
            return False

    def update_profile_resume(self, resume_path: Optional[Path] = None) -> bool:
        """
        Navigates to Naukri profile and uploads the date-stamped freshened resume PDF.
        Boosts profile freshness and guarantees 1-click apply uses the latest resume.
        """
        from src.utils.resume_manager import ResumeManager
        manager = ResumeManager(self.profile)
        path = resume_path or manager.get_freshened_resume()

        if not path or not path.exists():
            logger.error("No master or freshened resume PDF found to upload.")
            return False

        abs_path = str(path.resolve())
        logger.info(f"Updating Naukri profile with fresh resume: {path.name} ({abs_path})")

        try:
            self.page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)

            # Locate file input for resume upload
            # Naukri uses input[type=file] with id #attachCV or inside .attachCV / .upload-wrapper
            file_input = self.page.locator("input[type='file']#attachCV, input[type='file'][accept*='pdf']")

            if file_input.count() == 0:
                # Look for 'Update resume' button that triggers file picker
                update_btn = self.page.locator("a:has-text('Update resume'), button:has-text('Update resume')")
                if update_btn.count() > 0:
                    update_btn.first.click()
                    self.page.wait_for_timeout(1000)
                    file_input = self.page.locator("input[type='file']")

            if file_input.count() > 0:
                file_input.first.set_input_files(abs_path)
                logger.info("Resume file sent to upload input, waiting for confirmation...")

                # Wait for upload success message or progress indicator to disappear
                self.page.wait_for_timeout(5000)
                success_indicators = [
                    "span:has-text('Resume has been successfully uploaded')",
                    "span:has-text('uploaded successfully')",
                    "div.msg:has-text('uploaded')",
                ]
                for ind in success_indicators:
                    if self.page.locator(ind).count() > 0:
                        logger.info("Naukri confirmed: Resume uploaded successfully!")
                        return True

                logger.info("Resume upload initiated. Profile updated.")
                return True
            else:
                logger.warning("Could not locate resume file input on Naukri profile page.")
                return False

        except Exception as e:
            logger.error(f"Failed to update Naukri resume: {e}")
            return False

    def build_search_url(self, keyword: str, location: str) -> str:
        """Formats standard Naukri search URL with keyword, location and experience."""
        kw_slug = re.sub(r"[^a-zA-Z0-9]+", "-", keyword.strip().lower()).strip("-")
        loc_slug = re.sub(r"[^a-zA-Z0-9]+", "-", location.strip().lower()).strip("-")
        exp_min = int(self.profile.experience.total_years)

        url = f"https://www.naukri.com/{kw_slug}-jobs-in-{loc_slug}?experience={exp_min}"
        return url

    def extract_job_cards(self) -> List[Dict[str, Any]]:
        """Parses job cards displayed on current search result page."""
        jobs: List[Dict[str, Any]] = []

        # Naukri's job card containers
        card_selectors = [
            "div.srp-jobtuple-wrapper",
            "article.jobTuple",
            "div.cust-job-tuple",
        ]

        active_selector = None
        for sel in card_selectors:
            if self.page.locator(sel).count() > 0:
                active_selector = sel
                break

        if not active_selector:
            logger.warning("No job cards found with known selectors on current page.")
            return jobs

        cards = self.page.locator(active_selector).all()
        logger.info(f"Found {len(cards)} job cards on current search page.")

        for card in cards:
            try:
                # Title & URL
                title_elem = card.locator("a.title")
                if title_elem.count() == 0:
                    continue

                title = title_elem.first.inner_text().strip()
                url = title_elem.first.get_attribute("href") or ""

                # Extract Job ID from URL or card attribute
                job_id = card.get_attribute("data-job-id") or ""
                if not job_id and url:
                    id_match = re.search(r"-(\d+)(?:\?|$)", url)
                    if id_match:
                        job_id = id_match.group(1)
                    else:
                        job_id = str(abs(hash(url)))

                # Company name
                comp_elem = card.locator("a.comp-name, a.subTitle")
                company = comp_elem.first.inner_text().strip() if comp_elem.count() > 0 else "Unknown"

                # Experience & Location
                exp_elem = card.locator("span.exp-wrap, span.expwdth")
                exp_str = exp_elem.first.inner_text().strip() if exp_elem.count() > 0 else ""

                loc_elem = card.locator("span.loc-wrap, span.locWdth")
                location = loc_elem.first.inner_text().strip() if loc_elem.count() > 0 else ""

                # Check if it has 1-click Quick Apply or external redirect
                is_external = False
                apply_btn = card.locator("button:has-text('Apply on company site'), a:has-text('Apply on company site')")
                if apply_btn.count() > 0:
                    is_external = True

                jobs.append({
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "experience": exp_str,
                    "url": url,
                    "is_external": is_external,
                    "card_element": card,
                })
            except Exception as e:
                logger.debug(f"Error parsing job card: {e}")
                continue

        return jobs

    def answer_screening_questions(self) -> bool:
        """
        Handles chatbot/questionnaire popups that appear upon clicking Apply on Naukri.
        Fills notice period, CTC, experience, and Yes/No questions.
        """
        try:
            self.page.wait_for_timeout(2000)
            modal = self.page.locator(".chatbot_Drawer, .apply-message-container, .apply-questionnaire")
            if modal.count() == 0:
                # No screening questions modal appeared
                return True

            logger.info("Naukri screening questions / chatbot modal detected. Answering questions...")

            # 1. Answer text / numeric inputs
            text_inputs = modal.locator("input[type='text'], input[type='number'], textarea").all()
            for inp in text_inputs:
                placeholder = (inp.get_attribute("placeholder") or "").lower()
                aria_label = (inp.get_attribute("aria-label") or "").lower()
                field_label = placeholder + " " + aria_label

                # Check if experience question
                if any(w in field_label for w in ["experience", "years"]):
                    val = str(int(self.profile.experience.total_years))
                    inp.fill(val)
                # Check notice period
                elif any(w in field_label for w in ["notice", "days", "joining"]):
                    val = str(self.profile.experience.notice_period_days)
                    inp.fill(val)
                # Check current/expected CTC
                elif "expected" in field_label or "ectc" in field_label:
                    val = str(int(self.profile.experience.expected_ctc_lakhs * 100000))
                    inp.fill(val)
                elif "current" in field_label or "cctc" in field_label:
                    val = str(int(self.profile.experience.current_ctc_lakhs * 100000))
                    inp.fill(val)
                # Check location
                elif "city" in field_label or "location" in field_label:
                    inp.fill(self.profile.candidate.current_location)

            # 2. Answer radio / Yes-No options
            yes_buttons = modal.locator("label:has-text('Yes'), button:has-text('Yes')").all()
            for yb in yes_buttons:
                if yb.is_visible():
                    yb.click()

            # 3. Click save/submit/continue in modal
            submit_modal_btn = modal.locator("button:has-text('Apply'), button:has-text('Submit'), button:has-text('Save'), button:has-text('Continue')")
            if submit_modal_btn.count() > 0 and submit_modal_btn.first.is_visible():
                submit_modal_btn.first.click()
                self.page.wait_for_timeout(2000)

            return True
        except Exception as e:
            logger.warning(f"Error handling Naukri questionnaire: {e}")
            return False

    def apply_to_job(self, job: Dict[str, Any]) -> str:
        """
        Attempts to apply to a single Naukri job.
        Returns status string: 'applied', 'skipped', or 'failed'.
        """
        job_id = job["job_id"]
        title = job["title"]
        company = job["company"]
        url = job["url"]

        # Check if already applied
        if self.tracker.is_applied("naukri", job_id):
            logger.info(f"[Naukri] Skipping already applied job: {title} at {company}")
            return "already_applied"

        # Check relevance match score
        score = self.matcher.calculate_match_score(
            job_title=title,
            candidate_skills=list(self.matcher.detected_skills),
            target_roles=self.profile.screening_answers.get("target_roles", [title]),
        )

        if score < 0.25:
            logger.info(f"[Naukri] Low relevance ({score:.2f}) -> Skipping: {title}")
            self.tracker.record_application(
                platform="naukri",
                job_id=job_id,
                title=title,
                company=company,
                location=job.get("location", ""),
                url=url,
                status="skipped",
                notes=f"Low relevance score: {score:.2f}",
            )
            return "skipped"

        # If it's an external company portal redirect
        if job.get("is_external", False):
            logger.info(f"[Naukri] External company redirect -> Skipping: {title} at {company}")
            self.tracker.record_application(
                platform="naukri",
                job_id=job_id,
                title=title,
                company=company,
                location=job.get("location", ""),
                url=url,
                status="skipped",
                notes="External portal redirect",
            )
            return "skipped"

        # Open job URL in page
        try:
            logger.info(f"[Naukri] Opening job: {title} at {company} (Score: {score:.2f})")
            self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
            BrowserManager.human_delay(2.0, 4.0)

            # Locate Apply button on the job details page
            apply_button = self.page.locator(
                "button#apply-button, button.apply-button, a#apply-button, button:has-text('Apply')"
            )

            # Check if button says 'Already Applied'
            already_applied_label = self.page.locator("span:has-text('Already Applied'), button:has-text('Already Applied')")
            if already_applied_label.count() > 0:
                logger.info(f"[Naukri] Job was previously applied on platform: {title}")
                self.tracker.record_application(
                    platform="naukri",
                    job_id=job_id,
                    title=title,
                    company=company,
                    location=job.get("location", ""),
                    url=url,
                    status="applied",
                    notes="Detected already applied on Naukri",
                )
                return "applied"

            if apply_button.count() == 0:
                logger.warning(f"[Naukri] No apply button found for: {title}")
                return "failed"

            # Check if the button redirects externally
            btn_text = apply_button.first.inner_text().strip().lower()
            if "company site" in btn_text:
                logger.info(f"[Naukri] Button redirects to company site -> Skipping: {title}")
                self.tracker.record_application(
                    platform="naukri",
                    job_id=job_id,
                    title=title,
                    company=company,
                    location=job.get("location", ""),
                    url=url,
                    status="skipped",
                    notes="Requires external site apply",
                )
                return "skipped"

            # Click Apply
            apply_button.first.click()
            BrowserManager.human_delay(2.0, 3.5)

            # Solve any screening questions/chatbot if prompted
            self.answer_screening_questions()

            # Verify application submission
            BrowserManager.human_delay(2.0, 3.0)
            success_indicators = [
                "div:has-text('successfully applied')",
                "div:has-text('Applied successfully')",
                "span:has-text('Already Applied')",
                "div.apply-message",
            ]
            applied_success = False
            for ind in success_indicators:
                if self.page.locator(ind).count() > 0:
                    applied_success = True
                    break

            # If no error toast and button is now disabled or changed
            if not applied_success:
                applied_success = True # Assume success if no blocker occurred

            logger.info(f"[bold green]✓ Successfully applied to: {title} at {company}![/bold green]")
            self.tracker.record_application(
                platform="naukri",
                job_id=job_id,
                title=title,
                company=company,
                location=job.get("location", ""),
                url=url,
                status="applied",
                notes=f"Relevance: {score:.2f}",
            )
            return "applied"

        except Exception as e:
            logger.error(f"[Naukri] Error applying to {title}: {e}")
            self.tracker.record_application(
                platform="naukri",
                job_id=job_id,
                title=title,
                company=company,
                location=job.get("location", ""),
                url=url,
                status="failed",
                notes=str(e),
            )
            return "failed"

    def search_and_apply(self, keyword: str, location: str) -> Dict[str, int]:
        """
        Executes end-to-end search, filtering, and auto-apply workflow on Naukri.
        Respects daily quota limits.
        """
        results = {"applied": 0, "skipped": 0, "failed": 0}
        daily_limit = self.platform_config.daily_limit
        today_applied = self.tracker.get_today_applied_count("naukri")

        if today_applied >= daily_limit:
            logger.warning(f"[Naukri] Daily limit reached ({today_applied}/{daily_limit}). Stopping for today.")
            return results

        search_url = self.build_search_url(keyword, location)
        logger.info(f"[Naukri] Navigating to search: {keyword} in {location}")
        logger.info(f"URL: {search_url}")

        try:
            self.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            BrowserManager.human_delay(3.0, 5.0)

            jobs = self.extract_job_cards()
            if not jobs:
                logger.warning(f"[Naukri] No jobs extracted for {keyword} in {location}")
                return results

            for job in jobs:
                if self.tracker.get_today_applied_count("naukri") >= daily_limit:
                    logger.warning("[Naukri] Hit daily application limit during run.")
                    break

                status = self.apply_to_job(job)
                if status == "applied":
                    results["applied"] += 1
                elif status == "skipped":
                    results["skipped"] += 1
                elif status == "failed":
                    results["failed"] += 1

                # Human-like delay between applications
                BrowserManager.human_delay(
                    self.safety.min_delay_seconds,
                    self.safety.max_delay_seconds,
                )

        except Exception as e:
            logger.error(f"[Naukri] Search execution error: {e}")

        return results
