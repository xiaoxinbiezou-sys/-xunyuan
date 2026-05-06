import sys
import types

if "requests" not in sys.modules:
    req = types.ModuleType("requests")
    class _S:
        def get(self,*a,**k):
            raise RuntimeError()
    req.Session = _S
    sys.modules["requests"] = req

if "bs4" not in sys.modules:
    bs4 = types.ModuleType("bs4")
    class _BS:
        pass
    bs4.BeautifulSoup = _BS
    sys.modules["bs4"] = bs4

from pipeline import Step4Discoverer, PageFeatures


def test_login_like_page_not_list():
    d = Step4Discoverer()
    f = PageFeatures(
        final_url="https://camisvr.co.la.ca.us/lacobids",
        title="LA County Solicitations - Account Login",
        text="Account Login UserID Password",
        links=[],
        table_rows=6,
        table_has_header=True,
        repeated_blocks=6,
        titled_link_blocks=6,
        date_count=4,
        keyword_signal_count=2,
        has_pagination=False,
        single_object=False,
        mostly_long_text=False,
        records_count=6,
    )
    is_list, _, _, _, _ = d.is_list_page(f)
    assert is_list is False


def test_allow_external_public_bid_site_link():
    d = Step4Discoverer()
    links = [
        ("Public Bid Site", "https://smart.gep.com/publicRFx/ucal?oloc=215#/"),
        ("Other", "https://example.com/x"),
    ]
    out = d.select_candidate_links("https://procurement.ucop.edu/suppliers", links)
    assert any("smart.gep.com" in x for x in out)


def test_bidding_opportunities_path_controlled_list_exemption():
    d = Step4Discoverer()
    f = PageFeatures(
        final_url="https://suppliers.usc.edu/for-suppliers/bidding-opportunities",
        title="Bidding Opportunities",
        text="Bidding opportunities posted date due date",
        links=[],
        table_rows=0,
        table_has_header=False,
        repeated_blocks=5,
        titled_link_blocks=5,
        date_count=2,
        keyword_signal_count=2,
        has_pagination=False,
        single_object=False,
        mostly_long_text=False,
        records_count=5,
    )
    is_list, conf, _, _, _ = d.is_list_page(f)
    assert is_list is True
    assert conf >= 70


def test_schedule_page_not_list():
    d = Step4Discoverer()
    f = PageFeatures(
        final_url="https://dot.ca.gov/programs/procurement-and-contracts/bid-opening-schedule",
        title="Bid Opening Schedule",
        text="Bid opening schedule calendar dates",
        links=[],
        table_rows=4,
        table_has_header=True,
        repeated_blocks=2,
        titled_link_blocks=2,
        date_count=6,
        keyword_signal_count=1,
        has_pagination=False,
        single_object=False,
        mostly_long_text=False,
        records_count=4,
    )
    is_list, *_ = d.is_list_page(f)
    assert is_list is False


def test_search_shell_page_type():
    d = Step4Discoverer()
    f = PageFeatures(
        final_url="https://doingbusiness.lacounty.gov/open-solicitations",
        title="Open Solicitations",
        text="Open Solicitations Search",
        links=[],
        table_rows=0,
        table_has_header=False,
        repeated_blocks=0,
        titled_link_blocks=0,
        date_count=0,
        keyword_signal_count=0,
        has_pagination=False,
        single_object=False,
        mostly_long_text=False,
        records_count=0,
    )
    assert d.classify_non_list_page_type(f) == "search_shell"


def test_wikipedia_portal_is_not_list():
    d = Step4Discoverer()
    f = PageFeatures(
        final_url="https://en.wikipedia.org/wiki/Portal:Current_events",
        title="Portal:Current events",
        text="latest events news updates",
        links=[("Event A", "https://example.com/a")] * 8,
        table_rows=0,
        table_has_header=False,
        repeated_blocks=8,
        titled_link_blocks=8,
        date_count=8,
        keyword_signal_count=3,
        has_pagination=True,
        single_object=False,
        mostly_long_text=False,
        records_count=10,
    )
    is_list, _, _, triggered, demotion = d.is_list_page(f)
    assert is_list is False
    assert "WIKI_PORTAL_PAGE" in triggered
    assert demotion == "WIKI_PORTAL_PAGE"


def test_tax_guide_style_page_is_not_list():
    d = Step4Discoverer()
    f = PageFeatures(
        final_url="https://sambrotman.com/the-ultimate-guide-to-multistate-taxation-in-california/what-constitutes-doing-business-california",
        title="What Constitutes Doing Business in California",
        text="This tax guide explains doing business in california and wage/tax topics.",
        links=[("Section", "https://example.com/sec")] * 7,
        table_rows=0,
        table_has_header=False,
        repeated_blocks=7,
        titled_link_blocks=7,
        date_count=1,
        keyword_signal_count=0,
        has_pagination=False,
        single_object=False,
        mostly_long_text=True,
        records_count=8,
    )
    is_list, _, _, triggered, demotion = d.is_list_page(f)
    assert is_list is False
    assert ("GUIDE_STYLE_PAGE" in triggered) or ("TAX_GUIDE_PAGE" in triggered)
    assert demotion in {"GUIDE_STYLE_PAGE", "TAX_GUIDE_PAGE"}


def test_bid_opportunities_landing_page_not_list():
    d = Step4Discoverer()
    f = PageFeatures(
        final_url="https://foundationccc.org/our-work/system-support/providing-affordable-products-and-technology/collegebuys/rfp-and-bid-opportunities",
        title="RFP and Bid Opportunities",
        text="Bid opportunities vendor portal view all solicitations.",
        links=[("View opportunities", "https://example.com/opps"), ("Vendor portal", "https://example.com/portal")],
        table_rows=0,
        table_has_header=False,
        repeated_blocks=2,
        titled_link_blocks=2,
        date_count=0,
        keyword_signal_count=2,
        has_pagination=False,
        single_object=False,
        mostly_long_text=False,
        records_count=2,
    )
    is_list, _, _, _, demotion = d.is_list_page(f)
    assert is_list is False
    assert demotion in {"TOO_FEW_RECORDS", "LIST_HARD_GATES_FAILED"}


def test_path_contains_list_hard_passes():
    d = Step4Discoverer()
    f = PageFeatures(
        final_url="https://example.com/procurement/BidLookUp/OpenBidList",
        title="Open Bid List",
        text="Open Bid List",
        links=[],
        table_rows=1,
        table_has_header=False,
        repeated_blocks=1,
        titled_link_blocks=1,
        date_count=0,
        keyword_signal_count=1,
        has_pagination=False,
        single_object=False,
        mostly_long_text=False,
        records_count=1,
    )
    is_list, conf, _, triggered, demotion = d.is_list_page(f)
    assert is_list is True
    assert conf >= 90
    assert "PATH_CONTAINS_LIST" in triggered
    assert demotion is None


def test_pagination_total_records_pattern_hard_passes():
    d = Step4Discoverer()
    f = PageFeatures(
        final_url="https://example.org/procurement/open-bids",
        title="Open Bids",
        text="Page 1 of 25 / Showing 1 to 10 of total 248 records",
        links=[],
        table_rows=1,
        table_has_header=False,
        repeated_blocks=2,
        titled_link_blocks=2,
        date_count=0,
        keyword_signal_count=1,
        has_pagination=True,
        single_object=False,
        mostly_long_text=False,
        records_count=6,
    )
    is_list, conf, _, triggered, demotion = d.is_list_page(f)
    assert is_list is True
    assert conf >= 90
    assert "PAGINATION_TOTAL_RECORDS_PATTERN" in triggered
    assert demotion is None
