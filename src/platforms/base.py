from abc import ABC, abstractmethod
from typing import Any, Dict, List
from playwright.sync_api import Page
from src.config import ProfileConfig, PlatformConfig, SafetyConfig
from src.database import DatabaseTracker

class BasePlatform(ABC):
    """Abstract base class for platform automators (Naukri, LinkedIn)."""

    def __init__(
        self,
        page: Page,
        profile: ProfileConfig,
        platform_config: PlatformConfig,
        safety_config: SafetyConfig,
        tracker: DatabaseTracker,
    ):
        self.page = page
        self.profile = profile
        self.platform_config = platform_config
        self.safety = safety_config
        self.tracker = tracker

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Name of the platform, e.g. 'naukri' or 'linkedin'."""
        pass

    @abstractmethod
    def is_logged_in(self) -> bool:
        """Checks if current session is logged in."""
        pass

    @abstractmethod
    def search_and_apply(self, keyword: str, location: str) -> Dict[str, int]:
        """Runs search and processes job applications for given keyword and location."""
        pass
