"""
Base spider class with tenant awareness.

Provides common functionality for all Knowledge Mapper spiders:
- Tenant context management
- Job configuration loading
- Progress tracking
- Domain restrictions
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from urllib.parse import urlparse
from uuid import UUID

import scrapy
from scrapy.http import Response

from app.scraping.items import ScrapedPageItem

logger = logging.getLogger(__name__)


class TenantAwareSpider(scrapy.Spider):
    """
    Base spider class with tenant isolation.

    All Knowledge Mapper spiders should inherit from this class
    to ensure proper tenant context and configuration handling.
    """

    name = "tenant_aware"

    # These will be set from job configuration
    job_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    start_url: Optional[str] = None
    allowed_domains: list[str] = []
    url_patterns: list[str] = []
    excluded_patterns: list[str] = []
    crawl_depth: int = 2
    max_pages: int = 100
    use_llm_extraction: bool = True

    # Progress tracking
    pages_crawled: int = 0
    progress_callback: Optional[Callable[[int, int, int], None]] = None

    def __init__(
        self,
        job_id: str = None,
        tenant_id: str = None,
        start_url: str = None,
        allowed_domains: list[str] = None,
        url_patterns: list[str] = None,
        excluded_patterns: list[str] = None,
        crawl_depth: int = 2,
        max_pages: int = 100,
        use_llm_extraction: bool = True,
        progress_callback: Callable[[int, int, int], None] = None,
        *args,
        **kwargs,
    ):
        """
        Initialize spider with job configuration.

        Args:
            job_id: UUID of the scraping job
            tenant_id: UUID of the tenant
            start_url: URL to begin crawling from
            allowed_domains: List of domains to stay within
            url_patterns: Regex patterns for URLs to include
            excluded_patterns: Regex patterns for URLs to exclude
            crawl_depth: Maximum link depth to follow
            max_pages: Maximum pages to scrape
            use_llm_extraction: Whether to use LLM for extraction
            progress_callback: Callback for progress updates
        """
        super().__init__(*args, **kwargs)

        self.job_id = UUID(job_id) if job_id else None
        self.tenant_id = UUID(tenant_id) if tenant_id else None
        self.start_url = start_url
        self.allowed_domains = allowed_domains or []
        self.url_patterns = url_patterns or []
        self.excluded_patterns = excluded_patterns or []
        self.crawl_depth = crawl_depth
        self.max_pages = max_pages
        self.use_llm_extraction = use_llm_extraction
        self.progress_callback = progress_callback

        # Compile patterns
        self._url_patterns = [re.compile(p) for p in self.url_patterns]
        self._excluded_patterns = [re.compile(p) for p in self.excluded_patterns]

        # Extract domain from start_url if not specified
        if not self.allowed_domains and self.start_url:
            parsed = urlparse(self.start_url)
            if parsed.netloc:
                self.allowed_domains = [parsed.netloc]

        logger.info(
            f"Spider initialized for job {job_id}",
            extra={
                "job_id": str(job_id),
                "tenant_id": str(tenant_id),
                "start_url": start_url,
                "allowed_domains": self.allowed_domains,
                "crawl_depth": crawl_depth,
                "max_pages": max_pages,
            },
        )

    @property
    def start_urls(self) -> list[str]:
        """Return starting URLs."""
        if self.start_url:
            return [self.start_url]
        return []

    def parse(self, response: Response, **kwargs) -> Any:
        """
        Default parse method for processing responses.

        Override in subclasses for custom parsing logic.

        Args:
            response: HTTP response from Scrapy

        Yields:
            ScrapedPageItem or Request objects
        """
        # Check if we've hit the page limit
        if self.pages_crawled >= self.max_pages:
            logger.info(f"Reached max pages limit ({self.max_pages})")
            return

        # Extract page data
        item = self._extract_page_data(response)
        if item:
            yield item
            self.pages_crawled += 1

            # Update progress
            if self.progress_callback:
                self.progress_callback(self.pages_crawled, 0, 0)

        # Extract and follow links
        yield from self._follow_links(response)

    def _extract_page_data(self, response: Response) -> Optional[ScrapedPageItem]:
        """
        Extract page data from response.

        Args:
            response: HTTP response

        Returns:
            ScrapedPageItem or None
        """
        try:
            item = ScrapedPageItem()

            # Identifiers
            item["job_id"] = str(self.job_id)
            item["tenant_id"] = str(self.tenant_id)
            item["url"] = response.url

            # Extract canonical URL
            canonical = response.xpath("//link[@rel='canonical']/@href").get()
            item["canonical_url"] = canonical or response.url

            # Content
            item["html_content"] = response.text
            item["text_content"] = ""  # Will be extracted by pipeline

            # Metadata
            item["title"] = response.xpath("//title/text()").get()
            item["meta_description"] = response.xpath(
                "//meta[@name='description']/@content"
            ).get()
            item["meta_keywords"] = response.xpath(
                "//meta[@name='keywords']/@content"
            ).get()

            # HTTP info
            item["http_status"] = response.status
            item["content_type"] = response.headers.get(
                "Content-Type", b"text/html"
            ).decode("utf-8", errors="ignore")
            item["response_headers"] = dict(response.headers.to_unicode_dict())

            # Crawl info
            item["crawled_at"] = datetime.now(timezone.utc)
            item["depth"] = response.meta.get("depth", 0)

            logger.debug(
                f"Extracted page data: {response.url}",
                extra={
                    "url": response.url,
                    "status": response.status,
                    "depth": item["depth"],
                },
            )

            return item

        except Exception as e:
            logger.error(
                f"Failed to extract page data from {response.url}: {e}",
                exc_info=True,
            )
            return None

    def _follow_links(self, response: Response):
        """
        Extract and follow links from the page.

        Args:
            response: HTTP response

        Yields:
            Request objects for discovered links
        """
        current_depth = response.meta.get("depth", 0)

        # Don't follow links if at max depth
        if current_depth >= self.crawl_depth:
            return

        # Extract all links
        links = response.xpath("//a/@href").getall()

        for link in links:
            # Build absolute URL
            url = response.urljoin(link)

            # Check if URL should be followed
            if self._should_follow_url(url):
                yield response.follow(
                    link,
                    callback=self.parse,
                    meta={"depth": current_depth + 1},
                    errback=self._handle_error,
                )

    def _should_follow_url(self, url: str) -> bool:
        """
        Check if a URL should be followed.

        Args:
            url: URL to check

        Returns:
            True if URL should be followed
        """
        # Parse URL
        parsed = urlparse(url)

        # Check domain
        if self.allowed_domains:
            if parsed.netloc not in self.allowed_domains:
                return False

        # Check excluded patterns
        for pattern in self._excluded_patterns:
            if pattern.search(url):
                return False

        # Check include patterns (if specified)
        if self._url_patterns:
            matched = any(p.search(url) for p in self._url_patterns)
            if not matched:
                return False

        # Skip non-HTTP URLs
        if parsed.scheme not in ("http", "https"):
            return False

        # Skip common non-content URLs
        skip_extensions = {
            ".css", ".js", ".jpg", ".jpeg", ".png", ".gif", ".svg",
            ".ico", ".woff", ".woff2", ".ttf", ".eot", ".pdf",
            ".zip", ".tar", ".gz", ".mp3", ".mp4", ".avi", ".mov",
        }
        if any(parsed.path.lower().endswith(ext) for ext in skip_extensions):
            return False

        return True

    def _handle_error(self, failure):
        """Handle request failures."""
        logger.error(
            f"Request failed: {failure.request.url} - {failure.value}",
            extra={
                "url": failure.request.url,
                "error": str(failure.value),
                "job_id": str(self.job_id),
            },
        )
