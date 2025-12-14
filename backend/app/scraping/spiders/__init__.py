"""
Scrapy spiders for web crawling.

This package contains spider implementations:
- TenantAwareSpider: Base class for tenant-isolated scraping
- GenericSpider: Generic website crawler
"""

from app.scraping.spiders.base import TenantAwareSpider
from app.scraping.spiders.generic import GenericSpider

__all__ = [
    "TenantAwareSpider",
    "GenericSpider",
]
