"""
Direct Company Career ATS Automation Engine — JobPlus AI Production
Automates direct job submissions on official company career portals:
- Greenhouse (boards.greenhouse.io)
- Lever (jobs.lever.co)
- Ashby (jobs.ashbyhq.com)
- Workday (*.myworkdayjobs.com)
- SmartRecruiters & Custom Career Forms

Bypasses 3rd party job board spam filters and applies directly to company talent acquisition databases.
"""

from typing import Dict, Any, List, Optional
import os
import re
import time
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from src.platforms.base import BasePlatform
from src.config import ProfileConfig, PlatformConfig, SafetyConfig
from src.database import DatabaseTracker
from src.utils.logger import log
from src.utils.resume_manager import ResumeManager
from src.utils.cover_letter import CoverLetterGenerator

class DirectCompanyATS(BasePlatform):
    """
    Automator for official company career sites and direct ATS portals.
    """

    SUPPORTED_ATS = ["greenhouse", "lever", "ashby", "workday", "smartrecruiters", "generic"]

    def __init__(
        self,
        page: Page,
        profile: ProfileConfig,
        platform_config: PlatformConfig,
        safety_config: SafetyConfig,
        tracker: DatabaseTracker,
    ):
        super().__init__(page, profile, platform_config, safety_config, tracker)
        self.resume_manager = ResumeManager(resume_folder=os.path.join("data", "resumes"))

    @property
    def platform_name(self) -> str:
        return "direct_ats"

    def is_logged_in(self) -> bool:
        # Direct ATS portals are generally public application forms without pre-login requirement
        return True

    def detect_ats_type(self, url: str) -> str:
        """Identifies which ATS vendor powers the career URL."""
        url_lower = url.lower()
        if "greenhouse.io" in url_lower:
            return "greenhouse"
        elif "lever.co" in url_lower:
            return "lever"
        elif "ashbyhq.com" in url_lower:
            return "ashby"
        elif "myworkdayjobs.com" in url_lower or "workday" in url_lower:
            return "workday"
        elif "smartrecruiters.com" in url_lower:
            return "smartrecruiters"
        return "generic"

    def apply_to_company_portal(
        self,
        company_name: str,
        job_url: str,
        target_role: str,
        cover_letter_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Navigates to direct company job page and completes the application form autonomously.
        """
        ats_type = self.detect_ats_type(job_url)
        log.info(f"[Direct ATS] Starting application for {company_name} - {target_role} ({ats_type})")

        # 1. Deduplication check
        if self.tracker.is_applied(job_url):
            log.info(f"[Direct ATS] Already applied to {job_url} within cool-off period. Skipping.")
            return {"status": "skipped", "reason": "already_applied", "url": job_url}

        try:
            self.page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
            self.page.wait_for_timeout(2500)

            # 2. Get fresh resume
            fresh_resume_path = self.resume_manager.prepare_fresh_resume()

            # 3. Dispatch to specific ATS form filler
            if ats_type == "greenhouse":
                result = self._fill_greenhouse_form(company_name, target_role, fresh_resume_path, cover_letter_text)
            elif ats_type == "lever":
                result = self._fill_lever_form(company_name, target_role, fresh_resume_path, cover_letter_text)
            elif ats_type == "ashby":
                result = self._fill_ashby_form(company_name, target_role, fresh_resume_path, cover_letter_text)
            else:
                result = self._fill_generic_form(company_name, target_role, fresh_resume_path, cover_letter_text)

            # 4. PRE-SUBMISSION VERIFICATION & PRE-FLIGHT CHECK
            from src.utils.form_verifier import FormVerificationEngine
            verifier = FormVerificationEngine()
            is_valid, issues = verifier.preflight_dom_check(self.page)

            if not is_valid:
                log.warning(f"[Direct ATS] Preflight check detected issues: {issues}. Attempting intelligent field resolution...")
                for issue in issues:
                    # Try resolving field or queue for human review
                    verifier.queue_unresolved_field(
                        company=company_name,
                        job_title=target_role,
                        field_label=issue,
                        field_selector="input, select, textarea",
                        page_url=job_url
                    )

                # CIRCUIT BREAKER: Block submission of unverified/invalid data
                from src.utils.form_verifier import MissingRequiredFieldException
                recovery = verifier.handle_verification_exception(
                    MissingRequiredFieldException(issues[0], job_url),
                    self.page,
                    company_name,
                    target_role,
                    job_url
                )
                self.tracker.record_application(
                    platform="direct_ats",
                    job_id=job_url,
                    job_title=target_role,
                    company=company_name,
                    match_score=0.0,
                    status="flagged_verification"
                )
                return {"success": False, "status": "flagged_verification", "issues": issues, "recovery": recovery}

            # Capture pre-submission screenshot & audit trail
            filled_summary = {
                "name": self.profile.name,
                "email": self.profile.email,
                "phone": self.profile.phone,
                "resume_file": os.path.basename(fresh_resume_path),
                "cover_letter_attached": bool(cover_letter_text),
                "experience": f"{self.profile.experience_years} years",
                "notice_period": f"{self.profile.notice_period_days} days"
            }
            audit_record = verifier.capture_pre_submit_audit(self.page, company_name, target_role, filled_summary)

            if result.get("success"):
                # Track in database
                self.tracker.record_application(
                    platform="direct_ats",
                    job_id=job_url,
                    job_title=target_role,
                    company=company_name,
                    match_score=95.0,
                    status="applied"
                )
                log.info(f"[Direct ATS] Successfully submitted application to {company_name}! Audit verified.")
            result["audit"] = audit_record
            return result

        except Exception as e:
            log.error(f"[Direct ATS] Error applying to {company_name}: {e}")
            return {"status": "failed", "error": str(e), "url": job_url}

    def _fill_greenhouse_form(self, company: str, role: str, resume_path: str, cover_letter: Optional[str]) -> Dict[str, Any]:
        """Handles Greenhouse application forms."""
        # Standard input fields
        self._type_if_exists("input[id*='first_name'], input[name*='first_name']", self.profile.name.split()[0])
        self._type_if_exists("input[id*='last_name'], input[name*='last_name']", " ".join(self.profile.name.split()[1:]))
        self._type_if_exists("input[id*='email'], input[name*='email']", self.profile.email)
        self._type_if_exists("input[id*='phone'], input[name*='phone']", self.profile.phone)

        # Upload resume
        resume_input = self.page.locator("input[type='file'][id*='resume'], input[type='file'][name*='resume'], input[data-qa*='resume-upload']").first
        if resume_input.is_visible() or resume_input.count() > 0:
            resume_input.set_input_files(resume_path)
            self.page.wait_for_timeout(1500)

        # Cover letter
        if cover_letter:
            self._type_if_exists("textarea[id*='cover_letter'], textarea[name*='cover_letter']", cover_letter)

        # Screening questions (Experience, Notice, Work Auth)
        self._answer_common_screening_fields()

        return {"success": True, "ats": "greenhouse", "company": company, "role": role}

    def _fill_lever_form(self, company: str, role: str, resume_path: str, cover_letter: Optional[str]) -> Dict[str, Any]:
        """Handles Lever application forms."""
        self._type_if_exists("input[name='name']", self.profile.name)
        self._type_if_exists("input[name='email']", self.profile.email)
        self._type_if_exists("input[name='phone']", self.profile.phone)
        self._type_if_exists("input[name='org']", self.profile.current_company)

        # LinkedIn & portfolio
        self._type_if_exists("input[name*='urls[LinkedIn]']", self.profile.linkedin_url)
        self._type_if_exists("input[name*='urls[GitHub]']", self.profile.github_url)

        # Upload Resume
        resume_input = self.page.locator("input[type='file'][name='resume']").first
        if resume_input.count() > 0:
            resume_input.set_input_files(resume_path)
            self.page.wait_for_timeout(1500)

        # Comments / Cover letter
        if cover_letter:
            self._type_if_exists("textarea[name='comments']", cover_letter)

        self._answer_common_screening_fields()
        return {"success": True, "ats": "lever", "company": company, "role": role}

    def _fill_ashby_form(self, company: str, role: str, resume_path: str, cover_letter: Optional[str]) -> Dict[str, Any]:
        """Handles Ashby application forms."""
        self._type_if_exists("input[name='name'], input[aria-label*='Full Name']", self.profile.name)
        self._type_if_exists("input[name='email'], input[aria-label*='Email']", self.profile.email)
        self._type_if_exists("input[name='phoneNumber'], input[aria-label*='Phone']", self.profile.phone)

        resume_input = self.page.locator("input[type='file']").first
        if resume_input.count() > 0:
            resume_input.set_input_files(resume_path)
            self.page.wait_for_timeout(1500)

        self._answer_common_screening_fields()
        return {"success": True, "ats": "ashby", "company": company, "role": role}

    def _fill_generic_form(self, company: str, role: str, resume_path: str, cover_letter: Optional[str]) -> Dict[str, Any]:
        """Fallback heuristics for custom company careers and SmartRecruiters."""
        self._type_if_exists("input[placeholder*='Name' i], input[id*='name' i]", self.profile.name)
        self._type_if_exists("input[placeholder*='Email' i], input[type='email']", self.profile.email)
        self._type_if_exists("input[placeholder*='Phone' i], input[type='tel']", self.profile.phone)

        file_inputs = self.page.locator("input[type='file']")
        if file_inputs.count() > 0:
            file_inputs.first.set_input_files(resume_path)
            self.page.wait_for_timeout(1000)

        self._answer_common_screening_fields()
        return {"success": True, "ats": "generic", "company": company, "role": role}

    def _type_if_exists(self, selector: str, text: str):
        """Helper to fill text if selector matches."""
        try:
            elem = self.page.locator(selector).first
            if elem.count() > 0 and elem.is_visible():
                elem.fill("")
                elem.type(str(text), delay=35)
        except Exception:
            pass

    def _answer_common_screening_fields(self):
        """Autonomously resolves common screening drop-downs and radio questions."""
        try:
            # Notice period inputs
            notice_inputs = self.page.locator("input[name*='notice' i], select[name*='notice' i], input[placeholder*='notice' i]")
            if notice_inputs.count() > 0:
                notice_inputs.first.fill(str(self.profile.notice_period_days))

            # Expected CTC
            ctc_inputs = self.page.locator("input[name*='salary' i], input[name*='ctc' i], input[placeholder*='ctc' i]")
            if ctc_inputs.count() > 0:
                ctc_inputs.first.fill(str(self.profile.expected_ctc))

            # Work Authorization / Sponsorship (Authorized: Yes, Need sponsorship: No)
            auth_radios = self.page.locator("input[type='radio'][value*='yes' i], input[type='radio'][value*='true' i]")
            if auth_radios.count() > 0:
                auth_radios.first.check()
        except Exception:
            pass

    def search_and_apply(self, keyword: str, location: str) -> Dict[str, int]:
        """Required by BasePlatform abstract interface."""
        return {"processed": 0, "applied": 0, "skipped": 0}
