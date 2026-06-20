import pytest
from jw_org_mcp.parser import WOLParser
from jw_org_mcp.models import WOLParagraph

def test_parse_paragraphs_with_page_markers():
    html = """
    <article class="article document">
        <p class="sb"><span class="pageNum" id="page18"></span>Paragraph 1 on page 18</p>
        <p class="sb">Paragraph 2 on page 18</p>
        <p class="sb"><span class="pageNum" id="page19"></span>Paragraph 3 on page 19</p>
    </article>
    """
    paras = WOLParser.parse_paragraphs(html)
    assert len(paras) == 3
    assert paras[0].page == 18
    assert paras[1].page == 18
    assert paras[2].page == 19

def test_locate_paragraphs_with_pages():
    paragraphs = [
        WOLParagraph(number=1, text="P1", page=18, source="test"),
        WOLParagraph(number=2, text="P2", page=18, source="test"),
        WOLParagraph(number=3, text="P3", page=19, source="test"),
        WOLParagraph(number=4, text="P4", page=19, source="test"),
    ]

    # Return all on page 18
    res = WOLParser.locate_paragraphs(paragraphs, start_page=18)
    assert len(res) == 2
    assert res[0].text == "P1"
    assert res[1].text == "P2"

    # Return range across pages
    res = WOLParser.locate_paragraphs(paragraphs, start_page=18, end_page=19)
    assert len(res) == 4

    # Return specific paragraphs on specific page
    res = WOLParser.locate_paragraphs(paragraphs, start_num=3, start_page=19)
    assert len(res) == 1
    assert res[0].text == "P3"

def test_is_question_detection_extended():
    html = """
    <article class="article document">
        <p class="qu">14, 15. Question text?</p>
        <p class="sb">14 Content 14</p>
        <p class="sb">15 Content 15</p>
    </article>
    """
    paras = WOLParser.parse_paragraphs(html)
    assert len(paras) == 3
    assert paras[0].is_question is True
    assert paras[1].is_question is False
    assert paras[2].is_question is False

    # Locate should find both the question and the body paragraph
    res = WOLParser.locate_paragraphs(paras, start_num=14)
    assert len(res) == 2
    assert res[0].text == "14, 15. Question text?"
    assert res[1].text == "14 Content 14"
