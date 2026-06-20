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

        # It should extract the path and keep the lp-X part
        assert base_url == "https://wol.jw.org/pt/wol/qt/r5/lp-t"
        mock_http_client.stream.assert_called_with("GET", "https://wol.jw.org/pt")

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
