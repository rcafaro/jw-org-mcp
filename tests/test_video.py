import pytest
from jw_org_mcp.client import JWOrgClient

def test_extract_video_id():
    client = JWOrgClient()

    # Test direct video ID
    assert client._extract_video_id("pub-jwbvod25_17_VIDEO") == "pub-jwbvod25_17_VIDEO"

    # Test URL with lank parameter
    assert client._extract_video_id("https://www.jw.org/finder?srcid=jwlshare&wtlocale=E&lank=pub-jwbvod25_17_VIDEO") == "pub-jwbvod25_17_VIDEO"

    # Test URL with docid parameter
    assert client._extract_video_id("https://www.jw.org/finder?docid=1011214&wtlocale=E") == "1011214"

    # Test URL with pub- in path
    assert client._extract_video_id("https://www.jw.org/en/library/videos/#en/mediaitems/pub-jwbvod25_17_VIDEO") == "pub-jwbvod25_17_VIDEO"

    # Test non-matching URL
    assert client._extract_video_id("https://www.jw.org/en/news/") == "https://www.jw.org/en/news/"
