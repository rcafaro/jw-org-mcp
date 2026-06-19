import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from jw_org_mcp.client import JWOrgClient
from jw_org_mcp.models import WOLParagraph

@pytest.mark.asyncio
async def test_get_wol_reference_handles_307_redirect():
    client = JWOrgClient()

    # 1. Mock WOL base URL discovery
    with patch.object(client, "_get_wol_base_url", return_value="https://wol.jw.org/en/wol/qt/r1/lp-e"):

        # 2. Mock HTTP responses
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)

        # First call to base_url returns 307
        mock_redirect_response = MagicMock(spec=httpx.Response)
        mock_redirect_response.status_code = 307
        mock_redirect_response.headers = {"Location": "https://wol.jw.org/en/wol/qt/r1/lp-e?q=redirected"}
        mock_redirect_response.url = httpx.URL("https://wol.jw.org/en/wol/qt/r1/lp-e")

        # Second call returns 200 with article content
        mock_final_response = MagicMock(spec=httpx.Response)
        mock_final_response.status_code = 200
        mock_final_response.text = "<html><article><p class='sb'>Redirected Content</p></article></html>"
        mock_final_response.url = httpx.URL("https://wol.jw.org/en/wol/qt/r1/lp-e?q=redirected")

        mock_http_client.get.side_effect = [mock_redirect_response, mock_final_response]

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
                assert mock_http_client.get.call_count == 2
                assert str(mock_http_client.get.call_args_list[0][0][0]) == "https://wol.jw.org/en/wol/qt/r1/lp-e"
                assert str(mock_http_client.get.call_args_list[1][0][0]) == "https://wol.jw.org/en/wol/qt/r1/lp-e?q=redirected"

@pytest.mark.asyncio
async def test_get_wol_reference_handles_307_relative_redirect():
    client = JWOrgClient()

    with patch.object(client, "_get_wol_base_url", return_value="https://wol.jw.org/en/wol/qt/r1/lp-e"):
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)

        # First call to base_url returns 307 with RELATIVE Location
        mock_redirect_response = MagicMock(spec=httpx.Response)
        mock_redirect_response.status_code = 307
        mock_redirect_response.headers = {"Location": "relative-path?q=test"}
        mock_redirect_response.url = httpx.URL("https://wol.jw.org/en/wol/qt/r1/lp-e")

        # Second call
        mock_final_response = MagicMock(spec=httpx.Response)
        mock_final_response.status_code = 200
        mock_final_response.text = "<html><article><p class='sb'>Final Content</p></article></html>"
        mock_final_response.url = httpx.URL("https://wol.jw.org/en/wol/qt/r1/relative-path?q=test")

        mock_http_client.get.side_effect = [mock_redirect_response, mock_final_response]

        with patch.object(client, "_get_http_client", return_value=mock_http_client):
            with patch("jw_org_mcp.client.WOLParser") as mock_parser:
                mock_parser.clean_query.side_effect = lambda x: x
                mock_parser.is_lookup_page.return_value = False
                mock_parser.parse_paragraphs.return_value = [
                    WOLParagraph(number=1, text="Final Content", source="test", page=1)
                ]
                mock_parser.locate_paragraphs.return_value = mock_parser.parse_paragraphs.return_value
                mock_parser.extract_page_markers.return_value = {1}

                # Execute
                await client.get_wol_reference("w23.08")

                # Verify that the relative URL was joined correctly
                assert str(mock_http_client.get.call_args_list[1][0][0]) == "https://wol.jw.org/en/wol/qt/r1/relative-path?q=test"

@pytest.mark.asyncio
async def test_get_wol_reference_handles_multiple_307_hops():
    client = JWOrgClient()

    with patch.object(client, "_get_wol_base_url", return_value="https://wol.jw.org/start"):
        mock_http_client = AsyncMock(spec=httpx.AsyncClient)

        # Hop 1
        resp1 = MagicMock(spec=httpx.Response)
        resp1.status_code = 307
        resp1.headers = {"Location": "/hop2"}
        resp1.url = httpx.URL("https://wol.jw.org/start")

        # Hop 2
        resp2 = MagicMock(spec=httpx.Response)
        resp2.status_code = 307
        resp2.headers = {"Location": "/final"}
        resp2.url = httpx.URL("https://wol.jw.org/hop2")

        # Final
        resp3 = MagicMock(spec=httpx.Response)
        resp3.status_code = 200
        resp3.text = "Final Content"
        resp3.url = httpx.URL("https://wol.jw.org/final")

        mock_http_client.get.side_effect = [resp1, resp2, resp3]

        with patch.object(client, "_get_http_client", return_value=mock_http_client):
            with patch("jw_org_mcp.client.WOLParser") as mock_parser:
                mock_parser.clean_query.side_effect = lambda x: x
                mock_parser.is_lookup_page.return_value = False
                mock_parser.parse_paragraphs.return_value = [WOLParagraph(number=1, text="Final", source="test", page=1)]
                mock_parser.locate_paragraphs.return_value = mock_parser.parse_paragraphs.return_value
                mock_parser.extract_page_markers.return_value = {1}

                await client.get_wol_reference("query")

                assert mock_http_client.get.call_count == 3
                assert str(mock_http_client.get.call_args_list[1][0][0]) == "https://wol.jw.org/hop2"
                assert str(mock_http_client.get.call_args_list[2][0][0]) == "https://wol.jw.org/final"
