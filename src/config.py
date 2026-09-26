from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import yaml
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"

class CandidateInfo(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    phone_country_code: str = "+91"
    linkedin_profile: Optional[str] = None
    github_profile: Optional[str] = None
    portfolio_url: Optional[str] = None
    current_location: str = ""

class ExperienceInfo(BaseModel):
    total_years: float = 0.0
    relevant_years: float = 0.0
    current_job_title: str = ""
    current_company: str = ""
    notice_period_days: int = 30
    current_ctc_lakhs: float = 0.0
    expected_ctc_lakhs: float = 0.0

class WorkAuthorization(BaseModel):
    authorized_in_india: bool = True
    requires_visa_sponsorship: bool = False
    willing_to_relocate: bool = True

class ResumeConfig(BaseModel):
    directory: str = "data/resumes"
    auto_date_freshness: bool = True
    date_offset_days: int = 1
    base_name: str = "Rajesh_Saindane_DevOps_SRE_Resume"
    fallback_path: str = "data/resume.pdf"

class ProfileConfig(BaseModel):
    candidate: CandidateInfo
    experience: ExperienceInfo
    work_authorization: WorkAuthorization = Field(default_factory=WorkAuthorization)
    screening_answers: Dict[str, str] = Field(default_factory=dict)
    resume: ResumeConfig = Field(default_factory=ResumeConfig)
    resume_path: str = "data/resume.pdf"

class SearchCriteria(BaseModel):
    keywords: List[str] = Field(default_factory=lambda: ["Python Developer"])
    locations: List[str] = Field(default_factory=lambda: ["Bengaluru", "Remote"])
    experience_min_years: int = 0
    experience_max_years: int = 5
    work_modes: List[str] = Field(default_factory=lambda: ["Remote", "Hybrid"])

class PlatformConfig(BaseModel):
    enabled: bool = True
    daily_limit: int = 25
    auto_apply: bool = True
    easy_apply_only: bool = True
    skip_already_applied: bool = True

class SafetyConfig(BaseModel):
    min_delay_seconds: int = 3
    max_delay_seconds: int = 7
    headless: bool = False
    take_screenshots_on_apply: bool = True

class AppSearchConfig(BaseModel):
    search: SearchCriteria
    platforms: Dict[str, PlatformConfig]
    safety: SafetyConfig

def load_profile(path: Optional[Any] = None) -> ProfileConfig:
    """Loads and validates candidate profile from YAML."""
    file_path = Path(path).resolve() if path else (CONFIG_DIR / "profile.yaml")
    if not file_path.exists():
        raise FileNotFoundError(f"Profile config not found at: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return ProfileConfig(**data)

def load_search_config(path: Optional[Any] = None) -> AppSearchConfig:
    """Loads and validates job search configuration from YAML."""
    file_path = Path(path).resolve() if path else (CONFIG_DIR / "search_config.yaml")
    if not file_path.exists():
        raise FileNotFoundError(f"Search config not found at: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return AppSearchConfig(**data)

def load_safety_config(path: Optional[Any] = None) -> SafetyConfig:
    """Loads safety configuration from search_config.yaml or returns default."""
    try:
        search_cfg = load_search_config(path)
        return search_cfg.safety
    except Exception:
        return SafetyConfig()

