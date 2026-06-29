"""
Platform scraper registry.
Maps platform enum values to scraper classes for dispatch.
"""
import logging
from typing import Dict, Optional, Type

from app.services.scrapers.base import AbstractScraper

logger = logging.getLogger(__name__)

_scraper_registry: Dict[str, Type[AbstractScraper]] = {}


def register_scraper(platform: str):
    """Decorator to register a scraper class for a platform."""
    def wrapper(cls: Type[AbstractScraper]):
        _scraper_registry[platform] = cls
        return cls
    return wrapper


def get_scraper(platform: str, browser_manager) -> Optional[AbstractScraper]:
    """Factory: instantiate a scraper for the given platform, or None if unavailable."""
    cls = _scraper_registry.get(platform)
    if cls is None:
        return None
    return cls(browser_manager)


def available_platforms() -> list:
    return list(_scraper_registry.keys())


# Import scraper modules to trigger registration (lazy, handles missing Playwright)
try:
    from app.services.scrapers import weibo_scraper   # noqa: E402, F401
except Exception as e:
    logger.warning("Weibo scraper not available: %s", e)

try:
    from app.services.scrapers import zhihu_scraper   # noqa: E402, F401
except Exception as e:
    logger.warning("Zhihu scraper not available: %s", e)

try:
    from app.services.scrapers import xueqiu_scraper  # noqa: E402, F401
except Exception as e:
    logger.warning("Xueqiu scraper not available: %s", e)

try:
    from app.services.scrapers import wechat_scraper  # noqa: E402, F401
except Exception as e:
    logger.warning("WeChat scraper not available: %s", e)

try:
    from app.services.scrapers import eastmoney_scraper  # noqa: E402, F401
except Exception as e:
    logger.warning("EastMoney scraper not available: %s", e)
