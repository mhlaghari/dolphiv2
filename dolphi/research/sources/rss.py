from __future__ import annotations

import logging
import urllib.request
import xml.etree.ElementTree as ET

from .base import ResearchDocument

logger = logging.getLogger(__name__)


class RSSResearchSource:
    name = "rss"

    def __init__(self, feed_urls: list[str], timeout: int = 10):
        self._feed_urls = feed_urls
        self._timeout = timeout

    def fetch(self, query: str, limit: int = 10) -> list[ResearchDocument]:
        terms = {term for term in query.lower().split() if len(term) > 2}
        documents: list[ResearchDocument] = []
        for feed_url in self._feed_urls:
            try:
                with urllib.request.urlopen(feed_url, timeout=self._timeout) as response:
                    root = ET.fromstring(response.read())
            except Exception as exc:
                logger.warning("RSS feed %s failed: %s", feed_url, exc)
                continue

            for item in root.findall(".//item"):
                title = item.findtext("title", default="")
                description = item.findtext("description", default="")
                link = item.findtext("link", default=feed_url)
                published = item.findtext("pubDate", default="")
                text = f"{title} {description}".lower()
                if terms and not any(term in text for term in terms):
                    continue
                documents.append(
                    ResearchDocument(
                        title=title,
                        snippet=description,
                        source=self.name,
                        url=link,
                        published_at=published,
                        query=query,
                    )
                )
                if len(documents) >= limit:
                    return documents
        return documents
