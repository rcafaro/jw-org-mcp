import pytest
from jw_org_mcp.parser import WOLParser
from jw_org_mcp.models import WOLParagraph

def test_clean_query():
    assert WOLParser.clean_query("cf p. 134 pars. 14,15") == "cf p. 134"
    assert WOLParser.clean_query("w13 15/10 p. 27 § 1") == "w13 15/10 p. 27"
    assert WOLParser.clean_query("od 51 par. 1") == "od 51"
    assert WOLParser.clean_query("lffi 5") == "lffi 5"

def test_extract_page_markers():
    html = '<span id="page10" class="pageNum"></span> some text <span id="page11" class="pageNum"></span>'
    assert WOLParser.extract_page_markers(html) == [10, 11]

def test_locate_paragraphs():
    paragraphs = [
        WOLParagraph(number=1, text="Para 1", source="test"),
        WOLParagraph(number=None, text="Question 1, 2.", is_question=True, is_body=False, source="test"),
        WOLParagraph(number=2, text="Para 2", source="test"),
        WOLParagraph(number=3, text="Para 3", source="test"),
    ]

    # Locate by number
    res = WOLParser.locate_paragraphs(paragraphs, 2)
    assert len(res) == 1
    assert res[0].text == "Para 2"

    # Locate range
    res = WOLParser.locate_paragraphs(paragraphs, 1, 2)
    assert len(res) == 2
    assert res[0].text == "Para 1"
    assert res[1].text == "Para 2"

    # Locate by position (if number not found)
    paragraphs_no_num = [
        WOLParagraph(number=None, text="Intro", is_body=False, source="test"),
        WOLParagraph(number=None, text="Para 1", source="test"),
        WOLParagraph(number=None, text="Para 2", source="test"),
    ]
    # n=1 should be "Para 1" because "Intro" at i=0 without number is skipped by Method 2
    res = WOLParser.locate_paragraphs(paragraphs_no_num, 1)
    assert res[0].text == "Para 1"

def test_locate_paragraphs_no_criteria():
    paragraphs = [
        WOLParagraph(number=1, text="P1", source="test"),
        WOLParagraph(number=2, text="P2", source="test"),
    ]
    # If no paragraph number and no page is specified, it should now return all paragraphs
    res = WOLParser.locate_paragraphs(paragraphs, start_num=None, start_page=None)
    assert len(res) == 2

def test_locate_paragraphs_multiple_matches():
    paragraphs = [
        WOLParagraph(number=15, text="Question 15", is_question=True, is_body=False, source="test"),
        WOLParagraph(number=15, text="Answer 15", is_question=False, is_body=True, source="test"),
    ]

    # Should return both Question 15 and Answer 15
    res = WOLParser.locate_paragraphs(paragraphs, 15)
    assert len(res) == 2
    assert res[0].text == "Question 15"
    assert res[1].text == "Answer 15"

def test_locate_paragraphs_whole_page():
    paragraphs = [
        WOLParagraph(number=None, text="Title", is_header=True, page=10, source="test"),
        WOLParagraph(number=1, text="Para 1", page=10, source="test"),
        WOLParagraph(number=2, text="Para 2", page=11, source="test"),
    ]
    # Page 10 only
    res = WOLParser.locate_paragraphs(paragraphs, start_page=10)
    assert len(res) == 2
    assert res[0].is_header is True
    assert res[1].number == 1

def test_parse_paragraphs_bodytxt():
    html = """
    <div class="bodyTxt">
        <h1>Heading</h1>
        <p>1. First paragraph with <span class="it">italics</span> and <a href="#">link</a>.</p>
        <p>1, 2. Question?</p>
        <p>2. Second paragraph with <span id="page12" class="pageNum"></span> page marker.</p>
    </div>
    """
    paras = WOLParser.parse_paragraphs(html)
    assert len(paras) == 4
    assert paras[0].is_header is True
    assert paras[1].number == 1
    assert "italics and link" in paras[1].text
    assert paras[2].is_question is True
    assert paras[3].number == 2
    assert paras[3].page == 12

def test_parse_paragraphs_direct():
    html = """
    <article class="article document">
        <h1>Article Title</h1>
        <p class="sb"><span class="parNum" data-pnum="1">1</span> Content 1</p>
        <p class="qu">Question?</p>
        <p class="sb">2 Content 2</p>
    </article>
    """
    paras = WOLParser.parse_paragraphs(html)
    assert len(paras) == 4
    assert paras[0].is_header is True
    assert paras[0].text == "Article Title"
    assert paras[1].number == 1
    assert paras[2].is_question is True
    assert paras[3].number == 2
