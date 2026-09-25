import email
import os
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.config import ProfileConfig
from src.database import DatabaseTracker
from src.utils.logger import logger, console

# Regex to detect emails in text
EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

# Common system domains to ignore
IGNORED_DOMAINS = [
    "linkedin.com", "naukri.com", "example.com", "w3.org", "sentry.io",
    "github.com", "google.com", "facebook.com", "twitter.com"
]

class EmailOutreachEngine:
    """Extracts HR email IDs from job posts, crafts tailored drafts, and sends via Gmail."""

    def __init__(self, profile: ProfileConfig, tracker: DatabaseTracker):
        self.profile = profile
        self.tracker = tracker
        self._init_outreach_table()

    def _init_outreach_table(self):
        """Ensures email outreach tracking table exists in SQLite."""
        with self.tracker._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hr_outreach_emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipient_email TEXT NOT NULL UNIQUE,
                    job_title TEXT NOT NULL,
                    company TEXT,
                    subject TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL,
                    notes TEXT
                )
            """)
            conn.commit()

    def is_emailed(self, email_address: str) -> bool:
        """Checks if we have already contacted this HR email."""
        with self.tracker._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM hr_outreach_emails WHERE recipient_email = ? AND status = 'sent'",
                (email_address.lower().strip(),),
            )
            return cursor.fetchone() is not None

    def record_email_sent(
        self,
        recipient_email: str,
        job_title: str,
        company: str,
        subject: str,
        status: str = "sent",
        notes: str = "",
    ):
        """Logs sent email to prevent duplicate cold outreach."""
        try:
            with self.tracker._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO hr_outreach_emails (recipient_email, job_title, company, subject, status, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(recipient_email) DO UPDATE SET
                        status = excluded.status,
                        sent_at = CURRENT_TIMESTAMP,
                        notes = excluded.notes
                    """,
                    (recipient_email.lower().strip(), job_title, company, subject, status, notes),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to record email to {recipient_email}: {e}")

    def extract_emails(self, text: str) -> List[str]:
        """Finds valid HR/recruiter emails inside job post text."""
        raw_matches = re.findall(EMAIL_REGEX, text)
        valid_emails = []
        for em in raw_matches:
            em_clean = em.lower().strip()
            domain = em_clean.split("@")[-1]
            if not any(ig in domain for ig in IGNORED_DOMAINS):
                if em_clean not in valid_emails:
                    valid_emails.append(em_clean)
        return valid_emails

    def generate_email_content(
        self,
        job_title: str,
        company: str = "",
        job_description: str = "",
    ) -> Dict[str, str]:
        """
        Builds natural, human-written email content from config/email_templates.yaml.
        Allows complete user editing of wording and tone.
        """
        import yaml
        from src.config import CONFIG_DIR

        c = self.profile.candidate
        exp = self.profile.experience
        candidate_name = f"{c.first_name} {c.last_name}".strip()

        # Format Notice Period
        if exp.notice_period_days == 0:
            notice_str = "Immediate Joiner"
            notice_detail = "Immediate joiner (can start right away)"
        else:
            notice_str = f"{exp.notice_period_days} Days"
            if "immediate" in job_description.lower() and exp.notice_period_days <= 15:
                notice_detail = "Serving notice period (can join immediately / within 15 days)"
            else:
                notice_detail = f"{exp.notice_period_days} days (negotiable for early joining)"

        company_or_team = f"hiring team at {company}" if company else "Hiring Team"
        company_mention = f" currently at {exp.current_company}" if exp.current_company else ""

        variables = {
            "name": candidate_name,
            "first_name": c.first_name,
            "job_title": job_title,
            "company": company,
            "company_or_team": company_or_team,
            "company_mention": company_mention,
            "total_years": str(exp.total_years),
            "current_title": exp.current_job_title or "Software Developer",
            "current_company": exp.current_company,
            "location": c.current_location or "India",
            "notice_period": notice_str,
            "notice_period_detail": notice_detail,
            "current_ctc": str(exp.current_ctc_lakhs),
            "expected_ctc": str(exp.expected_ctc_lakhs),
            "phone": f"{c.phone_country_code} {c.phone}".strip(),
            "email": c.email,
            "linkedin": c.linkedin_profile or "",
        }

        # Load templates from YAML if available
        template_file = CONFIG_DIR / "email_templates.yaml"
        templates = {}
        if template_file.exists():
            try:
                with open(template_file, "r", encoding="utf-8") as f:
                    templates = yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Could not read email_templates.yaml: {e}")

        # Subject
        subj_tmpl = templates.get(
            "subject_template",
            "Application: {job_title} - {name} ({total_years} Yrs | {notice_period} Notice)",
        )
        subject = subj_tmpl.format(**variables)

        # Body selection
        if job_description.strip():
            body_tmpl = templates.get("with_job_description")
        else:
            body_tmpl = templates.get("cold_outreach_no_jd")

        if body_tmpl:
            body = body_tmpl.format(**variables)
        else:
            body = f"Hi {company_or_team},\n\nI saw your opening for {job_title} and wanted to reach out.\n\nThanks,\n{candidate_name}"

        return {"subject": subject.strip(), "body": body.strip()}

    def send_email(
        self,
        to_email: str,
        job_title: str,
        company: str = "",
        job_description: str = "",
        resume_path: Optional[Path] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
    ) -> bool:
        """
        Sends application email with resume attached.
        If SMTP credentials are not configured, runs in preview / test mode.
        """
        if self.is_emailed(to_email):
            logger.info(f"Skipping already contacted HR email: {to_email}")
            return False

        content = self.generate_email_content(job_title, company, job_description)
        subject = content["subject"]
        body = content["body"]

        # Check credentials from parameters or env
        user = smtp_user or os.getenv("GMAIL_ADDRESS") or self.profile.candidate.email
        password = smtp_password or os.getenv("GMAIL_APP_PASSWORD")

        from src.utils.resume_manager import ResumeManager
        manager = ResumeManager(self.profile)
        pdf_path = resume_path or manager.get_freshened_resume() or Path(self.profile.resume_path)

        if not password:
            # Preview / dry-run mode
            console.print(f"\n[bold yellow]--- HR Email Preview (No GMAIL_APP_PASSWORD set) ---[/bold yellow]")
            console.print(f"[cyan]To:[/cyan] {to_email}")
            console.print(f"[cyan]Subject:[/cyan] {subject}")
            console.print(f"[cyan]Body:[/cyan]\n{body}")
            console.print(f"[cyan]Attachment:[/cyan] {pdf_path}")
            console.print(f"[yellow]Set GMAIL_APP_PASSWORD in environment or config to send live.[/yellow]\n")
            self.record_email_sent(to_email, job_title, company, subject, status="preview", notes="Simulated preview")
            return True

        # Send live email via SMTP SSL
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = to_email
            msg.set_content(body)

            if pdf_path.exists():
                with open(pdf_path, "rb") as f:
                    file_data = f.read()
                    file_name = pdf_path.name
                msg.add_attachment(file_data, maintype="application", subtype="pdf", filename=file_name)

            logger.info(f"Sending email to {to_email} via Gmail SMTP...")
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)

            logger.info(f"[bold green]✓ Application email successfully sent to {to_email}![/bold green]")
            self.record_email_sent(to_email, job_title, company, subject, status="sent")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            self.record_email_sent(to_email, job_title, company, subject, status="failed", notes=str(e))
            return False
