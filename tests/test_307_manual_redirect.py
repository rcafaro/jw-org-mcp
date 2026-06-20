import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from jw_org_mcp.client import JWOrgClient
from jw_org_mcp.models import WOLParagraph

@pytest.mark.asyncio
async def test_get_wol_reference_handles_redirects():
    client = JWOrgClient()

    # 1. Mock WOL base URL discovery
    with patch.object(client, "_get_wol_base_url", return_value="https://wol.jw.org/en/wol/qt/r1/lp-e"):

        # 2. Mock HTTP responses
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)

        # First call returns 200 with article content (redirects handled by httpx)
        mock_final_response = MagicMock(spec=httpx.Response)
        mock_final_response.status_code = 200
        mock_final_response.text = "<html><article><p class='sb'>Redirected Content</p></article></html>"
        mock_final_response.url = httpx.URL("https://wol.jw.org/en/wol/qt/r1/lp-e?q=redirected")
        mock_final_response.history = []

        mock_http_client.get.return_value = mock_final_response

        with patch.object(client, "_get_http_client", return_value=mock_http_client):
            with patch("jw_org_mcp.client.WOLParser") as mock_parser:
                mock_parser.clean_query.side_effect = lambda x: x
                mock_parser.is_lookup_page.return_value = False
                mock_parser.parse_paragraphs.return_value = [
                    WOLParagraph(number=1, text="Redirected Content", source="test", page=1)
                ]
                mock_parser.locate_paragraphs.return_value = mock_parser.parse_paragraphs.return_value
                mock_parser.extract_page_markers.return_value = {1}

                # Execute
                result, metadata = await client.get_wol_reference("w23.08")

                # Verify
                assert result.paragraphs[0].text == "Redirected Content"
                assert mock_http_client.get.call_count == 1
                assert str(mock_http_client.get.call_args_list[0][0][0]) == "https://wol.jw.org/en/wol/qt/r1/lp-e"
