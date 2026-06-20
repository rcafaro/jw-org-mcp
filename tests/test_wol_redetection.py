import pytest
from unittest.mock import AsyncMock, MagicMock
from jw_org_mcp.client import JWOrgClient

@pytest.mark.asyncio
async def test_wol_base_url_redetection_on_404():
    client = JWOrgClient()

    # Setup mock HTTP client
    mock_http = AsyncMock()
    client._get_http_client = AsyncMock(return_value=mock_http)

    # Mock base url discovery
    # First time returns old_url, second time returns new_url
    client._get_wol_base_url = AsyncMock()
    client._get_wol_base_url.side_effect = [
        "https://wol.jw.org/en/wol/old",
        "https://wol.jw.org/en/wol/new"
    ]

    # Mock cache remove
    client._cache.remove = MagicMock()

    # Mock responses for _get_with_manual_redirect_handling
    # First call to old_url returns 404
    # Second call (after redetection) to new_url returns 200
    mock_404_resp = MagicMock()
    mock_404_resp.status_code = 404

    mock_200_resp = MagicMock()
    mock_200_resp.status_code = 200
    mock_200_resp.text = '<div class="bodyTxt"><p>Success</p></div>'
    mock_200_resp.url = MagicMock()
    mock_200_resp.url.join = lambda x: x

    async def mock_manual_redirect(c, url, params=None, wol_code=None):
        if "old" in str(url):
            return mock_404_resp
        return mock_200_resp

    with patch("jw_org_mcp.client.JWOrgClient._get_with_manual_redirect_handling", side_effect=mock_manual_redirect):
        res, metadata = await client.get_wol_reference("w13 1/1 p. 1")

        # Verify 404 handled:
        # 1. _get_wol_base_url called again
        assert client._get_wol_base_url.call_count == 2
        # 3. Successful result returned
        assert res.paragraphs[0].text == "Success"

from unittest.mock import patch
