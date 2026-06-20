"""Content parsers for JW.Org responses."""

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from .exceptions import ParseError
from .models import (
    ArticleContent,
    PublicationIndex,
    PublicationIndexEntry,
    SearchResult,
    WOLParagraph,
)

logger = logging.getLogger(__name__)


class QueryParser:
    """Parses user queries to extract meaningful search terms."""

    # Common question patterns to remove
    QUESTION_PATTERNS = [
        r"^what\s+(does|do|is|are)\s+the\s+bible\s+say\s+about\s+",
        r"^what\s+does\s+.*?\s+say\s+about\s+",
        r"^how\s+(does|do|can|should)\s+",
        r"^why\s+(does|do|is|are)\s+",
        r"^when\s+(does|do|will|should)\s+",
        r"^where\s+(does|do|is|can)\s+",
        r"^who\s+(is|are|was|were)\s+",
        r"^tell\s+me\s+about\s+",
        r"^explain\s+",
        r"^find\s+information\s+about\s+",
    ]

    @classmethod
    def extract_search_terms(cls, query: str) -> str:
        """Extract meaningful search terms from a natural language query.

        Args:
            query: User's natural language query

        Returns:
            Extracted search terms
        """
        # Clean the query
        cleaned = query.strip().lower()

        # Remove question patterns
        for pattern in cls.QUESTION_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Remove trailing question marks and periods
        cleaned = cleaned.rstrip("?.!")

        # If we removed too much, return original
        if not cleaned or len(cleaned) < 3:
            return query.strip()

        return cleaned.strip()


class SearchResponseParser:
    """Parses search API responses."""

    @staticmethod
    def parse_search_results(
        data: dict[str, Any], query: str, filter_type: str
    ) -> list[SearchResult]:
        """Parse search results from API response.

        Args:
            data: Raw API response data
            query: Original search query
            filter_type: Filter type used

        Returns:
            List of SearchResult objects

        Raises:
            ParseError: If parsing fails
        """
        try:
            results = []
            raw_results = data.get("results", [])

            for item in raw_results:
                # Handle nested group structure (for 'all' filter)
                if item.get("type") == "group":
                    nested_results = item.get("results", [])
                    for nested_item in nested_results:
                        result = SearchResponseParser._parse_single_result(nested_item)
                        if result:
                            results.append(result)
                # Handle flat structure (for other filters)
                else:
                    result = SearchResponseParser._parse_single_result(item)
                    if result:
                        results.append(result)

            return results

        except Exception as e:
            logger.error(f"Error parsing search results: {e}")
            raise ParseError(f"Failed to parse search results: {e}") from e

    @staticmethod
    def _parse_single_result(item: dict[str, Any]) -> SearchResult | None:
        """Parse a single search result item.

        Args:
            item: Raw result item

        Returns:
            SearchResult object or None if invalid
        """
        try:
            # Extract basic fields
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            item_type = item.get("type", "item")
            subtype = item.get("subtype", "")

            # Clean HTML from snippet
            snippet = SearchResponseParser._clean_html(snippet)

            # Extract URL (prefer wol link)
            links = item.get("links", {})
            url = links.get("wol") or links.get("jw.org") or ""

            # Extract context and metadata
            context = item.get("context")
            rank = item.get("insight", {}).get("rank")

            # Try to extract publication and year from context
            publication = None
            year = None
            if context:
                year_match = re.search(r"\((\d{4})\)", context)
                if year_match:
                    year = int(year_match.group(1))
                    publication = context.replace(f"({year})", "").strip()
                else:
                    publication = context

            return SearchResult(
                title=title,
                snippet=snippet,
                url=url,
                type=item_type,
                subtype=subtype,
                context=context,
                publication=publication,
                year=year,
                rank=rank,
            )

        except Exception as e:
            logger.warning(f"Could not parse result item: {e}")
            return None

    @staticmethod
    def _clean_html(text: str) -> str:
        """Remove HTML tags from text.

        Args:
            text: Text with HTML tags

        Returns:
            Clean text
        """
        if not text:
            return ""

        # Use BeautifulSoup to extract text
        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(separator=" ", strip=True)


