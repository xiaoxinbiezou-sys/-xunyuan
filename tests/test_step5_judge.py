from pipeline import Step5LLMJudge


def test_review_needed_entry_override_to_entry_page():
    j = Step5LLMJudge(provider="deepseek", model="x", api_key="k")
    j._call_model = lambda prompt: {"final_type": "review_needed", "confidence": 0.3, "reason": "uncertain"}
    d = j.judge_one(
        {
            "url": "https://foundationccc.org/rfp-and-bid-opportunities",
            "title": "RFP and Bid Opportunities",
            "text": "View all bid opportunities in vendor portal",
            "page_type": "entry_page",
        }
    )
    assert d.final_type == "entry_page"
    assert d.confidence >= 0.75
    assert "ENTRY_OVERRIDE" in d.reason


def test_review_needed_not_overridden_when_list_signals_exist():
    j = Step5LLMJudge(provider="deepseek", model="x", api_key="k")
    j._call_model = lambda prompt: {"final_type": "review_needed", "confidence": 0.3, "reason": "uncertain"}
    d = j.judge_one(
        {
            "url": "https://example.com/open-bids",
            "title": "Open Bids",
            "text": "Page 1 of 25 / Showing 1 to 10 of total 248 records",
            "page_type": "list_page",
        }
    )
    assert d.final_type == "review_needed"


def test_extract_json_from_markdown_codeblock():
    j = Step5LLMJudge(provider="deepseek", model="x", api_key="k")
    text = """```json
{
  "final_type": "general_info",
  "confidence": 0.95,
  "reason": "blog article"
}
```"""
    d = j._extract_json_from_text(text)
    assert isinstance(d, dict)
    assert d["final_type"] == "general_info"
