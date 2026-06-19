import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from jw_org_mcp.client import JWOrgClient

@pytest.mark.asyncio
async def test_wol_base_url_discovery():
    client = JWOrgClient()

    # Mock response for discovery URL
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    # Final URL after follow_redirects=True in httpx
    mock_response.url = httpx.URL("https://wol.jw.org/pt/wol/h/r5/lp-t")
    mock_response.text = '<html><form action="/pt/wol/qt/r5/lp-t"></form></html>'

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.get = AsyncMock(return_value=mock_response)

    with patch.object(JWOrgClient, "_get_http_client", return_value=mock_http_client):
        base_url = await client._get_wol_base_url("pt")

        # It should extract the path from form and replace qt with l
        assert base_url == "https://wol.jw.org/pt/wol/l/r5/lp-t"
        mock_http_client.get.assert_called_with("https://wol.jw.org/pt")

@pytest.mark.asyncio
async def test_get_wol_reference_uses_discovered_url():
    client = JWOrgClient()

    # Discovery mock
    mock_discovery_response = MagicMock(spec=httpx.Response)
    mock_discovery_response.status_code = 200
    mock_discovery_response.url = httpx.URL("https://wol.jw.org/pt/wol/h/r5/lp-t")
    mock_discovery_response.text = '<html><form action="/pt/wol/qt/r5/lp-t"></form></html>'

    # Search/Lookup mock
    mock_search_response = MagicMock(spec=httpx.Response)
    mock_search_response.status_code = 200
    mock_search_response.url = httpx.URL("https://wol.jw.org/pt/wol/b/r5/lp-t/1")
    mock_search_response.text = '<article>Paragraph text</article>'

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.get.side_effect = [mock_discovery_response, mock_search_response]

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

            await client.get_wol_reference("w23.08", language="T")

            # First call should be to discovery
            assert mock_http_client.get.call_args_list[0][0][0] == "https://wol.jw.org/pt"
            # Second call should be to the discovered base URL (with /wol/l/ instead of /wol/qt/)
            assert mock_http_client.get.call_args_list[1][0][0] == "https://wol.jw.org/pt/wol/l/r5/lp-t"
            # And it should have the search query
            assert mock_http_client.get.call_args_list[1][1]["params"] == {"q": "w23.08"}
