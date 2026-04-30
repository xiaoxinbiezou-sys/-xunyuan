import sys
import types

if "requests" not in sys.modules:
    req = types.ModuleType("requests")
    req.Session = lambda: None
    req.get = lambda *a, **k: None
    req.post = lambda *a, **k: None
    sys.modules["requests"] = req

if "bs4" not in sys.modules:
    bs4 = types.ModuleType("bs4")

    class _BS:  # pragma: no cover
        def __init__(self, *a, **k):
            pass

    bs4.BeautifulSoup = _BS
    sys.modules["bs4"] = bs4

from pipeline import SearchResult, Step3Classifier


def _row(i, url, title, snippet=""):
    return SearchResult(
        id=i,
        entity_id=1,
        query_text="q",
        query_type="base",
        query_priority=1,
        rank=1,
        title=title,
        snippet=snippet,
        url=url,
        provider="test",
    )


def test_youtube_rejected_irrelevant():
    c = Step3Classifier()
    d = c.classify_one(_row(1, "https://www.youtube.com/watch?v=qDZgSO-K6DU", "What is the California DGS Procurement Division? - YouTube"))
    assert d.result == "reject"
    assert d.type == "irrelevant"


def test_lacounty_gov_official_review_for_portal_login():
    c = Step3Classifier()
    d = c.classify_one(_row(2, "https://lacovss.lacounty.gov/", "Welcome to Los Angeles County Vendor Self Service Portal: Home"))
    assert d.type == "official_platform"
    assert d.result == "review"


def test_ucla_edu_official_pass():
    c = Step3Classifier()
    d = c.classify_one(_row(3, "https://www.capitalprograms.ucla.edu/Contracts/Bidding", "Projects Currently Bidding - UCLA Capital Programs Website"))
    assert d.type == "official_platform"
    assert d.result == "pass"


def test_planetbids_third_party_pass():
    c = Step3Classifier()
    d = c.classify_one(_row(4, "https://vendors.planetbids.com/portal/17950/bo/bo-search", "Bid Opportunities - PlanetBids Vendor Portal"))
    assert d.type == "third_party_platform"
    assert d.result == "pass"


def test_bidbanana_rejected_competitor():
    c = Step3Classifier()
    d = c.classify_one(_row(5, "https://bidbanana.thebidlab.com/articles/how-to-find-california-rfps-and-state-government-contracts", "how to find california rfps"))
    assert d.type == "competitor"
    assert d.result == "reject"


def test_other_login_page_now_review_for_recall():
    c = Step3Classifier()
    d = c.classify_one(_row(6, "https://example-bids-site.com/login", "Vendor Login"))
    assert d.type == "other"
    assert d.result == "review"


def test_news_like_title_not_rejected_for_recall():
    c = Step3Classifier()
    d = c.classify_one(_row(7, "https://city.example.org/procurement/news", "Procurement News and Announcements"))
    assert d.result in {"review", "pass"}
