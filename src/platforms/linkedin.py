import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from playwright.sync_api import Locator, Page
from src.browser import BrowserManager
from src.config import PlatformConfig, ProfileConfig, SafetyConfig
from src.database import DatabaseTracker
from src.platforms.base import BasePlatform
from src.platforms.email_outreach import EmailOutreachEngine
from src.utils.logger import logger, console
from src.utils.resume_matcher import ResumeMatcher

class LinkedInAutomator(BasePlatform):
    """Automation engine for LinkedIn Easy Apply jobs and HR email outreach."""

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
        self.outreach = EmailOutreachEngine(profile, tracker)

    @property
    def platform_name(self) -> str:
        return "linkedin"

    def is_logged_in(self) -> bool:
        """Verifies if the session is currently authenticated on LinkedIn."""
        try:
            self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=25000)
            self.page.wait_for_timeout(3000)
            current_url = self.page.url.lower()

            if any(term in current_url for term in ["login", "authwall", "signup", "checkpoint"]):
                return False

            if page_nav := self.page.locator("nav.global-nav"):
                if page_nav.count() > 0:
                    return True

            return "/feed" in current_url
        except Exception as e:
            logger.warning(f"Error checking LinkedIn login: {e}")
            return False

    def build_search_url(self, keyword: str, location: str) -> str:
        """Builds LinkedIn Jobs search URL filtered specifically by Easy Apply (f_AL=true)."""
        kw = quote_plus(keyword.strip())
        loc = quote_plus(location.strip())
        # f_AL=true filters exclusively for Easy Apply
        return f"https://www.linkedin.com/jobs/search/?keywords={kw}&location={loc}&f_AL=true"

    def extract_job_cards(self) -> List[Dict[str, Any]]:
        """Parses job cards displayed in LinkedIn job search results."""
        jobs: List[Dict[str, Any]] = []

        card_selectors = [
            "li.jobs-search-results__list-item",
            "div.job-card-container",
            "div[data-job-id]",
        ]

        active_selector = None
        for sel in card_selectors:
            if self.page.locator(sel).count() > 0:
                active_selector = sel
                break

        if not active_selector:
            logger.warning("No job cards found with known selectors on LinkedIn.")
            return jobs

        cards = self.page.locator(active_selector).all()
        logger.info(f"Found {len(cards)} LinkedIn Easy Apply job cards.")

        for card in cards:
            try:
                # Title
                title_elem = card.locator("a.job-card-list__title, a.job-card-container__link")
                if title_elem.count() == 0:
                    continue

                title = title_elem.first.inner_text().strip()
                url = title_elem.first.get_attribute("href") or ""

                # Job ID
                job_id = card.get_attribute("data-occludable-job-id") or card.get_attribute("data-job-id") or ""
                if not job_id and url:
                    id_match = re.search(r"view/(\d+)", url) or re.search(r"currentJobId=(\d+)", url)
                    if id_match:
                        job_id = id_match.group(1)
                    else:
                        job_id = str(abs(hash(url)))

                # Company
                comp_elem = card.locator(".job-card-container__primary-description, .artdeco-entity-lockup__subtitle")
                company = comp_elem.first.inner_text().strip() if comp_elem.count() > 0 else "Unknown"

                # Location
                loc_elem = card.locator(".job-card-container__metadata-item")
                location = loc_elem.first.inner_text().strip() if loc_elem.count() > 0 else ""

                jobs.append({
                    "job_id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": url,
                    "card_element": card,
                })
            except Exception as e:
                logger.debug(f"Error parsing LinkedIn job card: {e}")
                continue

        return jobs

    def solve_modal_step(self, modal: Locator) -> bool:
        """
        Intelligently resolves form fields in the current Easy Apply modal step.
        Strictly handles:
         - Numeric fields (digits only, e.g. '3', not '3 years')
         - Yes/No questions (radio/select 'Yes' or 'No', not numbers)
         - Resume file upload (attaches fresh data/resume.pdf)
         - Select dropdowns & CTC
        """
        try:
            # 1. Check for Resume Upload field in this step
            file_input = modal.locator("input[type='file']")
            resume_path = Path(self.profile.resume_path)
            if file_input.count() > 0 and resume_path.exists():
                logger.info(f"[LinkedIn] Attaching updated resume: {resume_path}")
                file_input.first.set_input_files(str(resume_path.resolve()))
                self.page.wait_for_timeout(1500)

            # 2. Handle Radio Groups (Yes / No questions)
            radio_groups = modal.locator("fieldset").all()
            for rg in radio_groups:
                legend = rg.locator("legend").inner_text().strip().lower() if rg.locator("legend").count() > 0 else ""
                
                # Check question semantics
                if any(w in legend for w in ["sponsorship", "require visa"]):
                    # Visa sponsorship question: select No if not required
                    target_val = "Yes" if self.profile.work_authorization.requires_visa_sponsorship else "No"
                elif any(w in legend for w in ["authorized", "legally", "relocate", "commute", "background", "degree"]):
                    target_val = "Yes"
                else:
                    target_val = "Yes" # Default positive response

                # Click target radio button
                radio_option = rg.locator(f"label:has-text('{target_val}') input[type='radio'], input[value='{target_val}'], label:has-text('{target_val}')")
                if radio_option.count() > 0:
                    radio_option.first.click()

            # 3. Handle Dropdowns / Select elements
            select_elements = modal.locator("select").all()
            for sel in select_elements:
                label_elem = modal.locator(f"label[for='{sel.get_attribute('id')}']")
                label_text = label_elem.inner_text().strip().lower() if label_elem.count() > 0 else ""

                if "notice" in label_text:
                    # Select notice period option
                    sel.select_option(label=f"{self.profile.experience.notice_period_days} days")
                elif any(w in label_text for w in ["authorized", "sponsorship"]):
                    sel.select_option(label="Yes")
                else:
                    # Default: pick first valid non-empty option
                    sel.select_option(index=1)

            # 4. Handle Numeric and Text Input Fields
            text_inputs = modal.locator("input[type='text'], input[type='number']").all()
            for inp in text_inputs:
                input_id = inp.get_attribute("id") or ""
                label_elem = modal.locator(f"label[for='{input_id}']")
                label_text = label_elem.inner_text().strip().lower() if label_elem.count() > 0 else ""

                current_val = inp.input_value()
                if current_val and current_val.strip():
                    continue # Already filled (e.g. pre-filled phone or name)

                # Check if field requires NUMERIC ONLY (Experience, Years, GPA)
                is_numeric = (
                    inp.get_attribute("type") == "number"
                    or inp.get_attribute("pattern") == "[0-9]*"
                    or any(w in label_text for w in ["how many years", "years of", "experience", "gpa"])
                )

                if is_numeric:
                    # Input clean integer digits ONLY (e.g. '3', never '3 years')
                    years_val = str(int(self.profile.experience.total_years))
                    inp.fill(years_val)
                    logger.debug(f"Filled numeric field '{label_text}': {years_val}")

                # Check for CTC / Salary questions
                elif any(w in label_text for w in ["ctc", "salary", "compensation"]):
                    if "expected" in label_text:
                        ctc_val = str(int(self.profile.experience.expected_ctc_lakhs * 100000))
                    else:
                        ctc_val = str(int(self.profile.experience.current_ctc_lakhs * 100000))
                    inp.fill(ctc_val)

                # Check for City / Location
                elif any(w in label_text for w in ["city", "location"]):
                    inp.fill(self.profile.candidate.current_location)

                # Check for Website / Portfolio / LinkedIn URL
                elif "linkedin" in label_text and self.profile.candidate.linkedin_profile:
                    inp.fill(self.profile.candidate.linkedin_profile)

            # 5. Uncheck optional 'Follow company' checkbox if present
            follow_checkbox = modal.locator("label:has-text('Follow') input[type='checkbox']")
            if follow_checkbox.count() > 0 and follow_checkbox.first.is_checked():
                follow_checkbox.first.uncheck()

            return True
        except Exception as e:
            logger.warning(f"Error solving modal step: {e}")
            return False

    def apply_to_job(self, job: Dict[str, Any]) -> str:
        """
        Opens LinkedIn Easy Apply modal and completes the application flow.
        Also scans for HR recruiter email for automated outreach.
        """
        job_id = job["job_id"]
        title = job["title"]
        company = job["company"]
        url = job["url"]

        if self.tracker.is_applied("linkedin", job_id):
            logger.info(f"[LinkedIn] Skipping already applied job: {title} at {company}")
            return "already_applied"

        try:
            logger.info(f"[LinkedIn] Viewing job: {title} at {company}")
            # Click card or navigate to URL
            if job.get("card_element") and job["card_element"].is_visible():
                job["card_element"].click()
                self.page.wait_for_timeout(2500)
            elif url:
                self.page.goto(url, wait_until="domcontentloaded", timeout=25000)
                self.page.wait_for_timeout(2500)

            # Check job description for HR Email IDs for cold outreach
            jd_elem = self.page.locator(".jobs-description-content, .jobs-box__html-content")
            jd_text = jd_elem.inner_text() if jd_elem.count() > 0 else ""
            extracted_emails = self.outreach.extract_emails(jd_text)

            if extracted_emails:
                for hr_email in extracted_emails:
                    logger.info(f"[LinkedIn Outreach] Found HR email: {hr_email} in job post!")
                    self.outreach.send_email(
                        to_email=hr_email,
                        job_title=title,
                        company=company,
                        job_description=jd_text,
                    )

            # Locate Easy Apply Button
            easy_apply_btn = self.page.locator(
                "button.jobs-apply-button:has-text('Easy Apply'), button:has-text('Easy Apply')"
            )

            if easy_apply_btn.count() == 0:
                logger.info(f"[LinkedIn] Not an Easy Apply job -> Skipping: {title}")
                self.tracker.record_application(
                    platform="linkedin",
                    job_id=job_id,
                    title=title,
                    company=company,
                    location=job.get("location", ""),
                    url=url,
                    status="skipped",
                    notes="No Easy Apply button",
                )
                return "skipped"

            # Click Easy Apply
            easy_apply_btn.first.click()
            BrowserManager.human_delay(1.5, 2.5)

            # Modal Container
            modal = self.page.locator(".jobs-easy-apply-modal, div[role='dialog']")
            if modal.count() == 0:
                logger.warning(f"[LinkedIn] Easy Apply modal did not appear for: {title}")
                return "failed"

            # Loop through multi-step dialog (up to 8 steps max)
            max_steps = 8
            step_count = 0
            while step_count < max_steps:
                step_count += 1
                self.solve_modal_step(modal)
                BrowserManager.human_delay(1.0, 2.0)

                # Check buttons: Submit application, Review, Next
                submit_btn = modal.locator("button:has-text('Submit application')")
                review_btn = modal.locator("button:has-text('Review')")
                next_btn = modal.locator("button:has-text('Next')")

                if submit_btn.count() > 0 and submit_btn.first.is_visible():
                    logger.info(f"[LinkedIn] Submitting application for: {title}...")
                    submit_btn.first.click()
                    BrowserManager.human_delay(2.0, 3.0)
                    break
                elif review_btn.count() > 0 and review_btn.first.is_visible():
                    review_btn.first.click()
                    BrowserManager.human_delay(1.5, 2.5)
                elif next_btn.count() > 0 and next_btn.first.is_visible():
                    next_btn.first.click()
                    BrowserManager.human_delay(1.5, 2.5)
                else:
                    # Neither next nor submit found
                    break

            # Close confirmation modal if open
            dismiss_btn = self.page.locator("button[aria-label='Dismiss'], button:has-text('Done')")
            if dismiss_btn.count() > 0 and dismiss_btn.first.is_visible():
                dismiss_btn.first.click()

            logger.info(f"[bold green]✓ Successfully applied to {title} at {company} on LinkedIn![/bold green]")
            self.tracker.record_application(
                platform="linkedin",
                job_id=job_id,
                title=title,
                company=company,
                location=job.get("location", ""),
                url=url,
                status="applied",
            )
            return "applied"

        except Exception as e:
            logger.error(f"[LinkedIn] Error during Easy Apply for {title}: {e}")
            self.tracker.record_application(
                platform="linkedin",
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
        """Runs search and processes Easy Apply applications on LinkedIn."""
        results = {"applied": 0, "skipped": 0, "failed": 0}
        daily_limit = self.platform_config.daily_limit
        today_applied = self.tracker.get_today_applied_count("linkedin")

        if today_applied >= daily_limit:
            logger.warning(f"[LinkedIn] Daily limit reached ({today_applied}/{daily_limit}). Stopping for today.")
            return results

        search_url = self.build_search_url(keyword, location)
        logger.info(f"[LinkedIn] Navigating to Easy Apply search: {keyword} in {location}")
        logger.info(f"URL: {search_url}")

        try:
            self.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            BrowserManager.human_delay(3.0, 5.0)

            jobs = self.extract_job_cards()
            if not jobs:
                logger.warning(f"[LinkedIn] No Easy Apply jobs found for {keyword} in {location}")
                return results

            for job in jobs:
                if self.tracker.get_today_applied_count("linkedin") >= daily_limit:
                    logger.warning("[LinkedIn] Reached daily application quota.")
                    break

                status = self.apply_to_job(job)
                if status == "applied":
                    results["applied"] += 1
                elif status == "skipped":
                    results["skipped"] += 1
                elif status == "failed":
                    results["failed"] += 1

                BrowserManager.human_delay(
                    self.safety.min_delay_seconds,
                    self.safety.max_delay_seconds,
                )

        except Exception as e:
            logger.error(f"[LinkedIn] Search execution error: {e}")

        return results