class ArticleParser:
    """Parses article content from wol.jw.org."""

    @staticmethod
    def parse_article(html: str, url: str) -> ArticleContent | PublicationIndex:
        """Parse article content from HTML.

        If the page is a publication index/table of contents (no article
        paragraphs but contains links to individual articles), returns a
        PublicationIndex instead.

        Args:
            html: Raw HTML content
            url: Source URL

        Returns:
            ArticleContent or PublicationIndex object

        Raises:
            ParseError: If parsing fails
        """
        try:
            soup = BeautifulSoup(html, "lxml")

            # Find article container
            article = soup.find("article", id="article")
            if not article:
                raise ParseError("Could not find article container in HTML")

            # Extract title
            title_elem = article.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else "Untitled"

            # Extract paragraphs
            paragraphs = []
            references = []

            # Find all paragraph elements with data-pid attribute
            para_elements = article.find_all("p", {"data-pid": True})

            for para in para_elements:
                # Skip if paragraph has class indicating it's not content
                class_attr = para.get("class")
                classes = class_attr if isinstance(class_attr, list) else []
                if any(cls in ["caption", "footnote", "boxTtl"] for cls in classes):
                    continue

                # Extract text, ignoring span highlights
                text = para.get_text(separator=" ", strip=True)
                if text:
                    paragraphs.append(text)

                # Extract scripture references
                scripture_refs = para.find_all("a", {"class": "b"})
                for ref in scripture_refs:
                    ref_text = ref.get_text(strip=True)
                    if ref_text:
                        references.append(ref_text)

            if paragraphs:
                return ArticleContent(
                    title=title,
                    paragraphs=paragraphs,
                    references=list(set(references)),  # Remove duplicates
                    source_url=url,
                )

            # No paragraphs found — try parsing as a publication index/TOC
            index = ArticleParser._try_parse_publication_index(soup, url)
            if index:
                return index

            raise ParseError("Could not extract any paragraphs from article")

        except ParseError:
            raise
        except Exception as e:
            logger.error(f"Error parsing article: {e}")
            raise ParseError(f"Failed to parse article: {e}") from e

    @staticmethod
    def _try_parse_publication_index(
        soup: BeautifulSoup, url: str
    ) -> PublicationIndex | None:
        """Try to parse the page as a publication index/table of contents.

        Detects pages that list links to individual articles (e.g., a magazine
        issue's table of contents).

        Args:
            soup: Parsed HTML
            url: Source URL

        Returns:
            PublicationIndex if article links are found, None otherwise
        """
        # Look for links to individual articles (/wol/d/ pattern)
        article_links = soup.find_all("a", href=re.compile(r"/wol/d/"))
        if not article_links:
            return None

        entries: list[PublicationIndexEntry] = []
        seen_urls: set[str] = set()

        for link in article_links:
            href_val = link.get("href", "")
            href = href_val if isinstance(href_val, str) else ""
            link_title = link.get_text(strip=True)

            if not href or not link_title:
                continue

            # Build full URL
            full_url = f"https://wol.jw.org{href}" if href.startswith("/") else href

            # Strip query parameters from the URL for deduplication and cleanliness
            clean_url = full_url.split("?")[0]

            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)

            entries.append(PublicationIndexEntry(title=link_title, url=clean_url))

        if not entries:
            return None

        # Get publication title from page heading
        h1 = soup.find("h1")
        pub_title = h1.get_text(strip=True) if h1 else "Publication Index"

        return PublicationIndex(
            title=pub_title,
            articles=entries,
            source_url=url,
        )


