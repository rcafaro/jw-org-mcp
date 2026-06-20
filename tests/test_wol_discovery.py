import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from jw_org_mcp.client import JWOrgClient

@pytest.fixture(autouse=True)
def mock_persistent_cache(tmp_path, monkeypatch):
    from jw_org_mcp.config import settings
    monkeypatch.setattr(settings, "enable_cache", False)
    cache_file = tmp_path / ".jw_org_mcp_wol_cache.json"
    monkeypatch.setattr(JWOrgClient, "PERSISTENT_CACHE_FILE", cache_file)
    yield

@pytest.mark.asyncio
async def test_wol_base_url_discovery():
    client = JWOrgClient()

    # Mock response for discovery URL
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.url = httpx.URL("https://wol.jw.org/pt/wol/h/r5/lp-t")

    async def mock_aiter_bytes(chunk_size):
        yield b'<html><form action="/pt/wol/qt/r5/lp-t"></form></html>'

    mock_response.aiter_bytes = mock_aiter_bytes
    mock_response.raise_for_status = MagicMock()

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)

    # Mock context manager for client.stream
    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_cm.__aexit__ = AsyncMock()

    mock_http_client.stream.return_value = mock_stream_cm

    with patch.object(JWOrgClient, "_get_http_client", return_value=mock_http_client):
        base_url = await client._get_wol_base_url("pt")

        # It should extract the path and keep the lp-X part
        assert base_url == "https://wol.jw.org/pt/wol/qt/r5/lp-t"
        mock_http_client.stream.assert_called_with("GET", "https://wol.jw.org/pt")

@pytest.mark.asyncio
async def test_get_wol_reference_uses_discovered_url():
    client = JWOrgClient()

    # Discovery mock
    mock_discovery_response = MagicMock()
    mock_discovery_response.status_code = 200
    mock_discovery_response.url = httpx.URL("https://wol.jw.org/pt/wol/h/r5/lp-t")
    async def mock_aiter_bytes(chunk_size):
        yield b'<html><form action="/pt/wol/qt/r5/lp-t"></form></html>'
    mock_discovery_response.aiter_bytes = mock_aiter_bytes
    mock_discovery_response.raise_for_status = MagicMock()

    # Search/Lookup mock
    mock_search_response = MagicMock(spec=httpx.Response)
    mock_search_response.status_code = 200
    mock_search_response.url = httpx.URL("https://wol.jw.org/pt/wol/b/r5/lp-t/1")
    mock_search_response.text = '<article>Paragraph text</article>'

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)

    # Mock stream for discovery
    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_discovery_response)
    mock_stream_cm.__aexit__ = AsyncMock()
    mock_http_client.stream.return_value = mock_stream_cm

    # Sequence of responses: discovery stream, search get
    mock_http_client.get.side_effect = [mock_search_response]

    with patch.object(JWOrgClient, "_get_http_client", return_value=mock_http_client):
        # We need to mock WOLParser as well because we use minimal HTML
        with patch("jw_org_mcp.client.WOLParser") as mock_parser:
            from jw_org_mcp.models import WOLParagraph
            mock_parser.parse_paragraphs.return_value = [
                WOLParagraph(number=1, text="Paragraph text", source="test", page=1)
            ]
            mock_parser.locate_paragraphs.return_value = mock_parser.parse_paragraphs.return_value
            mock_parser.is_lookup_page.return_value = False
            mock_parser.extract_page_markers.return_value = {1}
            mock_parser.clean_query.side_effect = lambda x: x # pass through

            with patch("jw_org_mcp.client.JWOrgClient._get_with_manual_redirect_handling", return_value=mock_search_response) as mock_redirect:
                await client.get_wol_reference("w23.08", language="T")
                mock_http_client.stream.assert_called()

@pytest.mark.asyncio
async def test_wol_base_url_strips_query_and_fragment():
    client = JWOrgClient()

    # Mock response for discovery URL with query and fragment in action
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.url = httpx.URL("https://wol.jw.org/en/wol/h/r1/lp-e")

    async def mock_aiter_bytes(chunk_size):
        # action URL has query and fragment
        yield b'<html><form action="/en/wol/qt/r1/lp-e?q=test#frag"></form></html>'

    mock_response.aiter_bytes = mock_aiter_bytes
    mock_response.raise_for_status = MagicMock()

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_cm.__aexit__ = AsyncMock()
    mock_http_client.stream.return_value = mock_stream_cm

    with patch.object(JWOrgClient, "_get_http_client", return_value=mock_http_client):
        base_url = await client._get_wol_base_url("en")

        # It should strip query and fragment but keep lp-e
        assert base_url == "https://wol.jw.org/en/wol/qt/r1/lp-e"

@pytest.mark.asyncio
async def test_wol_base_url_fallback_strips_query_and_fragment():
    client = JWOrgClient()

    # Mock response for discovery URL with no action, fallback to final URL
    mock_response = MagicMock()
    mock_response.status_code = 200
    # Final URL has query and fragment
    mock_response.url = httpx.URL("https://wol.jw.org/en/wol/h/r1/lp-e?q=fallback#frag")

    async def mock_aiter_bytes(chunk_size):
        yield b'<html>no action here</html>'

    mock_response.aiter_bytes = mock_aiter_bytes
    mock_response.raise_for_status = MagicMock()

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_cm.__aexit__ = AsyncMock()
    mock_http_client.stream.return_value = mock_stream_cm

    with patch.object(JWOrgClient, "_get_http_client", return_value=mock_http_client):
        base_url = await client._get_wol_base_url("en")

        # It should strip query and fragment from fallback URL
        assert base_url == "https://wol.jw.org/en/wol/h/r1/lp-e"

@pytest.mark.asyncio
async def test_wol_base_url_persistent_cache(tmp_path, monkeypatch):
    from jw_org_mcp.config import settings
    # Enable cache for this test
    monkeypatch.setattr(settings, "enable_cache", True)

    cache_file = tmp_path / ".jw_org_mcp_wol_cache.json"
    monkeypatch.setattr(JWOrgClient, "PERSISTENT_CACHE_FILE", cache_file)

    client = JWOrgClient()

    # 1. First discovery (cache miss)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.url = httpx.URL("https://wol.jw.org/pt/wol/h/r5/lp-t")
    async def mock_aiter_bytes(chunk_size):
        yield b'<html><form action="/pt/wol/qt/r5/lp-t"></form></html>'
    mock_response.aiter_bytes = mock_aiter_bytes
    mock_response.raise_for_status = MagicMock()

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_cm.__aexit__ = AsyncMock()
    mock_http_client.stream.return_value = mock_stream_cm

    with patch.object(JWOrgClient, "_get_http_client", return_value=mock_http_client):
        base_url = await client._get_wol_base_url("pt")
        assert base_url == "https://wol.jw.org/pt/wol/qt/r5/lp-t"
        assert cache_file.exists()

        # 2. Second discovery (should hit persistent cache)
        # We clear the memory cache to force persistent cache hit
        client._cache.clear()

        # We don't provide a mock for stream because it shouldn't be called
        mock_http_client.stream.side_effect = Exception("Should not be called")

        base_url_2 = await client._get_wol_base_url("pt")
        assert base_url_2 == "https://wol.jw.org/pt/wol/qt/r5/lp-t"
