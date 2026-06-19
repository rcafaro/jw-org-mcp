"""JW.Org API client."""

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from .auth import AuthManager
from .cache import Cache
from .config import settings
from .exceptions import ContentRetrievalError, SearchError
from .models import (
    ArticleContent,
    PublicationIndex,
    ResponseMetadata,
    SearchResponse,
    VideoCaptions,
)
from .parser import ArticleParser, QueryParser, SearchResponseParser

logger = logging.getLogger(__name__)


class JWOrgClient:
    """Client for interacting with JW.Org APIs."""

    def __init__(self) -> None:
        """Initialize the client."""
        self._auth_manager = AuthManager()
        self._cache = Cache(ttl_seconds=settings.cache_ttl_seconds)
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=settings.request_timeout,
                limits=httpx.Limits(
                    max_connections=settings.connection_pool_size,
                    max_keepalive_connections=settings.connection_pool_size,
                ),
                follow_redirects=True,
            )
        return self._http_client

    async def search(
        self,
        query: str,
        filter_type: str = "all",
        language: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[SearchResponse, ResponseMetadata]:
        """Search JW.Org content.

        Args:
            query: Search query
            filter_type: Content filter (all, publications, videos, audio, bible, indexes)
            language: Language code (default: E for English)
            limit: Number of results (not directly supported by API)
            offset: Result offset for pagination

        Returns:
            Tuple of (SearchResponse, ResponseMetadata)

        Raises:
            SearchError: If search fails
        """
        # Resolve language: explicit arg, env var, or fallback to English
        lang = language or settings.default_language

        # Parse query to extract meaningful search terms
        search_terms = QueryParser.extract_search_terms(query)

        # Check cache
        cache_key_parts = (search_terms, filter_type, lang, offset)
        if settings.enable_cache:
            cached = self._cache.get(*cache_key_parts)
            if cached is not None:
                logger.info(f"Cache hit for search: {search_terms}")
                response, metadata = cached
                metadata.cache_hit = True
                return response, metadata

        try:
            # Get CDN and auth
            cdn_info = await self._auth_manager.discover_cdn()
            headers = await self._auth_manager.get_authenticated_headers()

            # Build search URL
            search_url = (
                f"{cdn_info.base_url}/apis/search/results/"
                f"{lang}/{filter_type}?q={search_terms}"
            )

            if offset > 0:
                search_url += f"&offset={offset}"

            logger.info(f"Searching: {search_url}")

            # Make request
            client = await self._get_http_client()
            response = await client.get(search_url, headers=headers)
            response.raise_for_status()

            data = response.json()

            # Parse results
            results = SearchResponseParser.parse_search_results(
                data, search_terms, filter_type
            )

            # Get total count
            insight = data.get("insight", {})
            total_data = insight.get("total", {})
            total = total_data.get("value", len(results))

            # Build response
            search_response = SearchResponse(
                results=results[:limit] if limit > 0 else results,
                total=total,
                page=insight.get("page", 1),
                filter=filter_type,
                query=search_terms,
            )

            metadata = ResponseMetadata(
                source_domain="jw-cdn.org",
                source_url=search_url,
                timestamp=datetime.now(UTC),
                query_params={
                    "query": search_terms,
                    "filter": filter_type,
                    "language": lang,
                    "offset": offset,
                },
                cache_hit=False,
            )

            # Cache result
            if settings.enable_cache:
                self._cache.set(*cache_key_parts, value=(search_response, metadata))

            return search_response, metadata

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during search: {e}")
            raise SearchError(f"Search failed: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error during search: {e}")
            raise SearchError(f"Unexpected error during search: {e}") from e

    async def get_article(
        self, url: str
    ) -> tuple[ArticleContent | PublicationIndex, ResponseMetadata]:
        """Get article content from wol.jw.org.

        If the URL points to a publication index (table of contents) rather
        than a specific article, returns a PublicationIndex with links to
        individual articles.

        Args:
            url: Article URL or publication finder URL

        Returns:
            Tuple of (ArticleContent or PublicationIndex, ResponseMetadata)

        Raises:
            ContentRetrievalError: If content retrieval fails
        """
        # Check cache
        if settings.enable_cache:
            cached = self._cache.get(url, "article")
            if cached is not None:
                logger.info(f"Cache hit for article: {url}")
                content, metadata = cached
                metadata.cache_hit = True
                return content, metadata

        try:
            logger.info(f"Fetching article: {url}")

            client = await self._get_http_client()
            response = await client.get(url)
            response.raise_for_status()

            # Parse article
            article = ArticleParser.parse_article(response.text, url)

            metadata = ResponseMetadata(
                source_domain="wol.jw.org",
                source_url=url,
                timestamp=datetime.now(UTC),
                query_params={"url": url},
                cache_hit=False,
            )

            # Cache result
            if settings.enable_cache:
                self._cache.set(url, "article", value=(article, metadata))

            return article, metadata

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching article: {e}")
            raise ContentRetrievalError(f"Failed to fetch article: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error fetching article: {e}")
            raise ContentRetrievalError(
                f"Unexpected error fetching article: {e}"
            ) from e

    def _extract_video_id(self, video_id_or_url: str) -> str:
        """Extract video ID from JW.Org URL or return as-is.

        Args:
            video_id_or_url: Video ID or JW.Org URL

        Returns:
            Extracted video ID
        """
        if not video_id_or_url.startswith("http"):
            return video_id_or_url

        try:
            parsed = urlparse(video_id_or_url)
            query_params = parse_qs(parsed.query)

            # Check for 'lank' parameter
            if "lank" in query_params:
                return query_params["lank"][0]

            # Check for 'docid' parameter
            if "docid" in query_params:
                return query_params["docid"][0]

            # Check pathname for pub- pattern
            match = re.search(r"/(pub-[^/]+)", parsed.path)
            if match:
                return match.group(1)

            # Check fragment for pub- pattern
            if parsed.fragment:
                match = re.search(r"(pub-[^/]+)", parsed.fragment)
                if match:
                    return match.group(1)

            return video_id_or_url
        except Exception as e:
            logger.warning(f"Failed to parse video URL: {e}")
            return video_id_or_url

    async def get_video_captions(
        self, video_id: str, language: str | None = None
    ) -> tuple[VideoCaptions, ResponseMetadata]:
        """Get video captions and metadata.

        Args:
            video_id: Video ID or JW.Org URL
            language: Language code (default: E for English)

        Returns:
            Tuple of (VideoCaptions, ResponseMetadata)

        Raises:
            ContentRetrievalError: If content retrieval fails
        """
        lang = language or settings.default_language
        extracted_id = self._extract_video_id(video_id)

        # Check cache
        cache_key = f"captions:{extracted_id}:{lang}"
        if settings.enable_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.info(f"Cache hit for video captions: {extracted_id}")
                content, metadata = cached
                metadata.cache_hit = True
                return content, metadata

        try:
            # Step 1: Get media metadata from CDN
            cdn_info = await self._auth_manager.discover_cdn()
            # The API uses language codes like E, S, etc.
            media_url = f"{cdn_info.base_url}/apis/mediator/v1/media-items/{lang}/{extracted_id}?clientType=www"

            logger.info(f"Fetching video metadata: {media_url}")
            client = await self._get_http_client()
            response = await client.get(media_url)
            response.raise_for_status()
            media_data = response.json()

            if not media_data.get("media") or not media_data["media"][0].get("files"):
                raise ContentRetrievalError(f"No media found for video ID: {extracted_id}")

            media = media_data["media"][0]
            title = media.get("title", "Unknown Title")
            thumbnail = media.get("images", {}).get("wss", {}).get("sm", "")

            # Look for subtitles
            subtitles_url = None
            for file in media.get("files", []):
                if file.get("subtitles") and file["subtitles"].get("url"):
                    subtitles_url = file["subtitles"]["url"]
                    break

            if not subtitles_url:
                raise ContentRetrievalError(f"No subtitles found for video ID: {extracted_id}")

            # Step 2: Fetch subtitles
            logger.info(f"Fetching subtitles: {subtitles_url}")
            sub_response = await client.get(subtitles_url)
            sub_response.raise_for_status()
            subtitles = sub_response.text

            captions = VideoCaptions(
                title=title,
                thumbnail=thumbnail,
                subtitles=subtitles,
                source_url=subtitles_url,
            )

            metadata = ResponseMetadata(
                source_domain="jw-cdn.org",
                source_url=media_url,
                timestamp=datetime.now(UTC),
                query_params={"video_id": video_id, "language": lang},
                cache_hit=False,
            )

            # Cache result
            if settings.enable_cache:
                self._cache.set(cache_key, value=(captions, metadata))

            return captions, metadata

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching video captions: {e}")
            raise ContentRetrievalError(f"Failed to fetch video captions: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error fetching video captions: {e}")
            raise ContentRetrievalError(f"Unexpected error fetching video captions: {e}") from e

    async def get_scripture(
        self, reference: str, translation: str = "nwtsty", language: str | None = None
    ) -> tuple[dict[str, Any], ResponseMetadata]:
        """Get scripture content.

        Args:
            reference: Scripture reference (e.g., "John 3:16")
            translation: Bible translation code
            language: Language code (E=English, P=Portuguese, etc).
                      Falls back to settings.default_language if not provided.

        Returns:
            Tuple of (scripture data, ResponseMetadata)

        Raises:
            ContentRetrievalError: If content retrieval fails
        """
        # Search for the scripture reference
        search_response, _ = await self.search(
            reference, filter_type="bible", language=language or settings.default_language
        )

        if not search_response.results:
            raise ContentRetrievalError(f"Scripture not found: {reference}")

        # Get the first result
        result = search_response.results[0]

        scripture_data = {
            "text": result.snippet,
            "reference": result.title,
            "source_url": result.url,
        }

        metadata = ResponseMetadata(
            source_domain="jw.org",
            source_url=result.url,
            timestamp=datetime.now(UTC),
            query_params={"reference": reference, "translation": translation},
            cache_hit=False,
        )

        return scripture_data, metadata

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Cache statistics
        """
        return self._cache.get_stats()

    def clear_cache(self) -> None:
        """Clear the cache."""
        self._cache.clear()

    async def close(self) -> None:
        """Close all connections."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        await self._auth_manager.close()
