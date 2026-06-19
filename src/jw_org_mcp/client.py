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
    WOLReferenceResponse,
)
from .parser import ArticleParser, QueryParser, SearchResponseParser, WOLParser

logger = logging.getLogger(__name__)


class JWOrgClient:
    """Client for interacting with JW.Org APIs."""

    # Mapping from MCP language codes to WOL language and library codes
    WOL_LANG_MAP = {
        "E": {"code": "en", "lib": "lp-e"},
        "T": {"code": "pt", "lib": "lp-t"},
        "S": {"code": "es", "lib": "lp-s"},
    }

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

    async def get_wol_reference(
        self,
        query: str,
        start_paragraph: int | None = None,
        end_paragraph: int | None = None,
        language: str | None = None,
    ) -> tuple[WOLReferenceResponse, ResponseMetadata]:
        """Fetch specific paragraphs from publication reference(s) on WOL.

        Supports semicolon-separated multiple references.
        Supports page ranges (p. 18, pp. 17-18) and paragraph ranges (§ 5, §§ 4-6).

        Args:
            query: Publication reference(s) (e.g., "w13 15/10 p. 27", "it-2 pp. 1041-1043")
            start_paragraph: Starting paragraph number (optional if provided in query)
            end_paragraph: Ending paragraph number (optional if provided in query)
            language: Language code (default: E for English)

        Returns:
            Tuple of (WOLReferenceResponse, ResponseMetadata)

        Raises:
            ContentRetrievalError: If content retrieval fails
        """
        lang_code = language or settings.default_language
        wol_info = self.WOL_LANG_MAP.get(lang_code, self.WOL_LANG_MAP["E"])

        # Support semicolon-separated queries
        sub_queries = [q.strip() for q in query.split(";") if q.strip()]

        all_combined_paragraphs = []
        final_source_urls = []
        all_pages_found = set()

        for sub_query in sub_queries:
            # Parse sub_query for page and paragraph ranges
            # Examples:
            # w23.08 p. 18
            # it-2 pp. 1041-1043
            # it-2 p. 1044 §§ 3-4

            s_page, e_page = None, None
            # Match p. 123 or pp. 123-125
            page_match = re.search(r'\bpp?\.?\s*(\d+)(?:\s*[-–]\s*(\d+))?', sub_query)
            if page_match:
                s_page = int(page_match.group(1))
                if page_match.group(2):
                    e_page = int(page_match.group(2))

            s_para, e_para = start_paragraph, end_paragraph
            # Match § 5 or §§ 4-6
            para_match = re.search(r'§§?\s*(\d+)(?:\s*[-–]\s*(\d+))?', sub_query)
            if para_match:
                s_para = int(para_match.group(1))
                if para_match.group(2):
                    e_para = int(para_match.group(2))

            # Check cache
            cache_key = f"wol_ref:{sub_query}:{s_para}:{e_para}:{lang_code}"
            if settings.enable_cache:
                cached = self._cache.get(cache_key)
                if cached is not None:
                    logger.info(f"Cache hit for WOL reference: {sub_query}")
                    content, metadata = cached
                    all_combined_paragraphs.extend(content.paragraphs)
                    final_source_urls.append(content.source_url)
                    all_pages_found.update(content.pages)
                    continue

            try:
                base_url = f"https://wol.jw.org/{wol_info['code']}/wol/l/r1/{wol_info['lib']}"

                # Use cleaned query for search if it contains paragraph markers
                search_query = sub_query
                if para_match:
                    search_query = WOLParser.clean_query(sub_query)

                logger.info(f"Fetching WOL reference: {base_url} (query={search_query})")
                client = await self._get_http_client()
                response = await client.get(base_url, params={"q": search_query})
                response.raise_for_status()

                html = response.text
                final_url = str(response.url)

                # Handle lookup page
                if WOLParser.is_lookup_page(html):
                    links = WOLParser.extract_lookup_links(html)
                    if not links:
                        raise ContentRetrievalError(f"WOL search returned no results for: {sub_query}")

                    # If it's a reference book (it book) and we have a page range,
                    # we might need to follow multiple links if they fall within the range.
                    # For now, let's follow the first one as a baseline,
                    # but if we find "it-1" or "it-2" in query, we might want to be more inclusive.
                    article_paths = [links[0]["url"]]

                    # Heuristic for it-books: collect articles that might be relevant
                    if "it-" in sub_query.lower() and len(links) > 1:
                        # Follow up to top 3 if they seem relevant (too complex to perfectly match page ranges in link text)
                        article_paths = [l["url"] for l in links[:3]]

                    sub_all_paragraphs = []
                    for path in article_paths:
                        f_url = f"https://wol.jw.org{path}"
                        logger.info(f"Following lookup link: {f_url}")
                        resp = await client.get(f_url)
                        resp.raise_for_status()
                        sub_all_paragraphs.extend(WOLParser.parse_paragraphs(resp.text))
                        final_source_urls.append(f_url)
                        all_pages_found.update(WOLParser.extract_page_markers(resp.text))

                    requested_paragraphs = WOLParser.locate_paragraphs(
                        sub_all_paragraphs, s_para, e_para, s_page, e_page
                    )
                else:
                    # Direct article
                    all_paragraphs = WOLParser.parse_paragraphs(html)
                    if not all_paragraphs:
                        raise ContentRetrievalError(f"No paragraphs found in article: {final_url}")

                    requested_paragraphs = WOLParser.locate_paragraphs(
                        all_paragraphs, s_para, e_para, s_page, e_page
                    )
                    final_source_urls.append(final_url)
                    all_pages_found.update(WOLParser.extract_page_markers(html))

                all_combined_paragraphs.extend(requested_paragraphs)

                # Cache individual sub-query result
                if settings.enable_cache:
                    individual_content = WOLReferenceResponse(
                        query=sub_query,
                        paragraphs=requested_paragraphs,
                        total_paragraphs_in_article=len(requested_paragraphs), # Not perfectly accurate but works for cache
                        pages=sorted(list(all_pages_found)),
                        source_url=final_url,
                    )
                    self._cache.set(cache_key, value=(individual_content, ResponseMetadata(
                        source_domain="wol.jw.org",
                        source_url=final_url,
                        timestamp=datetime.now(UTC),
                        query_params={"query": sub_query},
                        cache_hit=False,
                    )))

            except httpx.HTTPError as e:
                logger.error(f"HTTP error fetching WOL reference '{sub_query}': {e}")
                # Don't fail the whole thing if one sub-query fails?
                # For now, let's raise if it's the only one, or just log.
                if len(sub_queries) == 1:
                    raise ContentRetrievalError(f"Failed to fetch WOL reference: {e}") from e
            except Exception as e:
                logger.error(f"Unexpected error fetching WOL reference '{sub_query}': {e}")
                if len(sub_queries) == 1:
                    raise

        if not all_combined_paragraphs:
            raise ContentRetrievalError(f"No paragraphs found for query: {query}")

        content = WOLReferenceResponse(
            query=query,
            paragraphs=all_combined_paragraphs,
            total_paragraphs_in_article=len(all_combined_paragraphs),
            pages=sorted(list(all_pages_found)),
            source_url="; ".join(list(set(final_source_urls))),
        )

        metadata = ResponseMetadata(
            source_domain="wol.jw.org",
            source_url=final_source_urls[0] if final_source_urls else "",
            timestamp=datetime.now(UTC),
            query_params={
                "query": query,
                "language": lang_code,
            },
            cache_hit=False,
        )

        return content, metadata

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
