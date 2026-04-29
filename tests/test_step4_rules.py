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
