import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from jw_org_mcp.client import JWOrgClient

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

        # It should extract the path from form exactly as it is
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

    mock_http_client.get.side_effect = [mock_search_response]

    with patch.object(JWOrgClient, "_get_http_client", return_value=mock_http_client):
        # We need to mock WOLParser.parse_paragraphs as well because we use minimal HTML
        with patch("jw_org_mcp.client.WOLParser") as mock_parser:
            from jw_org_mcp.models import WOLParagraph
            mock_parser.parse_paragraphs.return_value = [
                WOLParagraph(number=1, text="Paragraph text", source="test", page=1)
            ]
            mock_parser.locate_paragraphs.return_value = mock_parser.parse_paragraphs.return_value
            mock_parser.is_lookup_page.return_value = False
            mock_parser.extract_page_markers.return_value = {1}

            with patch("jw_org_mcp.client.JWOrgClient._get_with_manual_307_handling", return_value=mock_search_response):
                await client.get_wol_reference("w23.08", language="T")

                # First call should be to discovery via stream
                assert mock_http_client.stream.call_args_list[0][0][1] == "https://wol.jw.org/pt"
