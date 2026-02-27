"""
Web crawler for fetching and extracting content from URLs.

Supports single URL and limited-depth crawling with clean content extraction.
"""

import hashlib
import logging
import time
from typing import Dict, List, Optional, Set
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
import trafilatura
import validators
from bs4 import BeautifulSoup

from src.config import settings

logger = logging.getLogger(__name__)


class WebCrawler:
    """
    Web content crawler with clean text extraction.

    Supports single URL crawling and limited-depth link following.
    Uses trafilatura for high-quality content extraction.
    """

    def __init__(
        self,
        timeout: Optional[int] = None,
        max_size_mb: Optional[int] = None,
        user_agent: str = "Berengario/1.0 (Educational RAG System)",
        delay: Optional[float] = None,
    ):
        """
        Initialize the web crawler.

        Args:
            timeout: Request timeout in seconds (default from settings).
            max_size_mb: Maximum page size in megabytes (default from settings).
            user_agent: User agent string for requests.
            delay: Delay between requests in seconds (default from settings).
        """
        self.timeout = timeout if timeout is not None else settings.crawl_timeout
        max_size = (
            max_size_mb if max_size_mb is not None else settings.crawl_max_size_mb
        )
        self.max_size_bytes = max_size * 1024 * 1024
        self.user_agent = user_agent
        self.delay = delay if delay is not None else settings.crawl_delay

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

        logger.info(
            f"WebCrawler initialized (timeout={self.timeout}s, max_size={max_size}MB)"
        )

    def normalize_url(self, url: str) -> str:
        """
        Normalize URL for consistent deduplication.

        - Removes trailing slashes
        - Lowercases domain
        - Removes tracking parameters (utm_*)
        - Sorts query parameters
        - Removes fragments

        Args:
            url: URL to normalize.

        Returns:
            Normalized URL string.
        """
        try:
            parsed = urlparse(url)

            # Lowercase scheme and domain
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()

            # Remove trailing slash from path
            path = parsed.path.rstrip("/")

            # Filter out tracking parameters and sort
            if parsed.query:
                params = parse_qs(parsed.query, keep_blank_values=False)
                # Remove common tracking parameters
                tracking_params = {
                    k for k in params if k.startswith(("utm_", "ref_", "fbclid"))
                }
                for param in tracking_params:
                    del params[param]
                # Sort remaining parameters
                query = urlencode(sorted(params.items()), doseq=True) if params else ""
            else:
                query = ""

            # Remove fragment
            fragment = ""

            normalized = urlunparse((scheme, netloc, path, "", query, fragment))
            return normalized

        except Exception as e:
            logger.error(f"Error normalizing URL {url}: {e}")
            return url

    def get_url_hash(self, url: str) -> str:
        """
        Compute SHA-256 hash of normalized URL.

        Args:
            url: URL to hash.

        Returns:
            Hex string of URL hash.
        """
        normalized = self.normalize_url(url)
        return hashlib.sha256(normalized.encode()).hexdigest()

    def validate_url(self, url: str) -> bool:
        """
        Validate URL format.

        Args:
            url: URL to validate.

        Returns:
            True if valid, False otherwise.
        """
        if not url or not isinstance(url, str):
            return False

        # Use validators library
        result = validators.url(url)
        return result is True

    def fetch_html(self, url: str) -> Optional[str]:
        """
        Fetch HTML content from URL.

        Args:
            url: URL to fetch.

        Returns:
            HTML content as string, or None on error.

        Raises:
            requests.RequestException: On network errors.
        """
        try:
            logger.info(f"Fetching {url}")

            response = self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=True,
                stream=True,
            )

            # Check status
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                logger.warning(f"Non-HTML content type: {content_type}")

            # Check size
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > self.max_size_bytes:
                logger.error(f"Content too large: {content_length} bytes")
                return None

            # Read content with size limit
            content = b""
            for chunk in response.iter_content(chunk_size=8192):
                content += chunk
                if len(content) > self.max_size_bytes:
                    logger.error("Content exceeded size limit during download")
                    return None

            html = content.decode(response.encoding or "utf-8", errors="replace")
            logger.info(f"Successfully fetched {len(html)} characters from {url}")

            return html

        except requests.Timeout:
            logger.error(f"Timeout fetching {url}")
            raise
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}")
            raise

    def extract_content(self, html: str, url: str) -> Optional[str]:
        """
        Extract clean text content from HTML.

        Uses trafilatura for high-quality main content extraction,
        removing navigation, ads, footers, etc.

        Args:
            html: HTML content.
            url: Source URL (for context).

        Returns:
            Extracted text content, or None if extraction fails.
        """
        try:
            # Use trafilatura for content extraction
            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                favor_precision=False,
                favor_recall=True,
            )

            if text and text.strip():
                logger.info(f"Extracted {len(text)} characters from {url}")
                return text.strip()

            # Fallback to BeautifulSoup if trafilatura fails
            logger.warning(f"Trafilatura extraction failed for {url}, using fallback")
            soup = BeautifulSoup(html, "lxml")

            # Remove script, style, and navigation elements
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()

            # Get text
            text = soup.get_text(separator="\n", strip=True)

            if text and text.strip():
                logger.info(f"Fallback extracted {len(text)} characters from {url}")
                return text.strip()

            logger.error(f"No content extracted from {url}")
            return None

        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            return None

    def extract_links(self, html: str, base_url: str) -> Set[str]:
        """
        Extract all HTTP(S) links from HTML.

        Args:
            html: HTML content.
            base_url: Base URL for resolving relative links.

        Returns:
            Set of absolute URLs found in the page.
        """
        try:
            soup = BeautifulSoup(html, "lxml")
            links = set()

            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]

                # Resolve relative URLs
                absolute_url = urljoin(base_url, href)

                # Only include http/https URLs
                if absolute_url.startswith(("http://", "https://")):
                    # Only include URLs from same domain
                    base_domain = urlparse(base_url).netloc
                    link_domain = urlparse(absolute_url).netloc

                    if base_domain == link_domain:
                        links.add(absolute_url)

            logger.info(f"Extracted {len(links)} same-domain links from {base_url}")
            return links

        except Exception as e:
            logger.error(f"Error extracting links from {base_url}: {e}")
            return set()

    def crawl_url(
        self,
        url: str,
        crawl_depth: int = 1,
        max_pages: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        Crawl URL(s) with limited depth.

        Args:
            url: Starting URL to crawl.
            crawl_depth: Maximum depth to crawl (1 = single page, 2 = follow links once).
            max_pages: Maximum number of pages to crawl (default from settings).

        Returns:
            List of dicts with 'url', 'content', 'url_hash' keys.

        Raises:
            ValueError: If URL is invalid.
            requests.RequestException: On network errors.
        """
        # Validate URL
        if not self.validate_url(url):
            raise ValueError(f"Invalid URL: {url}")

        # Use settings default if max_pages not specified
        if max_pages is None:
            max_pages = settings.crawl_max_pages

        results = []
        visited = set()
        to_crawl = [(url, 0)]  # (url, current_depth)

        while to_crawl and len(results) < max_pages:
            current_url, depth = to_crawl.pop(0)

            # Skip if already visited
            normalized = self.normalize_url(current_url)
            if normalized in visited:
                continue

            visited.add(normalized)

            try:
                # Respect rate limiting
                if len(visited) > 1:
                    time.sleep(self.delay)

                # Fetch HTML
                html = self.fetch_html(current_url)
                if not html:
                    continue

                # Extract content
                content = self.extract_content(html, current_url)
                if not content:
                    continue

                # Store result
                results.append(
                    {
                        "url": current_url,
                        "normalized_url": normalized,
                        "url_hash": self.get_url_hash(current_url),
                        "content": content,
                        "depth": depth,
                    }
                )

                logger.info(f"Successfully crawled {current_url} (depth={depth})")

                # Extract links if we haven't reached max depth
                # depth + 1 < crawl_depth ensures:
                #   crawl_depth=1: only root page (no link following)
                #   crawl_depth=2: root page + 1 level of links
                if depth + 1 < crawl_depth:
                    links = self.extract_links(html, current_url)

                    # Add unvisited links to queue
                    for link in links:
                        link_normalized = self.normalize_url(link)
                        if link_normalized not in visited:
                            to_crawl.append((link, depth + 1))

            except requests.RequestException as e:
                logger.error(f"Failed to crawl {current_url}: {e}")
                # Continue with next URL
                continue
            except Exception as e:
                logger.error(f"Unexpected error crawling {current_url}: {e}")
                continue

        logger.info(
            f"Crawling complete: {len(results)} pages crawled, {len(visited)} URLs visited"
        )

        return results