class WOLParser:
    """Parses content specifically from wol.jw.org with paragraph tracking."""

    @staticmethod
    def clean_query(query: str) -> str:
        """Remove paragraph/page details from query for better WOL searching.

        Examples:
            "cf p. 134 pars. 14,15" -> "cf p. 134"
            "w13 15/10 p. 27 § 1" -> "w13 15/10 p. 27"
        """
        original = query
        # Remove: "pars. 14,15", "par. 1", "parágrafo 1", "pars 14-15" etc.
        query = re.sub(
            r"\b(?:pars?\.?\s*|parágrafo[s]?\s*)[\d,\-–\s]+$", "", query
        ).strip()
        # Remove: "§ 1", "§§ 14-15" etc.
        query = re.sub(r"\s*§{1,2}\s*[\d,\-–\s]+$", "", query).strip()
        # Remove trailing punctuation (but preserve "p. 134")
        query = re.sub(r"[,;.\s]+$", "", query).strip()
        return query if query else original

    @staticmethod
    def is_lookup_page(html: str) -> bool:
        """Check if the HTML is a lookup/search results page."""
        return 'class="article lookup"' in html or "lookupResults" in html

    @staticmethod
    def extract_page_markers(html: str) -> list[int]:
        """Extract page numbers from HTML."""
        return [
            int(m)
            for m in re.findall(
                r'<span[^>]*id="page(\d+)"[^>]*class="pageNum"[^>]*></span>', html
            )
        ]

    @staticmethod
    def parse_paragraphs(html: str) -> list[WOLParagraph]:
        """Extract paragraphs with metadata from WOL HTML."""
        paragraphs: list[WOLParagraph] = []
        soup = BeautifulSoup(html, "lxml")

        # Define tags to look for in order
        content_tags = ["p", "span", "h1", "h2", "h3", "h4"]

        # --- Format A: bodyTxt ---
        body_div = soup.find("div", class_="bodyTxt")
        if body_div:
            current_page = None
            elements = body_div.find_all(content_tags)
            processed_elements = set()
            for elem in elements:
                if elem in processed_elements:
                    continue

                if elem.name == "span" and "pageNum" in elem.get("class", []):
                    try:
                        current_page = int(elem.get("id", "").replace("page", ""))
                    except (ValueError, TypeError):
                        pass
                    continue

                if elem.name not in ["p", "h1", "h2", "h3", "h4"]:
                    continue

                # Check for page markers inside BEFORE processing text
                inner_spans = elem.find_all("span", class_="pageNum")
                for span in inner_spans:
                    try:
                        current_page = int(span.get("id", "").replace("page", ""))
                    except (ValueError, TypeError):
                        pass
                    processed_elements.add(span)

                text = elem.get_text(separator=" ", strip=True)
                if not text:
                    continue

                # Detect classes
                p_classes = elem.get("class", [])
                if isinstance(p_classes, str):
                    p_classes = [p_classes]

                is_header = elem.name in ["h1", "h2", "h3", "h4"]
                is_question = "qu" in p_classes or bool(re.match(r"^\d+[,–-]\s*\d+", text))
                is_body = "sb" in p_classes or (not is_question and not is_header)

                # Extract paragraph number
                num = None
                par_num_span = elem.find("span", class_="parNum")
                if par_num_span and par_num_span.has_attr("data-pnum"):
                    try:
                        num = int(par_num_span["data-pnum"])
                    except (ValueError, TypeError):
                        pass

                if num is None:
                    m = re.match(r"^(\d+)[,.\s)]", text)
                    num = int(m.group(1)) if m else None

                paragraphs.append(
                    WOLParagraph(
                        number=num,
                        text=text,
                        is_question=is_question,
                        is_body=is_body,
                        is_header=is_header,
                        page=current_page,
                        source="bodyTxt",
                    )
                )
            return paragraphs

        # --- Format B: Direct in article ---
        # Some articles use article.scalableui, others article.article.document
        article = soup.find("article", class_=re.compile(r"article|scalableui"))
        if not article:
            return paragraphs

        current_page = None
        # Use find_all with a list of tags to preserve order
        elements = article.find_all(content_tags, recursive=True)

        # Track spans we've already processed if they were nested
        processed_elements = set()

        for elem in elements:
            if elem in processed_elements:
                continue

            if elem.name == "span" and "pageNum" in elem.get("class", []):
                try:
                    current_page = int(elem.get("id", "").replace("page", ""))
                except (ValueError, TypeError):
                    pass
                continue

            if elem.name in ["p", "h1", "h2", "h3", "h4"]:
                # Check for page markers inside BEFORE processing text
                inner_spans = elem.find_all("span", class_="pageNum")
                for span in inner_spans:
                    try:
                        current_page = int(span.get("id", "").replace("page", ""))
                    except (ValueError, TypeError):
                        pass
                    processed_elements.add(span)

                text = elem.get_text(separator=" ", strip=True)
                if not text:
                    continue

                # Check for parNum span
                par_num_span = elem.find("span", class_="parNum")
                num = None
                if par_num_span and par_num_span.has_attr("data-pnum"):
                    try:
                        num = int(par_num_span["data-pnum"])
                    except (ValueError, TypeError):
                        pass

                # If no parNum, try start of text
                if num is None:
                    m = re.match(r"^(\d+)[,.\s)]", text)
                    num = int(m.group(1)) if m else None

                # Detect classes
                p_classes = elem.get("class", [])
                if isinstance(p_classes, str):
                    p_classes = [p_classes]

                is_header = elem.name in ["h1", "h2", "h3", "h4"]
                is_question = "qu" in p_classes or bool(re.match(r"^\d+[,–-]\s*\d+", text))
                is_body = "sb" in p_classes

                if num is not None or is_body or is_question or is_header:
                    paragraphs.append(
                        WOLParagraph(
                            number=num,
                            text=text,
                            is_question=is_question,
                            is_body=is_body,
                            is_header=is_header,
                            page=current_page,
                            source="direto",
                        )
                    )

        return paragraphs

    @staticmethod
    def locate_paragraphs(
        paragraphs: list[WOLParagraph],
        start_num: int | None = None,
        end_num: int | None = None,
        start_page: int | None = None,
        end_page: int | None = None,
    ) -> list[WOLParagraph]:
        """Locate specific paragraphs by number/position and/or page range."""

        # If no specific paragraph or page requested, return all
        if start_num is None and start_page is None:
            return paragraphs

        # If we have pages but no paragraph numbers, return all elements on those pages
        if start_page is not None and start_num is None:
            if end_page is None:
                end_page = start_page

            # Find the first page marker to know the starting page if it's not explicitly set for early paragraphs
            first_marker_page = next((p.page for p in paragraphs if p.page is not None), None)

            results = []
            last_header = None

            # Track if we have seen any page marker yet
            seen_any_marker = False
            for p in paragraphs:
                # Determine if this element is in the requested page range
                in_range = False
                if p.page is not None:
                    seen_any_marker = True
                    if start_page <= p.page <= end_page:
                        in_range = True
                elif not seen_any_marker:
                    # If it's before any marker, check if the first marker is in range
                    # Heuristic: elements before any marker belong to the first marker's page
                    if first_marker_page is not None and start_page <= first_marker_page <= end_page:
                        in_range = True
                    # Fallback for small pages with no markers
                    elif first_marker_page is None:
                        in_range = True

                if p.is_header:
                    last_header = p

                if in_range:
                    # If we found content in range, ensure we include the last seen header
                    if last_header and last_header not in results:
                        results.append(last_header)
                    if p not in results:
                        results.append(p)

            if results:
                return results

            # If no results and we have no page markers at all, return everything
            # (handles small it-2 lookup pages)
            if not seen_any_marker:
                return paragraphs

            return []

        # Traditional paragraph locating
        work_set = paragraphs
        if start_page is not None:
            if end_page is None:
                end_page = start_page
            # Find the first page marker to know the starting page if it's not explicitly set for early paragraphs
            first_marker_page = next((p.page for p in paragraphs if p.page is not None), None)

            work_set = [
                p for p in paragraphs
                if (p.page is not None and start_page <= p.page <= end_page)
                or (p.page is None and first_marker_page is not None and start_page <= first_marker_page <= end_page)
            ]

        if start_num is None:
            return []

        if end_num is None:
            end_num = start_num

        results: list[WOLParagraph] = []
        for n in range(start_num, end_num + 1):
            encontrado = None

            # Method 1: Explicit paragraph number (skip questions and headers)
            matches = [p for p in work_set if p.number == n and not p.is_header]
            if matches:
                matches.sort(key=lambda x: (not x.is_body, x.is_question))
                if not matches[0].is_question:
                    encontrado = matches[0]

            # Method 2: Positional counting
            if not encontrado:
                filtered = [
                    p
                    for i, p in enumerate(work_set)
                    if not (i == 0 and p.number is None and not p.is_question and not p.is_header)
                    and not p.is_question
                    and not p.is_header
                ]
                if 1 <= n <= len(filtered):
                    encontrado = filtered[n - 1]

            # Method 3: Simple count
            if not encontrado:
                no_questions_or_headers = [p for p in work_set if not p.is_question and not p.is_header]
                if 1 <= n <= len(no_questions_or_headers):
                    encontrado = no_questions_or_headers[n - 1]

            if encontrado:
                results.append(encontrado)

        return results

    @staticmethod
    def extract_lookup_links(html: str) -> list[dict[str, str]]:
        """Extract article links from a lookup page."""
        links = []
        # Look for /lang/wol/d/rX/lp-X/DOCID
        pattern = r'href="(/[^/]+/wol/d/[^/]+/[^/]+/(\d+)[^"]*)"'
        for m in re.finditer(pattern, html):
            url = m.group(1)
            doc_id = m.group(2)
            # Remove fragment
            clean_url = url.split("#")[0]
            links.append(
                {
                    "doc_id": doc_id,
                    "url": clean_url,
                }
            )
        return links
