import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from jw_org_mcp.client import JWOrgClient
from jw_org_mcp.models import WOLReferenceResponse

@pytest.mark.asyncio
async def test_it_book_page_consolidation():
    client = JWOrgClient()

    # Mocking _get_wol_base_url
    client._get_wol_base_url = AsyncMock(return_value="https://wol.jw.org/en/wol/s/r1/lp-e")

    # Mocking _get_http_client
    mock_http = AsyncMock()
    client._get_http_client = AsyncMock(return_value=mock_http)

    # First response: Lookup page with multiple links
    lookup_html = """
    <div class="lookupResults">
        <a href="/en/wol/d/r1/lp-e/1001">Entry 1</a>
        <a href="/en/wol/d/r1/lp-e/1002">Entry 2</a>
        <a href="/en/wol/d/r1/lp-e/1003">Entry 3</a>
        <a href="/en/wol/d/r1/lp-e/1004">Entry 4</a>
    </div>
    <div class="article lookup"></div>
    """
    mock_lookup_resp = MagicMock()
    mock_lookup_resp.status_code = 200
    mock_lookup_resp.text = lookup_html
    mock_lookup_resp.url = MagicMock()
    mock_lookup_resp.url.join = lambda x: x

    # Entry responses
    entry1_html = '<div class="bodyTxt"><h1>Entry 1</h1><p><span class="pageNum" id="page50"></span>Content 1</p></div>'
    entry2_html = '<div class="bodyTxt"><h1>Entry 2</h1><p>Content 2</p></div>'
    entry3_html = '<div class="bodyTxt"><h1>Entry 3</h1><p>Content 3</p></div>'
    entry4_html = '<div class="bodyTxt"><h1>Entry 4</h1><p>Content 4</p></div>'

    def mock_get_side_effect(url, params=None, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.history = []
        if "/1001" in str(url):
            mock_resp.text = entry1_html
        elif "/1002" in str(url):
            mock_resp.text = entry2_html
        elif "/1003" in str(url):
            mock_resp.text = entry3_html
        elif "/1004" in str(url):
            mock_resp.text = entry4_html
        else:
            mock_resp.text = lookup_html
        mock_resp.url = MagicMock()
        mock_resp.url.join = lambda x: x
        return mock_resp

    mock_http.get.side_effect = mock_get_side_effect

    # Query with 'it' book and page number
    res, metadata = await client.get_wol_reference("it-1 p. 50")

    # Should have consolidated all 4 entries because it's an 'it' book page reference
    # Total paragraphs: 4 headers + 4 paragraphs = 8
    assert len(res.paragraphs) == 8
    assert "Entry 1" in res.paragraphs[0].text
    assert "Entry 4" in res.paragraphs[6].text

@pytest.mark.asyncio
async def test_it_book_word_heuristic():
    client = JWOrgClient()
    client._get_wol_base_url = AsyncMock(return_value="https://wol.jw.org/en/wol/s/r1/lp-e")
    mock_http = AsyncMock()
    client._get_http_client = AsyncMock(return_value=mock_http)

    lookup_html = """
    <div class="lookupResults">
        <a href="/en/wol/d/r1/lp-e/1001">Entry 1</a>
        <a href="/en/wol/d/r1/lp-e/1002">Entry 2</a>
        <a href="/en/wol/d/r1/lp-e/1003">Entry 3</a>
        <a href="/en/wol/d/r1/lp-e/1004">Entry 4</a>
    </div>
    <div class="article lookup"></div>
    """

    def mock_get_side_effect(url, params=None, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.history = []
        mock_resp.text = lookup_html if "/100" not in str(url) else '<div class="bodyTxt"><p>Content</p></div>'
        mock_resp.url = MagicMock()
        mock_resp.url.join = lambda x: x
        return mock_resp

    mock_http.get.side_effect = mock_get_side_effect

    # Query with 'it' book but NO page number
    res, metadata = await client.get_wol_reference("it-1 Abraham")

    # Should only have followed top 3 (default heuristic for word search)
    # Each followed link has 1 paragraph in this mock
    assert len(res.paragraphs) == 3
