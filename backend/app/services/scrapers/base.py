"""Abstract base class for all platform scrapers."""
from abc import ABC, abstractmethod
from typing import List, Dict, TYPE_CHECKING

from app.models.models import VStar

if TYPE_CHECKING:
    from app.services.browser_manager import BrowserManager


class AbstractScraper(ABC):
    """Each platform scraper must implement this interface."""

    def __init__(self, browser_manager: "BrowserManager"):
        self._bm = browser_manager

    @abstractmethod
    async def scrape(self, vstar: VStar, days_back: int = 30) -> List[Dict]:
        """
        Scrape articles for the given VStar within the time window.

        Returns a list of article dicts with keys:
            title, content, summary, url, platform, published_at, source_hash
        """
        ...

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform display name, e.g. '雪球'."""
        ...
