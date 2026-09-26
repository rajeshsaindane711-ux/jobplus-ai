import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from src.config import ProfileConfig
from src.utils.logger import logger

class ResumeManager:
    """Manages master resumes, monthly version detection, and dynamic date freshness stamping."""

    def __init__(self, profile: ProfileConfig):
        self.profile = profile
        self.resume_cfg = profile.resume
        self.resumes_dir = Path(self.resume_cfg.directory)
        self.resumes_dir.mkdir(parents=True, exist_ok=True)
        self.stamped_dir = self.resumes_dir / "stamped"
        self.stamped_dir.mkdir(parents=True, exist_ok=True)

    def find_master_resume(self) -> Optional[Path]:
        """
        Locates the latest master resume PDF.
        Supports Option 1: auto-detects newest monthly version dropped into data/resumes/.
        """
        # Look in data/resumes/ excluding stamped subfolder
        pdf_candidates = [
            f for f in self.resumes_dir.glob("*.pdf")
            if f.is_file() and "stamped" not in str(f)
        ]

        if pdf_candidates:
            # Sort by modification time (most recent first)
            pdf_candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            chosen = pdf_candidates[0]
            logger.info(f"Using master resume from resumes folder: {chosen.name}")
            return chosen

        # Fallback to legacy path if specified
        fallback = Path(self.resume_cfg.fallback_path)
        if fallback.exists():
            return fallback

        legacy_path = Path(self.profile.resume_path)
        if legacy_path.exists():
            return legacy_path

        return None

    def get_freshened_resume(self, date_offset_days: Optional[int] = None) -> Optional[Path]:
        """
        Generates or returns an application-ready resume.
        Supports Option 2: stamps filename with yesterday's (or offset) date (DDMMYYYY).
        Example: Rajesh_Saindane_DevOps_SRE_Resume_24092026.pdf
        """
        master_file = self.find_master_resume()
        if not master_file or not master_file.exists():
            logger.warning("No master resume PDF found to freshen.")
            return None

        if not self.resume_cfg.auto_date_freshness:
            return master_file

        offset = date_offset_days if date_offset_days is not None else self.resume_cfg.date_offset_days
        target_date = datetime.now() - timedelta(days=offset)
        date_str = target_date.strftime("%d%m%Y") # Format: DDMMYYYY, e.g. 24092026

        base_name = self.resume_cfg.base_name or master_file.stem
        fresh_filename = f"{base_name}_{date_str}.pdf"
        fresh_file_path = self.stamped_dir / fresh_filename

        try:
            # Copy master resume to the stamped filename
            shutil.copy2(master_file, fresh_file_path)
            logger.info(f"[Resume Freshness] Created date-stamped resume: {fresh_filename} (Date: {date_str})")
            return fresh_file_path
        except Exception as e:
            logger.warning(f"Failed to create fresh date-stamped copy: {e}. Using master.")
            return master_file

    def prepare_fresh_resume(self, date_offset_days: Optional[int] = None) -> str:
        """Returns string path to the application-ready resume."""
        res = self.get_freshened_resume(date_offset_days)
        if res:
            return str(res)
        return str(Path(self.profile.resume_path).resolve())
