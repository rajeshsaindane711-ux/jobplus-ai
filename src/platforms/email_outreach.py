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
        Builds customized professional subject line and body.
        Adapts dynamically if job description is present or empty.
        Handles notice period and CTC requirements intelligently.
        """
        c = self.profile.candidate
        exp = self.profile.experience
        candidate_name = f"{c.first_name} {c.last_name}".strip()

        # Format Notice Period
        if exp.notice_period_days == 0:
            notice_str = "Immediate Joiner"
        else:
            notice_str = f"{exp.notice_period_days} Days Notice"

        # Subject Line
        subject = f"Application: {job_title} - {candidate_name} ({exp.total_years} Yrs Exp | {notice_str})"

        # Body Generation
        salutation = f"Hi hiring team{f' at {company}' if company else ''},"

        # Format notice details: if JD asks for immediate and candidate has notice, explain flexibility
        notice_detail = ""
        if "immediate" in job_description.lower():
            if exp.notice_period_days <= 15:
                notice_detail = "I am serving my notice period and can join immediately / within 15 days."
            else:
                notice_detail = f"My official notice period is {exp.notice_period_days} days, negotiable for early release."
        else:
            notice_detail = f"My notice period is {notice_str}."

        if job_description.strip():
            # Tailored template matching JD
            body = f"""{salutation}

I came across your job opening for the position of {job_title} and would like to formally express my interest.

With over {exp.total_years} years of professional experience as a {exp.current_job_title}, I have extensive hands-on expertise building scalable solutions.

Key Profile Highlights:
• Current Role: {exp.current_job_title} at {exp.current_company or 'Tech Corp'}
• Total Experience: {exp.total_years} years
• Current Location: {c.current_location or 'India'}
• Notice Period: {notice_detail}
• Current CTC: {exp.current_ctc_lakhs} LPA | Expected CTC: {exp.expected_ctc_lakhs} LPA

I have attached my updated resume for your kind review. I look forward to the opportunity to discuss how my skill set aligns with your team's goals.

Best regards,
{candidate_name}
Phone: {c.phone_country_code} {c.phone}
Email: {c.email}
LinkedIn: {c.linkedin_profile or ''}
"""
        else:
            # Clean fallback cold application template
            body = f"""{salutation}

I am writing to express my enthusiastic interest in joining your team as a {job_title}.

I bring {exp.total_years} years of software development experience specializing as a {exp.current_job_title}. 

Brief Overview:
• Total Experience: {exp.total_years} years
• Primary Expertise: {exp.current_job_title}
• Notice Period: {notice_detail}
• Location: {c.current_location or 'India'}

Please find my updated resume attached to this email. I would welcome the chance to connect for a brief introductory call.

Thank you for your time and consideration.

Warm regards,
{candidate_name}
Phone: {c.phone_country_code} {c.phone}
Email: {c.email}
LinkedIn: {c.linkedin_profile or ''}
"""

        return {"subject": subject, "body": body.strip()}

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

        pdf_path = resume_path or Path(self.profile.resume_path)

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
